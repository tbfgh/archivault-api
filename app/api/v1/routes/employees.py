from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.models import Employee, DriveEmployee, FileIndex, Drive, ShelfLocation
from app.schemas import EmployeeCreate, EmployeeUpdate, EmployeeOut

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=List[EmployeeOut])
def list_employees(
    search: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    q = db.query(Employee)
    if search:
        q = q.filter(
            (Employee.full_name.ilike(f"%{search}%")) |
            (Employee.emp_code.ilike(f"%{search}%"))
        )
    if department:
        q = q.filter(Employee.department == department)
    return q.order_by(Employee.full_name).offset(skip).limit(limit).all()


@router.post("", response_model=EmployeeOut)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    existing = db.query(Employee).filter(Employee.emp_code == payload.emp_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Employee code already exists")
    emp = Employee(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/{emp_id}", response_model=EmployeeOut)
def get_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if current_user.role == "employee" and current_user.employee_id != emp_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return emp


@router.patch("/{emp_id}", response_model=EmployeeOut)
def update_employee(
    emp_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/{emp_id}/drives")
def get_employee_drives(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role == "employee" and current_user.employee_id != emp_id:
        raise HTTPException(status_code=403, detail="Access denied")
    assignments = db.query(DriveEmployee).filter(DriveEmployee.employee_id == emp_id).all()
    result = []
    for a in assignments:
        drive = db.query(Drive).filter(Drive.id == a.drive_id).first()
        shelf = db.query(ShelfLocation).filter(ShelfLocation.drive_id == a.drive_id).first()
        result.append({
            "drive_id": drive.id,
            "drive_number": drive.drive_number,
            "status": drive.status,
            "folder_path": a.folder_path,
            "total_files": a.total_files,
            "total_size_bytes": a.total_size_bytes,
            "indexed_at": a.indexed_at,
            "shelf_location": {
                "row_number": shelf.row_number,
                "shelf": shelf.shelf,
                "slot": shelf.slot
            } if shelf else None
        })
    return result


@router.get("/{emp_id}/files")
def get_employee_files(
    emp_id: int,
    path_prefix: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role == "employee" and current_user.employee_id != emp_id:
        raise HTTPException(status_code=403, detail="Access denied")

    q = db.query(FileIndex).filter(FileIndex.employee_id == emp_id)
    if path_prefix:
        q = q.filter(FileIndex.file_path.like(f"{path_prefix}%"))
    if search:
        q = q.filter(FileIndex.file_name.ilike(f"%{search}%"))
    if file_type:
        q = q.filter(FileIndex.file_extension == file_type.lower())

    total = q.count()
    files = q.order_by(FileIndex.file_path).offset(skip).limit(limit).all()
    return {"total": total, "files": files}
