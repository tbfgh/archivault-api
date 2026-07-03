from fastapi import APIRouter
from app.api.v1.routes import auth, employees, drives, files, indexer, requests, admin

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(employees.router)
api_router.include_router(drives.router)
api_router.include_router(files.router)
api_router.include_router(indexer.router)
api_router.include_router(requests.router)
api_router.include_router(admin.router)
