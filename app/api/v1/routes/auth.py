from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user
)
from app.models import User, AuditLog
from app.schemas import LoginRequest, TokenResponse, RefreshRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    log = AuditLog(
        user_id=user.id, action="login",
        entity_type="user", entity_id=user.id,
        ip_address=request.client.host if request.client else None
    )
    db.add(log)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        full_name=user.full_name
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = decoded.get("sub")
    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        role=user.role,
        full_name=user.full_name
    )


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "employee_id": current_user.employee_id
    }


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = AuditLog(user_id=current_user.id, action="logout", entity_type="user", entity_id=current_user.id)
    db.add(log)
    db.commit()
    return {"message": "Logged out successfully"}
