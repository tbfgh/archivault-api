from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from sqlalchemy.exc import DataError
from typing import Optional
import secrets
import string
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.security import get_current_admin, verify_indexer_token
from app.models import (
    IndexerToken, IndexerSession, Drive, ShelfLocation,
    Employee, DriveEmployee, FileIndex, SessionStatus, DriveStatus
)
from app.schemas import (
    IndexerTokenCreate, IndexerTokenOut,
    IndexerDriveOut, IndexerEmployeeOut,
    IndexerSessionStart, IndexerSessionStartResponse,
    IndexerFileBatch, IndexerSessionComplete
)

router = APIRouter(prefix="/indexer", tags=["Indexer"])


def get_token_from_header(x_indexer_token: Optional[str] = Header(None)) -> str:
    if not x_indexer_token:
        raise HTTPException(status_code=401, detail="Indexer token required")
    return x_indexer_token


def _check_field_lengths(file_objects: list) -> None:
    """
    Pre-flight check against the model's *actual* column limits (read from
    FileIndex.__table__ so this stays correct automatically if a column
    width ever changes again) — so an oversized value is reported as a
    clean 4xx naming the exact field/file, instead of surfacing as a bulk
    insert failure with no indication of which of the batch's files it was.
    This is a safety net for any future column, not a substitute for
    sizing columns realistically in the first place (see migration 0003).
    """
    limits = {
        col.name: col.type.length
        for col in FileIndex.__table__.columns
        if getattr(col.type, "length", None)
    }
    for obj in file_objects:
        for field, limit in limits.items():
            value = getattr(obj, field, None)
            if isinstance(value, str) and len(value) > limit:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"File '{obj.file_path}' has a '{field}' value of "
                        f"{len(value)} characters, which exceeds the column "
                        f"limit of {limit}. No files from this batch were saved — "
                        f"retry after excluding or fixing this entry."
                    )
                )


# ─── Token Management (Admin only) ────────────────────────────────────────────

@router.post("/token", response_model=IndexerTokenOut)
def create_indexer_token(
    payload: IndexerTokenCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    alphabet = string.ascii_letters + string.digits
    token_str = "av_" + "".join(secrets.choice(alphabet) for _ in range(48))
    token = IndexerToken(name=payload.name, token=token_str, created_by_id=current_user.id)
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


@router.get("/tokens", response_model=list[IndexerTokenOut])
def list_indexer_tokens(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    return db.query(IndexerToken).order_by(IndexerToken.created_at.desc()).all()


@router.delete("/token/{token_id}")
def revoke_indexer_token(
    token_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    token = db.query(IndexerToken).filter(IndexerToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    token.is_active = False
    db.commit()
    return {"message": "Token revoked"}


@router.get("/token/verify")
def verify_token(
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    if not verify_indexer_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return {"valid": True, "message": "Token is valid"}


# ─── Selection Lists (Indexer token) ───────────────────────────────────────────
# The Indexer tool no longer accepts free-text drive/employee details; it must
# select from records that already exist in the system. These endpoints back
# those selection dropdowns.

@router.get("/drives", response_model=list[IndexerDriveOut])
def list_indexer_drives(
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    if not verify_indexer_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return db.query(Drive).filter(
        Drive.status == DriveStatus.active
    ).order_by(Drive.drive_number).all()


@router.get("/employees", response_model=list[IndexerEmployeeOut])
def list_indexer_employees(
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    if not verify_indexer_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return db.query(Employee).filter(
        Employee.is_active == True
    ).order_by(Employee.full_name).all()


# ─── Indexing Session ─────────────────────────────────────────────────────────

@router.post("/session/start", response_model=IndexerSessionStartResponse)
def start_session(
    payload: IndexerSessionStart,
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    token_record = db.query(IndexerToken).filter(
        IndexerToken.token == token, IndexerToken.is_active == True
    ).first()
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid token")

    token_record.last_used_at = datetime.now(timezone.utc)

    # Drive must already be registered (with shelf location) via the admin panel.
    drive = db.query(Drive).filter(Drive.id == payload.drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=404,
            detail="Drive not found. Register it in the admin panel before indexing."
        )
    if drive.status != DriveStatus.active:
        raise HTTPException(
            status_code=400,
            detail=f"Drive {drive.drive_number} is not active (status: {drive.status.value})."
        )

    if not payload.employees:
        raise HTTPException(status_code=400, detail="At least one employee assignment is required")

    # Employees must already exist — no auto-creation from indexer input.
    emp_map = {}
    for ep in payload.employees:
        emp = db.query(Employee).filter(Employee.id == ep.employee_id).first()
        if not emp:
            raise HTTPException(
                status_code=404,
                detail=f"Employee id {ep.employee_id} not found. Register them in the admin panel before indexing."
            )
        emp_map[str(emp.id)] = emp.id

        # Upsert DriveEmployee (folder path is the only thing the indexer supplies)
        de = db.query(DriveEmployee).filter(
            DriveEmployee.drive_id == drive.id,
            DriveEmployee.employee_id == emp.id
        ).first()
        if de:
            de.folder_path = ep.folder_path
        else:
            de = DriveEmployee(drive_id=drive.id, employee_id=emp.id, folder_path=ep.folder_path)
            db.add(de)

    # Create session
    session_key = secrets.token_hex(32)
    session = IndexerSession(
        session_key=session_key,
        drive_id=drive.id,
        token_id=token_record.id,
        status=SessionStatus.running,
        employees_data=emp_map
    )
    db.add(session)
    db.commit()

    return IndexerSessionStartResponse(
        session_key=session_key,
        drive_id=drive.id,
        message="Session started. Begin uploading file batches."
    )


@router.post("/session/{session_key}/files")
def upload_file_batch(
    session_key: str,
    payload: IndexerFileBatch,
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    if not verify_indexer_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid token")

    session = db.query(IndexerSession).filter(
        IndexerSession.session_key == session_key,
        IndexerSession.status == SessionStatus.running
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    emp_map = session.employees_data or {}
    file_objects = []

    for fr in payload.files:
        emp_id = emp_map.get(str(fr.employee_id))
        if not emp_id:
            continue
        file_objects.append(FileIndex(
            drive_id=session.drive_id,
            employee_id=emp_id,
            session_id=session.id,
            file_name=fr.file_name,
            file_path=fr.file_path,
            file_extension=fr.file_extension,
            file_size_bytes=fr.file_size_bytes,
            file_modified_at=fr.file_modified_at,
            file_created_at=fr.file_created_at,
            is_directory=fr.is_directory,
            depth_level=fr.depth_level
        ))

    _check_field_lengths(file_objects)

    try:
        db.bulk_save_objects(file_objects)
        db.commit()
    except DataError as e:
        db.rollback()
        # Safety net for anything _check_field_lengths didn't anticipate
        # (e.g. a column this endpoint doesn't know about yet). Not expected
        # to trigger in normal operation now that columns are sized
        # realistically (migration 0003) and the pre-flight check above
        # catches the common case.
        raise HTTPException(
            status_code=422,
            detail=(
                "This batch could not be saved — one or more files have a "
                f"field value too large for the database: {e.orig}"
            )
        )

    return {"inserted": len(file_objects), "message": "Batch saved"}


@router.post("/session/{session_key}/complete")
def complete_session(
    session_key: str,
    payload: IndexerSessionComplete,
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db)
):
    if not verify_indexer_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid token")

    session = db.query(IndexerSession).filter(
        IndexerSession.session_key == session_key
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = SessionStatus.completed
    session.total_files = payload.total_files
    session.total_size_bytes = payload.total_size_bytes
    session.completed_at = datetime.now(timezone.utc)
    session.error_log = payload.error_log

    # Update drive used_gb
    drive = db.query(Drive).filter(Drive.id == session.drive_id).first()
    if drive:
        drive.used_gb = payload.total_size_bytes / (1024 ** 3)

    # Update DriveEmployee totals
    emp_map = session.employees_data or {}
    for emp_id in set(emp_map.values()):
        count = db.query(FileIndex).filter(
            FileIndex.drive_id == session.drive_id,
            FileIndex.employee_id == emp_id
        ).count()
        size = db.query(func.sum(FileIndex.file_size_bytes)).filter(
            FileIndex.drive_id == session.drive_id,
            FileIndex.employee_id == emp_id
        ).scalar() or 0

        de = db.query(DriveEmployee).filter(
            DriveEmployee.drive_id == session.drive_id,
            DriveEmployee.employee_id == emp_id
        ).first()
        if de:
            de.total_files = count
            de.total_size_bytes = size
            de.indexed_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": "Session completed successfully",
        "total_files": payload.total_files,
        "total_size_bytes": payload.total_size_bytes
    }
