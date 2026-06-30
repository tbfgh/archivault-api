from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.core.database import get_db
from app.core.security import get_current_admin, get_password_hash
from app.models import User, Employee, Drive, FileIndex, RetrievalRequest, RequestStatus
from app.schemas import UserCreate, UserUpdate, UserOut, AdminStats
from typing import List

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStats)
def get_stats(db: Session = Depends(get_db), current_user=Depends(get_current_admin)):
    total_drives = db.query(Drive).count()
    active_drives = db.query(Drive).filter(Drive.status == "active").count()
    total_employees = db.query(Employee).count()
    total_files = db.query(FileIndex).count()
    total_size = db.query(func.sum(FileIndex.file_size_bytes)).scalar() or 0
    pending_requests = db.query(RetrievalRequest).filter(
        RetrievalRequest.status == RequestStatus.pending
    ).count()

    return AdminStats(
        total_drives=total_drives,
        active_drives=active_drives,
        total_employees=total_employees,
        total_files=total_files,
        total_size_bytes=total_size,
        total_size_tb=round(total_size / (1024 ** 4), 4),
        pending_requests=pending_requests
    )


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), current_user=Depends(get_current_admin)):
    return db.query(User).order_by(User.full_name).all()


@router.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        employee_id=payload.employee_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
