from fastapi import APIRouter
from app.api.v1.routes import (
    auth, employees, drives, files, indexer, requests, admin,
    departments, admin_batches, admin_backup,
)
from app.core.config import settings

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(employees.router)
api_router.include_router(drives.router)
api_router.include_router(files.router)
api_router.include_router(indexer.router)
api_router.include_router(requests.router)
api_router.include_router(admin.router)
api_router.include_router(departments.router)
api_router.include_router(admin_batches.router)
api_router.include_router(admin_backup.router)


@api_router.get("/meta", tags=["Meta"])
def get_meta():
    """Public app metadata for UI chrome (e.g. the admin panel footer)."""
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "company_name": settings.COMPANY_NAME,
    }
