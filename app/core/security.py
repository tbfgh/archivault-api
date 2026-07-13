from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    from app.models import User
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_admin(current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_current_superadmin(current_user=Depends(get_current_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user


def get_visible_employee_ids(current_user, db: Session) -> Optional[list]:
    """
    Returns the list of employee_ids the current_user is allowed to see,
    or None if they may see all employees without restriction.

    - superadmin: None (no filtering)
    - employee: only their own linked employee_id
    - admin: employees belonging to any department the admin is assigned to.
      An admin with no departments assigned sees nothing (safe default) rather
      than silently seeing everyone.
    """
    from app.models import Employee

    if current_user.role == "superadmin":
        return None
    if current_user.role == "employee":
        return [current_user.employee_id] if current_user.employee_id else []

    # admin
    dept_ids = [d.id for d in current_user.departments]
    if not dept_ids:
        return []
    rows = db.query(Employee.id).filter(Employee.department_id.in_(dept_ids)).all()
    return [r[0] for r in rows]


def verify_indexer_token(token: str, db: Session) -> bool:
    from app.models import IndexerToken
    record = db.query(IndexerToken).filter(
        IndexerToken.token == token,
        IndexerToken.is_active == True
    ).first()
    return record is not None
