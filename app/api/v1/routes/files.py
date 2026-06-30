from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models import FileIndex, Drive, ShelfLocation, Employee

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("")
def search_files(
    search: Optional[str] = Query(None),
    emp_code: Optional[str] = Query(None),
    drive_number: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    q = db.query(FileIndex)

    # Employees can only see their own files
    if current_user.role == "employee":
        q = q.filter(FileIndex.employee_id == current_user.employee_id)
    else:
        if emp_code:
            emp = db.query(Employee).filter(Employee.emp_code == emp_code).first()
            if emp:
                q = q.filter(FileIndex.employee_id == emp.id)
        if drive_number:
            drive = db.query(Drive).filter(Drive.drive_number == drive_number).first()
            if drive:
                q = q.filter(FileIndex.drive_id == drive.id)

    if search:
        q = q.filter(FileIndex.file_name.ilike(f"%{search}%"))
    if file_type:
        q = q.filter(FileIndex.file_extension == file_type.lower().lstrip("."))

    total = q.count()
    files = q.order_by(FileIndex.file_path).offset(skip).limit(limit).all()

    results = []
    for f in files:
        drive = db.query(Drive).filter(Drive.id == f.drive_id).first()
        shelf = db.query(ShelfLocation).filter(ShelfLocation.drive_id == f.drive_id).first()
        emp = db.query(Employee).filter(Employee.id == f.employee_id).first()
        size_mb = f.file_size_bytes / (1024 * 1024)
        estimated_seconds = size_mb / settings.SAS_READ_SPEED_MBPS

        results.append({
            "file": {
                "id": f.id,
                "file_name": f.file_name,
                "file_path": f.file_path,
                "file_extension": f.file_extension,
                "file_size_bytes": f.file_size_bytes,
                "file_modified_at": f.file_modified_at,
                "is_directory": f.is_directory,
                "indexed_at": f.indexed_at,
            },
            "drive_number": drive.drive_number if drive else None,
            "shelf_location": {
                "row_number": shelf.row_number,
                "shelf": shelf.shelf,
                "slot": shelf.slot
            } if shelf else None,
            "employee_name": emp.full_name if emp else None,
            "emp_code": emp.emp_code if emp else None,
            "estimated_retrieval_seconds": round(estimated_seconds, 2)
        })

    return {"total": total, "results": results}


@router.get("/retrieval-estimate")
def retrieval_estimate(
    file_ids: str = Query(..., description="Comma-separated file IDs"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ids = [int(i) for i in file_ids.split(",") if i.strip().isdigit()]
    files = db.query(FileIndex).filter(FileIndex.id.in_(ids)).all()

    total_bytes = sum(f.file_size_bytes for f in files)
    total_mb = total_bytes / (1024 * 1024)
    # Add 60 seconds per drive for physical fetch
    drive_ids = list(set(f.drive_id for f in files))
    physical_overhead = len(drive_ids) * 60
    estimated_seconds = (total_mb / settings.SAS_READ_SPEED_MBPS) + physical_overhead

    drives = db.query(Drive).filter(Drive.id.in_(drive_ids)).all()
    drive_numbers = [d.drive_number for d in drives]

    return {
        "file_count": len(files),
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_mb, 2),
        "estimated_seconds": round(estimated_seconds, 2),
        "estimated_minutes": round(estimated_seconds / 60, 2),
        "drives_required": drive_numbers,
        "physical_drives_count": len(drive_ids),
        "note": f"Includes ~{len(drive_ids) * 60}s for physical drive retrieval from shelf"
    }


@router.get("/{file_id}")
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    f = db.query(FileIndex).filter(FileIndex.id == file_id).first()
    if not f:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    if current_user.role == "employee" and current_user.employee_id != f.employee_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")

    drive = db.query(Drive).filter(Drive.id == f.drive_id).first()
    shelf = db.query(ShelfLocation).filter(ShelfLocation.drive_id == f.drive_id).first()

    return {
        "file": f,
        "drive_number": drive.drive_number if drive else None,
        "shelf_location": shelf,
    }
