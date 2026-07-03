from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import Optional
import secrets
import string
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.security import get_current_admin, verify_indexer_token
from app.models import (
    IndexerToken, IndexerSession, Drive, ShelfLocation,
    Employee, DriveEmployee, FileIndex, SessionStatus
)
from app.schemas import (
    IndexerTokenCreate, IndexerTokenOut,
    IndexerSessionStart, IndexerSessionStartResponse,
    IndexerFileBatch, IndexerSessionComplete
)

router = APIRouter(prefix="/indexer", tags=["Indexer"])


def get_token_from_header(x_indexer_token: Optional[str] = Header(None)) -> str:
    if not x_indexer_token:
        raise HTTPException(status_code=401, detail="Indexer token required")
    return x_indexer_token


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

    # Get or create drive
    drive = db.query(Drive).filter(Drive.drive_number == payload.drive_number).first()
    if not drive:
        drive = Drive(
            drive_number=payload.drive_number,
            capacity_gb=payload.capacity_gb,
            used_gb=0.0
        )
        db.add(drive)
        db.flush()

    # Upsert shelf location
    shelf = db.query(ShelfLocation).filter(ShelfLocation.drive_id == drive.id).first()
    if shelf:
        shelf.row_number = payload.shelf_row
        shelf.shelf = payload.shelf_shelf
        shelf.slot = payload.shelf_slot
    else:
        shelf = ShelfLocation(
            drive_id=drive.id,
            row_number=payload.shelf_row,
            shelf=payload.shelf_shelf,
            slot=payload.shelf_slot
        )
        db.add(shelf)

    # Ensure employees exist
    emp_map = {}
    for ep in payload.employees:
        emp = db.query(Employee).filter(Employee.emp_code == ep.emp_code).first()
        if not emp:
            emp = Employee(emp_code=ep.emp_code, full_name=ep.full_name, department=ep.department)
            db.add(emp)
            db.flush()
        emp_map[ep.emp_code] = emp.id

        # Upsert DriveEmployee
        de = db.query(DriveEmployee).filter(
            DriveEmployee.drive_id == drive.id,
            DriveEmployee.employee_id == emp.id
        ).first()
        if not de:
            de = DriveEmployee(drive_id=drive.id, employee_id=emp.id, folder_path=ep.folder_path)
            db.add(de)

    # Create session
    session_key = secrets.token_hex(32)
    session = IndexerSession(
        session_key=session_key,
        drive_id=drive.id,
        token_id=token_record.id,
        status=SessionStatus.running,
        employees_data={ep.emp_code: emp_map[ep.emp_code] for ep in payload.employees}
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
        emp_id = emp_map.get(fr.emp_code)
        if not emp_id:
            continue
        file_objects.append(FileIndex(
            drive_id=session.drive_id,
            employee_id=emp_id,
            file_name=fr.file_name,
            file_path=fr.file_path,
            file_extension=fr.file_extension,
            file_size_bytes=fr.file_size_bytes,
            file_modified_at=fr.file_modified_at,
            file_created_at=fr.file_created_at,
            is_directory=fr.is_directory,
            depth_level=fr.depth_level
        ))

    db.bulk_save_objects(file_objects)
    db.commit()

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
    for emp_code, emp_id in emp_map.items():
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
