#!/bin/bash
# ============================================================
#  ArchiveVault API — Server Setup Script (v2)
#  Tested on: Ubuntu 24.04 LTS
#  Run as: sudo bash setup.sh
#
#  v2 changes:
#   - API_PORT / BIND_HOST are configurable and independent of the UI's port
#   - Optional "direct expose" mode (no nginx) for split-server setups
#   - nginx template proxies the whole API root in ONE location block
#     (fixes /docs + /openapi.json 404/shadowing bug from v1)
#   - bcrypt pinned via requirements.txt, no separate step needed
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
error()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
header() { echo -e "\n${BLUE}══════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}══════════════════════════════════════${NC}"; }

# ── Must run as root ──────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then error "Please run as root: sudo bash setup.sh"; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/archivault"
APP_USER="archivault"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/archivault"

header "ArchiveVault API Setup (v2)"
echo ""
echo "This script will install and configure:"
echo "  • PostgreSQL 16"
echo "  • Python 3.12 + virtualenv"
echo "  • FastAPI application"
echo "  • systemd service"
echo "  • Nginx reverse proxy (optional)"
echo ""

# ── Collect config from user ──────────────────────────────────
read -p "API port [8000]: " API_PORT
API_PORT="${API_PORT:-8000}"

echo ""
echo "How should this API be reachable?"
echo "  1) Behind nginx on port 80/443 with a domain or IP (recommended)"
echo "  2) Directly on ${API_PORT} with no nginx (quick split-server setup, no domain yet)"
read -p "Choose [1/2, default 1]: " EXPOSE_MODE
EXPOSE_MODE="${EXPOSE_MODE:-1}"

if [ "$EXPOSE_MODE" == "1" ]; then
    read -p "Enter the domain or IP this API will be reached at (e.g. api.company.com or 192.168.1.100): " SERVER_DOMAIN
    BIND_HOST="127.0.0.1"
else
    SERVER_DOMAIN=""
    BIND_HOST="0.0.0.0"
    warn "Direct-expose mode: the API will be plain HTTP on port ${API_PORT}, reachable at http://<this-server-ip>:${API_PORT}"
    warn "No TLS in this mode — fine for a trusted LAN, not for the public internet."
fi

read -p "Enter admin email: " ADMIN_EMAIL
read -s -p "Enter admin password: " ADMIN_PASSWORD; echo ""
read -p "Enter admin full name [IT Manager]: " ADMIN_NAME
ADMIN_NAME="${ADMIN_NAME:-IT Manager}"
read -p "Frontend origin(s) for CORS, comma-separated (e.g. http://192.168.1.101,https://archivault-ui.company.com): " FRONTEND_URL

# Generate secrets
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
SECRET_KEY=$(openssl rand -base64 48 | tr -d '/+=')

header "Step 1: System Update"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget gnupg2 software-properties-common \
    build-essential libpq-dev openssl python3.12 python3.12-venv \
    python3.12-dev python3-pip git ufw
if [ "$EXPOSE_MODE" == "1" ]; then
    apt-get install -y -qq nginx
fi
log "System packages installed"

header "Step 2: PostgreSQL 16"
if ! command -v psql &>/dev/null; then
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg
    echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    apt-get update -qq
    apt-get install -y -qq postgresql-16 postgresql-client-16
fi
systemctl enable postgresql
systemctl start postgresql
log "PostgreSQL installed and running"

# Create DB and user
sudo -u postgres psql -c "DROP DATABASE IF EXISTS archivault;" 2>/dev/null || true
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'archivault') THEN
    CREATE USER archivault WITH PASSWORD '$DB_PASSWORD';
  ELSE
    ALTER USER archivault WITH PASSWORD '$DB_PASSWORD';
  END IF;
END
\$\$;
CREATE DATABASE archivault OWNER archivault;
GRANT ALL PRIVILEGES ON DATABASE archivault TO archivault;
SQL
log "Database 'archivault' created with user 'archivault'"

header "Step 3: Application User & Directory"
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home "$APP_DIR" --create-home "$APP_USER"
fi
mkdir -p "$APP_DIR" "$LOG_DIR"
cp -r "$SCRIPT_DIR/." "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$LOG_DIR"
log "App directory created at $APP_DIR"

header "Step 4: Python Virtual Environment"
sudo -u "$APP_USER" python3.12 -m venv "$VENV_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
log "Python virtualenv ready (bcrypt pinned to 4.0.1 — avoids the passlib crash)"

header "Step 5: Environment Configuration"
cat > "$APP_DIR/.env" <<ENV
DATABASE_URL=postgresql://archivault:${DB_PASSWORD}@localhost:5432/archivault
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
APP_NAME=ArchiveVault
APP_VERSION=2.0.0
DEBUG=false
ALLOWED_ORIGINS=${FRONTEND_URL}
BIND_HOST=${BIND_HOST}
API_PORT=${API_PORT}
SAS_READ_SPEED_MBPS=500
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_FULL_NAME=${ADMIN_NAME}
ENV
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
log ".env file created (API_PORT=${API_PORT}, BIND_HOST=${BIND_HOST})"

header "Step 6: Database Migrations"
cd "$APP_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/alembic" upgrade head
log "Database schema created"

header "Step 7: Create Admin User"
sudo -u "$APP_USER" "$VENV_DIR/bin/python" "$APP_DIR/scripts/create_admin.py"
log "Admin user created"

header "Step 8: Generate Indexer Token"
INDEXER_TOKEN=$(sudo -u "$APP_USER" "$VENV_DIR/bin/python" "$APP_DIR/scripts/generate_token.py")
log "Indexer token generated"

header "Step 9: systemd Service"
cat > /etc/systemd/system/archivault.service <<SERVICE
[Unit]
Description=ArchiveVault API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind ${BIND_HOST}:${API_PORT} \
    --timeout 120 \
    --access-logfile ${LOG_DIR}/access.log \
    --error-logfile ${LOG_DIR}/error.log
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable archivault
systemctl start archivault
log "systemd service created and started, listening on ${BIND_HOST}:${API_PORT}"

if [ "$EXPOSE_MODE" == "1" ]; then
    header "Step 10: Nginx Configuration"
    # v2 fix: proxy the ENTIRE API root in one location block instead of
    # enumerating /api/, /docs, /health separately. This is what was
    # silently breaking /openapi.json (and therefore /docs) in v1 — any
    # path not explicitly listed fell through to a static text response.
    cat > /etc/nginx/sites-available/archivault-api <<NGINX
server {
    listen 80;
    server_name ${SERVER_DOMAIN};

    client_max_body_size 50M;

    location / {
        proxy_pass http://${BIND_HOST}:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
NGINX

    ln -sf /etc/nginx/sites-available/archivault-api /etc/nginx/sites-enabled/archivault-api
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl restart nginx
    log "Nginx configured — single proxy block, no path shadowing"

    header "Step 11: Firewall"
    ufw allow OpenSSH
    ufw allow 'Nginx Full'
    ufw --force enable
    log "Firewall configured"

    API_BASE_URL="http://${SERVER_DOMAIN}"
else
    header "Step 10: Firewall"
    ufw allow OpenSSH
    ufw allow "${API_PORT}/tcp"
    ufw --force enable
    log "Firewall configured — opened port ${API_PORT}"

    SERVER_IP=$(hostname -I | awk '{print $1}')
    API_BASE_URL="http://${SERVER_IP}:${API_PORT}"
fi

# ── Final Summary ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ArchiveVault API Setup Complete!            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  API Base URL  : ${BLUE}${API_BASE_URL}${NC}   ${YELLOW}← paste this into the UI's setup screen${NC}"
echo -e "  API Docs      : ${BLUE}${API_BASE_URL}/docs${NC}"
echo -e "  Health Check  : ${BLUE}${API_BASE_URL}/health${NC}"
echo ""
echo -e "  Admin Email   : ${YELLOW}${ADMIN_EMAIL}${NC}"
echo -e "  Admin Pass    : ${YELLOW}${ADMIN_PASSWORD}${NC}"
echo ""
echo -e "  Indexer Token : ${YELLOW}${INDEXER_TOKEN}${NC}"
echo ""
echo -e "  DB Name       : archivault"
echo -e "  DB User       : archivault"
echo -e "  DB Password   : ${YELLOW}${DB_PASSWORD}${NC}"
echo ""
echo -e "${YELLOW}  ► Save the Indexer Token — paste it into the indexer's config.json (server_url)${NC}"
echo -e "${YELLOW}  ► Save DB credentials securely${NC}"
echo -e "${YELLOW}  ► If you add more UI origins later, edit ALLOWED_ORIGINS in ${APP_DIR}/.env and 'systemctl restart archivault'${NC}"
echo ""
echo -e "  Logs          : $LOG_DIR"
echo -e "  App directory : $APP_DIR"
echo ""
