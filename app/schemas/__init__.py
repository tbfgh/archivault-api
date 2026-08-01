from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    superadmin = "superadmin"
    admin = "admin"
    employee = "employee"

class DriveStatus(str, Enum):
    active = "active"
    damaged = "damaged"
    retired = "retired"

class RequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    full_name: str

class RefreshRequest(BaseModel):
    refresh_token: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters long")
        return v


# ─── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.employee
    employee_id: Optional[int] = None
    department_ids: List[int] = []  # only meaningful when role == admin

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    employee_id: Optional[int] = None

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    employee_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Employee ─────────────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    emp_code: str
    full_name: str
    department: Optional[str] = None       # legacy string, kept as fallback
    department_id: Optional[int] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_joined: Optional[datetime] = None
    date_left: Optional[datetime] = None
    notes: Optional[str] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None       # legacy string, kept as fallback
    department_id: Optional[int] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_joined: Optional[datetime] = None
    date_left: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeOut(BaseModel):
    id: int
    emp_code: str
    full_name: str
    department: Optional[str]        # legacy string, kept as fallback display value
    department_id: Optional[int]
    designation: Optional[str]
    email: Optional[str]
    date_joined: Optional[datetime]
    date_left: Optional[datetime]
    notes: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Department ───────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str
    slug: str

class DepartmentOut(BaseModel):
    id: int
    name: str
    slug: str
    employee_count: int
    user_count: int

class UserDepartmentAssign(BaseModel):
    user_id: int
    department_ids: List[int]

class BatchOut(BaseModel):
    session_id: int
    drive_id: int
    drive_number: Optional[str] = None
    status: str
    total_files: int
    total_size_bytes: int
    started_at: datetime
    completed_at: Optional[datetime]

class BatchBulkUpdate(BaseModel):
    employee_id: Optional[int] = None
    drive_id: Optional[int] = None


# ─── Shelf Location ───────────────────────────────────────────────────────────

class ShelfLocationCreate(BaseModel):
    row_number: str
    shelf: str
    slot: str
    notes: Optional[str] = None

class ShelfLocationOut(BaseModel):
    id: int
    row_number: str
    shelf: str
    slot: str
    notes: Optional[str]

    class Config:
        from_attributes = True


# ─── Drive ────────────────────────────────────────────────────────────────────

class DriveCreate(BaseModel):
    drive_number: str
    capacity_gb: float
    drive_type: str = "SAS"
    filesystem: str = "NTFS"
    status: DriveStatus = DriveStatus.active
    notes: Optional[str] = None
    shelf_location: Optional[ShelfLocationCreate] = None

class DriveUpdate(BaseModel):
    capacity_gb: Optional[float] = None
    status: Optional[DriveStatus] = None
    notes: Optional[str] = None
    shelf_location: Optional[ShelfLocationCreate] = None

class DriveOut(BaseModel):
    id: int
    drive_number: str
    capacity_gb: float
    used_gb: float
    drive_type: str
    filesystem: str
    status: str
    notes: Optional[str]
    date_added: datetime
    shelf_location: Optional[ShelfLocationOut]

    class Config:
        from_attributes = True


# ─── File Index ───────────────────────────────────────────────────────────────

class FileOut(BaseModel):
    id: int
    drive_id: int
    employee_id: int
    file_name: str
    file_path: str
    file_extension: Optional[str]
    file_size_bytes: int
    file_modified_at: Optional[datetime]
    file_created_at: Optional[datetime]
    is_directory: bool
    depth_level: int
    indexed_at: datetime

    class Config:
        from_attributes = True

class FileSearchResult(BaseModel):
    file: FileOut
    drive_number: str
    shelf_location: Optional[ShelfLocationOut]
    employee_name: str
    emp_code: str
    estimated_retrieval_seconds: float

class RetrievalEstimate(BaseModel):
    file_ids: List[int]
    total_size_bytes: int
    total_size_mb: float
    estimated_seconds: float
    estimated_minutes: float
    drive_ids: List[int]
    drives_required: List[str]


# ─── Indexer ──────────────────────────────────────────────────────────────────

class IndexerTokenCreate(BaseModel):
    name: str

class IndexerTokenOut(BaseModel):
    id: int
    name: str
    token: str
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

# Lightweight read models exposed to the Indexer tool (token-authenticated)
# so it can populate selection dropdowns instead of accepting free text.
class IndexerDriveOut(BaseModel):
    id: int
    drive_number: str
    capacity_gb: float
    used_gb: float
    status: str
    shelf_location: Optional[ShelfLocationOut]

    class Config:
        from_attributes = True

class IndexerEmployeeOut(BaseModel):
    id: int
    emp_code: str
    full_name: str
    department: Optional[str]

    class Config:
        from_attributes = True

class IndexerEmployeeAssignment(BaseModel):
    employee_id: int
    folder_path: str

class IndexerSessionStart(BaseModel):
    drive_id: int
    employees: List[IndexerEmployeeAssignment]

class IndexerSessionStartResponse(BaseModel):
    session_key: str
    drive_id: int
    message: str

class FileRecord(BaseModel):
    file_name: str
    file_path: str
    file_extension: Optional[str]
    file_size_bytes: int
    file_modified_at: Optional[datetime]
    file_created_at: Optional[datetime]
    is_directory: bool
    depth_level: int
    employee_id: int

class IndexerFileBatch(BaseModel):
    files: List[FileRecord]

class IndexerSessionComplete(BaseModel):
    total_files: int
    total_size_bytes: int
    error_log: Optional[str] = None


# ─── Retrieval Request ────────────────────────────────────────────────────────

class RetrievalRequestCreate(BaseModel):
    employee_id: int
    file_ids: List[int]
    notes: Optional[str] = None

class RetrievalRequestUpdate(BaseModel):
    status: RequestStatus
    admin_notes: Optional[str] = None

class RetrievalRequestOut(BaseModel):
    id: int
    employee_id: int
    status: str
    notes: Optional[str]
    admin_notes: Optional[str]
    estimated_minutes: Optional[float]
    file_ids: List[Any]
    total_size_bytes: int
    requested_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Admin Stats ──────────────────────────────────────────────────────────────

class AdminStats(BaseModel):
    total_drives: int
    total_employees: int
    total_files: int
    total_size_bytes: int
    total_size_tb: float
    pending_requests: int
    active_drives: int
