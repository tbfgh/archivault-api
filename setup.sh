#!/bin/bash
# ============================================================
#  ArchiveVault — Server Setup Script
#  Tested on: Ubuntu 24.04 LTS
#  Run as: sudo bash setup.sh
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

header "ArchiveVault Server Setup"
echo ""
echo "This script will install and configure:"
echo "  • PostgreSQL 16"
echo "  • Python 3.12 + virtualenv"
echo "  • FastAPI application"
echo "  • Nginx reverse proxy"
echo "  • systemd service"
echo ""

# ── Collect config from user ──────────────────────────────────
read -p "Enter your domain or server IP (e.g. archivault.company.com or 192.168.1.100): " SERVER_DOMAIN
read -p "Enter admin email: " ADMIN_EMAIL
read -s -p "Enter admin password: " ADMIN_PASSWORD; echo ""
read -p "Enter admin full name [IT Manager]: " ADMIN_NAME
ADMIN_NAME="${ADMIN_NAME:-IT Manager}"
read -p "Frontend URL (for CORS, e.g. http://192.168.1.101 or https://archivault-ui.company.com): " FRONTEND_URL

# Generate secrets
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
SECRET_KEY=$(openssl rand -base64 48 | tr -d '/+=')

header "Step 1: System Update"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget gnupg2 software-properties-common \
    build-essential libpq-dev openssl nginx python3.12 python3.12-venv \
    python3.12-dev python3-pip git ufw
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
log "Python virtualenv ready"

header "Step 5: Environment Configuration"
cat > "$APP_DIR/.env" <<ENV
DATABASE_URL=postgresql://archivault:${DB_PASSWORD}@localhost:5432/archivault
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
APP_NAME=ArchiveVault
APP_VERSION=1.0.0
DEBUG=false
ALLOWED_ORIGINS=${FRONTEND_URL},http://localhost:3000
SAS_READ_SPEED_MBPS=500
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_FULL_NAME=${ADMIN_NAME}
ENV
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
log ".env file created"

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
    --bind 127.0.0.1:8000 \
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
log "systemd service created and started"

header "Step 10: Nginx Configuration"
cat > /etc/nginx/sites-available/archivault <<NGINX
server {
    listen 80;
    server_name ${SERVER_DOMAIN};

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host \$host;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    location / {
        return 200 'ArchiveVault API is running. Use /docs for API reference.';
        add_header Content-Type text/plain;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/archivault /etc/nginx/sites-enabled/archivault
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
log "Nginx configured"

header "Step 11: Firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
log "Firewall configured"

# ── Final Summary ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ArchiveVault Setup Complete!                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  API URL       : ${BLUE}http://${SERVER_DOMAIN}/api/v1${NC}"
echo -e "  API Docs      : ${BLUE}http://${SERVER_DOMAIN}/docs${NC}"
echo -e "  Health Check  : ${BLUE}http://${SERVER_DOMAIN}/health${NC}"
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
echo -e "${YELLOW}  ► Save the Indexer Token — paste it into the indexer's config.json${NC}"
echo -e "${YELLOW}  ► Save DB credentials securely${NC}"
echo ""
echo -e "  Logs          : $LOG_DIR"
echo -e "  App directory : $APP_DIR"
echo ""
