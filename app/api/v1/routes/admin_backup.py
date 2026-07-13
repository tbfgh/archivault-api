from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from app.core.security import get_current_superadmin
from app.services import backup_service, restore_service

router = APIRouter(prefix="/admin/backup", tags=["Admin Backup"])


@router.post("/create")
def create_backup(current_user=Depends(get_current_superadmin)):
    try:
        path = backup_service.create_backup_archive()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"filename": path.name, "size_bytes": path.stat().st_size}


@router.get("/list")
def list_backups(current_user=Depends(get_current_superadmin)):
    return backup_service.list_backups()


@router.get("/safety-list")
def safety_list(current_user=Depends(get_current_superadmin)):
    return backup_service.list_backups(directory=restore_service.SAFETY_DIR)


@router.get("/download/{filename}")
def download_backup(filename: str, current_user=Depends(get_current_superadmin)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = backup_service.BACKUP_DIR / filename
    if not path.exists():
        path = restore_service.SAFETY_DIR / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, filename=filename, media_type="application/gzip")


@router.delete("/{filename}")
def delete_backup(filename: str, current_user=Depends(get_current_superadmin)):
    try:
        backup_service.delete_backup(filename)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"deleted": filename}


@router.post("/restore")
async def restore_from_upload(
    file: UploadFile = File(...),
    current_user=Depends(get_current_superadmin),
):
    status = restore_service.get_status()
    if status["state"] not in ("idle", "done", "error"):
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    if not file.filename.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Expected a .tar.gz ArchiveVault backup file")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    upload_path = backup_service.BACKUP_DIR / f"restore-upload-{timestamp}.tar.gz"
    with open(upload_path, "wb") as f:
        f.write(await file.read())

    restore_service.start_restore(upload_path, cleanup_source=True)
    return {"message": "Restore started"}


@router.post("/restore-existing/{filename}")
def restore_from_existing(filename: str, current_user=Depends(get_current_superadmin)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    status = restore_service.get_status()
    if status["state"] not in ("idle", "done", "error"):
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    archive_path = backup_service.BACKUP_DIR / filename
    if not archive_path.exists():
        archive_path = restore_service.SAFETY_DIR / filename
        if not archive_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")

    restore_service.start_restore(archive_path, cleanup_source=False)
    return {"message": "Restore started"}


@router.get("/restore/status")
def restore_status(current_user=Depends(get_current_superadmin)):
    return restore_service.get_status()
