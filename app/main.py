from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import api_router
from app.services import restore_service

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ArchiveVault — Offline Drive Index & Retrieval System",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)
# NOTE (v2): docs_url, redoc_url and openapi_url all live at the API root.
# In v1, nginx only proxied /api/, /docs and /health individually, so a
# request for /openapi.json (which /docs needs to render) fell through to
# the catch-all block and got a plain-text response instead of JSON —
# that's why Swagger UI failed to load. v2's nginx template proxies the
# entire API root in one location block instead of enumerating paths,
# so this class of bug can't recur.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def maintenance_mode_guard(request: Request, call_next):
    """
    While a restore is in progress, block every request except the backup/
    restore admin endpoints themselves (so the frontend can keep polling
    status) and /health. Everything else gets a clear 503 rather than
    hitting a database mid-restore.
    """
    status = restore_service.get_status()
    if status["state"] not in ("idle", "done", "error"):
        path = request.url.path
        if not path.startswith("/api/v1/admin/backup") and path != "/health":
            return JSONResponse(
                status_code=503,
                content={"detail": "System is restoring from backup. Please wait a moment and try again."},
            )
    return await call_next(request)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {"status": "ok"}
