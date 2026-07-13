import subprocess
import tarfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings

BACKUP_DIR = Path("/opt/archivault/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _parse_db_url():
    """
    Parses settings.DATABASE_URL (e.g. postgresql://user:pass@host:5432/dbname)
    into the pieces pg_dump/psql need. Raises if it isn't a Postgres URL —
    backup/restore only supports Postgres, matching production deployment.
    """
    parsed = urlparse(settings.DATABASE_URL)
    if not parsed.scheme.startswith("postgresql"):
        raise RuntimeError(
            f"Backup/restore only supports PostgreSQL. DATABASE_URL scheme is '{parsed.scheme}'."
        )
    return {
        "user": parsed.username,
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": parsed.path.lstrip("/"),
    }


def create_backup_archive(destination: Path | None = None) -> Path:
    """
    Creates a full backup archive (currently just a Postgres dump, wrapped in
    a .tar.gz with a manifest for forward-compatibility if file storage is
    ever added). Used by both the manual 'Create Backup Now' endpoint and the
    automatic pre-restore safety snapshot.
    """
    db = _parse_db_url()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if destination is None:
        destination = BACKUP_DIR / f"archivault-backup-{timestamp}.tar.gz"

    staging_dir = BACKUP_DIR / f"staging-{timestamp}-{destination.stem}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        dump_path = staging_dir / "db.sql"
        result = subprocess.run(
            [
                "pg_dump",
                "-U", db["user"],
                "-h", db["host"],
                "-p", db["port"],
                "-d", db["dbname"],
                "-f", str(dump_path),
                "--no-owner",
            ],
            env={"PGPASSWORD": db["password"]},
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(
            f'{{"created_at": "{timestamp}", "db_name": "{db["dbname"]}", '
            f'"app_version": "{settings.APP_VERSION}"}}'
        )

        with tarfile.open(destination, "w:gz") as tar:
            tar.add(dump_path, arcname="db.sql")
            tar.add(manifest_path, arcname="manifest.json")

        return destination
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def list_backups(directory: Path = BACKUP_DIR) -> list[dict]:
    if not directory.exists():
        return []
    return sorted(
        [
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            for f in directory.glob("*.tar.gz")
        ],
        key=lambda x: x["created_at"],
        reverse=True,
    )


def delete_backup(filename: str, directory: Path = BACKUP_DIR) -> None:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("Invalid filename")
    path = directory / filename
    if not path.exists():
        raise FileNotFoundError("Backup not found")
    path.unlink()


def prune_old_safety_snapshots(directory: Path, keep: int = 3) -> None:
    if not directory.exists():
        return
    snapshots = sorted(directory.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[keep:]:
        old.unlink()
