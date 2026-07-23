import json
import subprocess
import tarfile
import shutil
from pathlib import Path
from threading import Thread

from app.core.database import engine
from app.services.backup_service import (
    create_backup_archive, prune_old_safety_snapshots, BACKUP_DIR, _parse_db_url,
)

STATUS_FILE = BACKUP_DIR / "restore_status.json"
SAFETY_DIR = BACKUP_DIR / "pre_restore_safety"
SAFETY_DIR.mkdir(parents=True, exist_ok=True)


def write_status(state: str, detail: str = ""):
    STATUS_FILE.write_text(json.dumps({"state": state, "detail": detail}))


def get_status() -> dict:
    if not STATUS_FILE.exists():
        return {"state": "idle"}
    return json.loads(STATUS_FILE.read_text())


def run_restore_from_path(archive_path: Path, cleanup_source: bool = False):
    """
    Core restore logic, run in a background thread so the HTTP request that
    triggered it can return immediately rather than blocking on gunicorn's
    worker timeout. Runs entirely in-process — no systemd unit, no sudo,
    no cross-process handoff.
    """
    extract_dir = archive_path.parent / f"restore_tmp_{archive_path.stem}"
    try:
        write_status("safety_snapshot", "Backing up current database before restore")
        safety_path = SAFETY_DIR / f"pre-restore-safety-{archive_path.stem}.tar.gz"
        create_backup_archive(destination=safety_path)
        prune_old_safety_snapshots(SAFETY_DIR, keep=3)

        write_status("extracting", "Unpacking backup archive")
        extract_dir.mkdir(exist_ok=True)
        with tarfile.open(archive_path) as tar:
            tar.extractall(extract_dir, filter="data")

        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Archive is missing manifest.json — not a valid ArchiveVault backup")

        write_status("closing_connections", "Releasing database connection pool")
        engine.dispose()

        write_status("restoring_db", "Restoring database from backup")
        db = _parse_db_url()
        sql_file = extract_dir / "db.sql"
        result = subprocess.run(
            [
                "psql",
                "-U", db["user"],
                "-h", db["host"],
                "-p", db["port"],
                "-d", db["dbname"],
                "-v", "ON_ERROR_STOP=1",
                "-f", str(sql_file),
            ],
            env={"PGPASSWORD": db["password"]},
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Database restore failed: {result.stderr.strip()}")

        write_status("done", "Restore complete. Please log in again.")

    except Exception as e:
        write_status("error", str(e))
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if cleanup_source:
            archive_path.unlink(missing_ok=True)


def start_restore(archive_path: Path, cleanup_source: bool = False):
    write_status("queued", "Restore starting")
    Thread(target=run_restore_from_path, args=(archive_path, cleanup_source), daemon=True).start()
