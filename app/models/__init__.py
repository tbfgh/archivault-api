from sqlalchemy import (
    Column, Integer, String, BigInteger, Boolean,
    DateTime, ForeignKey, Text, Float, Enum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    employee = "employee"


class DriveStatus(str, enum.Enum):
    active = "active"
    damaged = "damaged"
    retired = "retired"


class RequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"


class SessionStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.employee, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="user", foreign_keys=[employee_id])
    retrieval_requests = relationship("RetrievalRequest", back_populates="requested_by_user")
    audit_logs = relationship("AuditLog", back_populates="user")


# ─── Employee ─────────────────────────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    emp_code = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False, index=True)
    department = Column(String(100), nullable=True)
    designation = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    date_joined = Column(DateTime(timezone=True), nullable=True)
    date_left = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="employee", foreign_keys=[User.employee_id])
    drive_assignments = relationship("DriveEmployee", back_populates="employee")
    file_indexes = relationship("FileIndex", back_populates="employee")
    retrieval_requests = relationship("RetrievalRequest", back_populates="employee")


# ─── Drive ────────────────────────────────────────────────────────────────────

class Drive(Base):
    __tablename__ = "drives"

    id = Column(Integer, primary_key=True, index=True)
    drive_number = Column(String(50), unique=True, index=True, nullable=False)
    capacity_gb = Column(Float, nullable=False)
    used_gb = Column(Float, default=0.0)
    drive_type = Column(String(20), default="SAS")
    filesystem = Column(String(20), default="NTFS")
    status = Column(Enum(DriveStatus), default=DriveStatus.active)
    notes = Column(Text, nullable=True)
    date_added = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    shelf_location = relationship("ShelfLocation", back_populates="drive", uselist=False)
    employee_assignments = relationship("DriveEmployee", back_populates="drive")
    file_indexes = relationship("FileIndex", back_populates="drive")
    indexer_sessions = relationship("IndexerSession", back_populates="drive")


# ─── Shelf Location ───────────────────────────────────────────────────────────

class ShelfLocation(Base):
    __tablename__ = "shelf_locations"

    id = Column(Integer, primary_key=True, index=True)
    drive_id = Column(Integer, ForeignKey("drives.id"), unique=True, nullable=False)
    row_number = Column(String(20), nullable=False)
    shelf = Column(String(20), nullable=False)
    slot = Column(String(20), nullable=False)
    notes = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    drive = relationship("Drive", back_populates="shelf_location")


# ─── Drive ↔ Employee (many-to-many) ─────────────────────────────────────────

class DriveEmployee(Base):
    __tablename__ = "drive_employees"

    id = Column(Integer, primary_key=True, index=True)
    drive_id = Column(Integer, ForeignKey("drives.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    folder_path = Column(String(1024), nullable=True)
    total_files = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    drive = relationship("Drive", back_populates="employee_assignments")
    employee = relationship("Employee", back_populates="drive_assignments")


# ─── File Index ───────────────────────────────────────────────────────────────

class FileIndex(Base):
    __tablename__ = "file_index"

    id = Column(Integer, primary_key=True, index=True)
    drive_id = Column(Integer, ForeignKey("drives.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    file_name = Column(String(512), nullable=False, index=True)
    file_path = Column(Text, nullable=False)
    file_extension = Column(String(20), nullable=True, index=True)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_modified_at = Column(DateTime(timezone=True), nullable=True)
    file_created_at = Column(DateTime(timezone=True), nullable=True)
    is_directory = Column(Boolean, default=False)
    depth_level = Column(Integer, default=0)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())

    drive = relationship("Drive", back_populates="file_indexes")
    employee = relationship("Employee", back_populates="file_indexes")


# ─── Indexer Token ────────────────────────────────────────────────────────────

class IndexerToken(Base):
    __tablename__ = "indexer_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    sessions = relationship("IndexerSession", back_populates="token")


# ─── Indexer Session ──────────────────────────────────────────────────────────

class IndexerSession(Base):
    __tablename__ = "indexer_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_key = Column(String(64), unique=True, nullable=False, index=True)
    drive_id = Column(Integer, ForeignKey("drives.id"), nullable=False)
    token_id = Column(Integer, ForeignKey("indexer_tokens.id"), nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.running)
    total_files = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)
    employees_data = Column(JSON, nullable=True)
    error_log = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    drive = relationship("Drive", back_populates="indexer_sessions")
    token = relationship("IndexerToken", back_populates="sessions")


# ─── Retrieval Request ────────────────────────────────────────────────────────

class RetrievalRequest(Base):
    __tablename__ = "retrieval_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(RequestStatus), default=RequestStatus.pending)
    notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    estimated_minutes = Column(Float, nullable=True)
    file_ids = Column(JSON, nullable=False, default=list)
    total_size_bytes = Column(BigInteger, default=0)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    employee = relationship("Employee", back_populates="retrieval_requests")
    requested_by_user = relationship("User", back_populates="retrieval_requests")


# ─── Audit Log ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="audit_logs")
