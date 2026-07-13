from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models import IndexerSession, FileIndex, Employee, Drive
from app.schemas import BatchOut, BatchBulkUpdate

router = APIRouter(prefix="/admin/batches", tags=["Admin"])

BATCH_PREVIEW_LIMIT = 50


@router.get("", response_model=List[BatchOut])
def list_batches(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    sessions = (
        db.query(IndexerSession)
        .order_by(IndexerSession.started_at.desc())
        .offset(skip).limit(limit)
        .all()
    )
    out = []
    for s in sessions:
        drive = db.query(Drive).filter(Drive.id == s.drive_id).first()
        out.append(BatchOut(
            session_id=s.id,
            drive_id=s.drive_id,
            drive_number=drive.drive_number if drive else None,
            status=s.status,
            total_files=s.total_files or 0,
            total_size_bytes=s.total_size_bytes or 0,
            started_at=s.started_at,
            completed_at=s.completed_at,
        ))
    return out


@router.get("/{session_id}/files")
def get_batch_files(
    session_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    session = db.query(IndexerSession).filter(IndexerSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Batch not found")

    q = db.query(FileIndex).filter(FileIndex.session_id == session_id)
    total = q.count()
    preview = q.order_by(FileIndex.file_path).limit(BATCH_PREVIEW_LIMIT).all()

    return {
        "session_id": session_id,
        "total": total,
        "preview_limit": BATCH_PREVIEW_LIMIT,
        "files": [
            {
                "id": f.id,
                "file_name": f.file_name,
                "file_path": f.file_path,
                "employee_id": f.employee_id,
                "drive_id": f.drive_id,
                "file_size_bytes": f.file_size_bytes,
            }
            for f in preview
        ],
    }


@router.put("/{session_id}/bulk-update")
def bulk_update_batch(
    session_id: int,
    payload: BatchBulkUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    session = db.query(IndexerSession).filter(IndexerSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Batch not found")

    q = db.query(FileIndex).filter(FileIndex.session_id == session_id)
    if q.count() == 0:
        raise HTTPException(status_code=404, detail="No files are linked to this batch")

    update_fields = {}
    if payload.employee_id is not None:
        if not db.query(Employee).filter(Employee.id == payload.employee_id).first():
            raise HTTPException(status_code=400, detail="Invalid employee_id")
        update_fields["employee_id"] = payload.employee_id
    if payload.drive_id is not None:
        if not db.query(Drive).filter(Drive.id == payload.drive_id).first():
            raise HTTPException(status_code=400, detail="Invalid drive_id")
        update_fields["drive_id"] = payload.drive_id

    if not update_fields:
        raise HTTPException(status_code=400, detail="Provide employee_id and/or drive_id to update")

    q.update(update_fields, synchronize_session=False)
    db.commit()

    return {
        "session_id": session_id,
        "updated_count": db.query(FileIndex).filter(FileIndex.session_id == session_id).count(),
        "fields_changed": list(update_fields.keys()),
    }
