from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.core.config import settings
from app.models import RetrievalRequest, FileIndex, Drive, RequestStatus
from app.schemas import RetrievalRequestCreate, RetrievalRequestUpdate, RetrievalRequestOut

router = APIRouter(prefix="/requests", tags=["Retrieval Requests"])


@router.get("", response_model=List[RetrievalRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    q = db.query(RetrievalRequest)
    if current_user.role == "employee":
        q = q.filter(RetrievalRequest.requested_by_id == current_user.id)
    return q.order_by(RetrievalRequest.requested_at.desc()).all()


@router.post("", response_model=RetrievalRequestOut)
def create_request(
    payload: RetrievalRequestCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Validate files exist and belong to employee
    files = db.query(FileIndex).filter(FileIndex.id.in_(payload.file_ids)).all()
    if not files:
        raise HTTPException(status_code=400, detail="No valid files found")

    if current_user.role == "employee":
        if any(f.employee_id != current_user.employee_id for f in files):
            raise HTTPException(status_code=403, detail="Cannot request files from other employees")

    total_bytes = sum(f.file_size_bytes for f in files)
    total_mb = total_bytes / (1024 * 1024)
    drive_ids = list(set(f.drive_id for f in files))
    physical_overhead = len(drive_ids) * 60
    estimated_seconds = (total_mb / settings.SAS_READ_SPEED_MBPS) + physical_overhead

    req = RetrievalRequest(
        employee_id=payload.employee_id,
        requested_by_id=current_user.id,
        file_ids=payload.file_ids,
        notes=payload.notes,
        total_size_bytes=total_bytes,
        estimated_minutes=round(estimated_seconds / 60, 2)
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/{req_id}", response_model=RetrievalRequestOut)
def get_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    req = db.query(RetrievalRequest).filter(RetrievalRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if current_user.role == "employee" and req.requested_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return req


@router.patch("/{req_id}/status", response_model=RetrievalRequestOut)
def update_request_status(
    req_id: int,
    payload: RetrievalRequestUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    req = db.query(RetrievalRequest).filter(RetrievalRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = payload.status
    if payload.admin_notes:
        req.admin_notes = payload.admin_notes
    if payload.status == RequestStatus.completed:
        req.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(req)
    return req
