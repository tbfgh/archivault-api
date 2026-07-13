from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_superadmin
from app.models import Department, User
from app.schemas import DepartmentCreate, DepartmentOut, UserDepartmentAssign

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=List[DepartmentOut])
def list_departments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)  # readable by admin + superadmin (needed for user-creation dropdown)
):
    depts = db.query(Department).order_by(Department.name).all()
    return [
        DepartmentOut(
            id=d.id, name=d.name, slug=d.slug,
            employee_count=len(d.employees), user_count=len(d.users)
        )
        for d in depts
    ]


@router.post("", response_model=DepartmentOut)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    if db.query(Department).filter(
        (Department.slug == payload.slug) | (Department.name == payload.name)
    ).first():
        raise HTTPException(status_code=400, detail="A department with this name or slug already exists")
    dept = Department(name=payload.name, slug=payload.slug)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return DepartmentOut(id=dept.id, name=dept.name, slug=dept.slug, employee_count=0, user_count=0)


@router.put("/{department_id}", response_model=DepartmentOut)
def rename_department(
    department_id: int,
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    conflict = db.query(Department).filter(
        Department.id != department_id,
        (Department.slug == payload.slug) | (Department.name == payload.name)
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail="Another department already uses this name or slug")
    dept.name = payload.name
    dept.slug = payload.slug
    db.commit()
    return DepartmentOut(
        id=dept.id, name=dept.name, slug=dept.slug,
        employee_count=len(dept.employees), user_count=len(dept.users)
    )


@router.delete("/{department_id}")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if dept.employees:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete '{dept.name}' — {len(dept.employees)} employee(s) are still "
                "assigned to it. Reassign them to another department first."
            ),
        )
    db.delete(dept)
    db.commit()
    return {"deleted": department_id}


@router.get("/users")
def list_users_with_departments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    users = db.query(User).order_by(User.full_name).all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "departments": [{"id": d.id, "name": d.name} for d in u.departments],
        }
        for u in users
    ]


@router.put("/assign")
def assign_user_departments(
    payload: UserDepartmentAssign,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_superadmin)
):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(
            status_code=400,
            detail="Superadmins already have unrestricted access and cannot be scoped to departments",
        )
    depts = db.query(Department).filter(Department.id.in_(payload.department_ids)).all()
    if len(depts) != len(payload.department_ids):
        raise HTTPException(status_code=400, detail="One or more department_ids are invalid")
    user.departments = depts  # full replacement of the assignment set
    db.commit()
    return {"user_id": user.id, "departments": [d.name for d in user.departments]}
