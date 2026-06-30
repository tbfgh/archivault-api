# ArchiveVault API

Backend service for ArchiveVault — indexes and tracks ex-employee data stored on offline SAS drives.

## Stack
- Python 3.12 + FastAPI
- PostgreSQL 16
- SQLAlchemy + Alembic (migrations)
- Nginx + Gunicorn (production)

## One-Command Setup (Ubuntu 24.04 LTS)

```bash
git clone <this-repo> archivault-api
cd archivault-api
sudo bash setup.sh
```

The script will prompt for:
- Server domain/IP
- Admin email & password
- Frontend URL (for CORS)

It installs PostgreSQL, Python, Nginx, creates the database, runs all migrations, creates your admin account, generates your first indexer token, and starts the API as a systemd service.

At the end it prints your **API URL**, **admin credentials**, and **indexer token** — save these.

## Upgrading (Future Versions)

```bash
cd /opt/archivault
sudo bash upgrade.sh
```

This pulls the latest code, installs new dependencies, runs **only new** database migrations (existing data is never touched), and restarts the service. Safe to run anytime.

## Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL etc.
alembic upgrade head
uvicorn app.main:app --reload
```

API docs available at `http://localhost:8000/docs`.

## Project Structure

```
app/
  main.py              FastAPI app entrypoint
  core/                config, database, security (JWT, password hashing)
  models/               SQLAlchemy models (all tables)
  schemas/             Pydantic request/response schemas
  api/v1/routes/       All API endpoints, grouped by resource
migrations/            Alembic migrations — versioned schema history
scripts/               One-off setup scripts (create_admin, generate_token)
setup.sh                Full server provisioning (run once)
upgrade.sh              Safe upgrade script (run anytime)
```

## Database Migrations

Every schema change must go through Alembic — never edit the database directly.

```bash
# After changing a model in app/models/__init__.py:
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

Commit the generated migration file in `migrations/versions/` to git. When you deploy, `upgrade.sh` applies it automatically.

## API Overview

All endpoints are under `/api/v1`. Full interactive docs at `/docs`.

| Group | Purpose |
|---|---|
| `/auth` | Login, token refresh, current user |
| `/employees` | Ex-employee records, their drives, their files |
| `/drives` | Physical drive registry + shelf locations |
| `/files` | Global file search, retrieval time estimates |
| `/indexer` | Endpoints used by the Indexer tool (token-authenticated) |
| `/requests` | Retrieval request lifecycle |
| `/admin` | Stats, user management |

## Indexer Authentication

The Indexer tool (separate repo) authenticates via a long-lived token, not user login. Generate tokens from the admin UI (`Indexer Tokens` page) or via API:

```bash
curl -X POST https://your-server/api/v1/indexer/token \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Linux Mint - IT Desk"}'
```

## Environment Variables

See `.env.example` for all options. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing key — keep secret |
| `SAS_READ_SPEED_MBPS` | Used to calculate retrieval time estimates (default 500) |
| `ALLOWED_ORIGINS` | Comma-separated frontend URLs for CORS |
