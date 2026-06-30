#!/bin/bash
# ============================================================
#  ArchiveVault — Upgrade Script
#  Run as: sudo bash upgrade.sh
#  Safe to run multiple times — never loses data
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
header() { echo -e "\n${BLUE}══════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}══════════════════════════════════════${NC}"; }

if [ "$EUID" -ne 0 ]; then echo "Please run as root: sudo bash upgrade.sh"; exit 1; fi

APP_DIR="/opt/archivault"
APP_USER="archivault"
VENV_DIR="$APP_DIR/venv"

header "ArchiveVault Upgrade"

header "Step 1: Pull Latest Code"
cd "$APP_DIR"
git pull origin main
log "Code updated"

header "Step 2: Install New Dependencies"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
log "Dependencies updated"

header "Step 3: Run Database Migrations"
# Alembic only runs NEW migrations — existing data is never touched
sudo -u "$APP_USER" "$VENV_DIR/bin/alembic" upgrade head
log "Database schema up to date"

header "Step 4: Restart Service"
systemctl restart archivault
sleep 2
if systemctl is-active --quiet archivault; then
    log "Service restarted successfully"
else
    echo -e "${RED}Service failed to restart. Check logs:${NC}"
    journalctl -u archivault -n 30 --no-pager
    exit 1
fi

header "Step 5: Reload Nginx"
nginx -t && systemctl reload nginx
log "Nginx reloaded"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ArchiveVault Upgrade Complete    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Health: $(curl -s http://localhost/health)"
echo ""
