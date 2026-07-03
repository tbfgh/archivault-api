from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import api_router

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
