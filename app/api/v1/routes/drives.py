from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.models import Drive, ShelfLocation, DriveEmployee, Employee
from app.schemas import DriveCreate, DriveUpdate, DriveOut

router = APIRouter(prefix="/drives", tags=["Drives"])


@router.get("", response_model=List[DriveOut])
def list_drives(
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    return db.query(Drive).order_by(Drive.drive_number).offset(skip).limit(limit).all()


@router.post("", response_model=DriveOut)
def create_drive(
    payload: DriveCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    existing = db.query(Drive).filter(Drive.drive_number == payload.drive_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Drive number already exists")

    drive_data = payload.model_dump(exclude={"shelf_location"})
    drive = Drive(**drive_data)
    db.add(drive)
    db.flush()

    if payload.shelf_location:
        shelf = ShelfLocation(drive_id=drive.id, **payload.shelf_location.model_dump())
        db.add(shelf)

    db.commit()
    db.refresh(drive)
    return drive


@router.get("/{drive_id}", response_model=DriveOut)
def get_drive(
    drive_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    drive = db.query(Drive).filter(Drive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    return drive


@router.patch("/{drive_id}", response_model=DriveOut)
def update_drive(
    drive_id: int,
    payload: DriveUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    drive = db.query(Drive).filter(Drive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")

    update_data = payload.model_dump(exclude_unset=True, exclude={"shelf_location"})
    for field, value in update_data.items():
        setattr(drive, field, value)

    if payload.shelf_location:
        shelf = db.query(ShelfLocation).filter(ShelfLocation.drive_id == drive_id).first()
        if shelf:
            for field, value in payload.shelf_location.model_dump().items():
                setattr(shelf, field, value)
        else:
            shelf = ShelfLocation(drive_id=drive_id, **payload.shelf_location.model_dump())
            db.add(shelf)

    db.commit()
    db.refresh(drive)
    return drive


@router.get("/{drive_id}/employees")
def get_drive_employees(
    drive_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    drive = db.query(Drive).filter(Drive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    assignments = db.query(DriveEmployee).filter(DriveEmployee.drive_id == drive_id).all()
    result = []
    for a in assignments:
        emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
        result.append({
            "employee_id": emp.id,
            "emp_code": emp.emp_code,
            "full_name": emp.full_name,
            "department": emp.department,
            "folder_path": a.folder_path,
            "total_files": a.total_files,
            "total_size_bytes": a.total_size_bytes,
            "indexed_at": a.indexed_at,
        })
    return result
