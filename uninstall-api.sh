#!/bin/bash
# ============================================================
#  ArchiveVault API — Uninstall Script (v2)
#  Removes everything setup.sh created, for a clean reinstall test.
#  Run as: sudo bash uninstall-api.sh
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

if [ "$EUID" -ne 0 ]; then error "Please run as root: sudo bash uninstall-api.sh"; fi

APP_DIR="/opt/archivault"
APP_USER="archivault"
LOG_DIR="/var/log/archivault"

header "ArchiveVault API — Uninstall"
echo ""
warn "This will PERMANENTLY remove:"
echo "  • The archivault systemd service"
echo "  • $APP_DIR (app code, venv, .env with credentials)"
echo "  • $LOG_DIR"
echo "  • Nginx site config (if present)"
echo "  • The 'archivault' PostgreSQL database and role"
echo "  • The 'archivault' system user"
echo ""
warn "PostgreSQL itself, nginx itself, and other system packages are NOT removed"
warn "(only the archivault-specific pieces), since other things may depend on them."
echo ""

read -p "Type 'yes' to confirm you want to proceed: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted. Nothing was changed."
    exit 0
fi

echo ""
read -p "Back up the database first with pg_dump before dropping it? [Y/n]: " DO_BACKUP
DO_BACKUP="${DO_BACKUP:-Y}"

header "Step 1: Stop & Disable Service"
if systemctl list-unit-files | grep -q '^archivault.service'; then
    systemctl stop archivault 2>/dev/null || true
    systemctl disable archivault 2>/dev/null || true
    rm -f /etc/systemd/system/archivault.service
    systemctl daemon-reload
    log "systemd service removed"
else
    warn "archivault.service not found — skipping"
fi

header "Step 2: Database Backup & Removal"
if command -v psql &>/dev/null && sudo -u postgres psql -lqt 2>/dev/null | cut -d '|' -f1 | grep -qw archivault; then
    if [[ "$DO_BACKUP" =~ ^[Yy]$ ]]; then
        BACKUP_FILE="/root/archivault_backup_$(date +%Y%m%d_%H%M%S).sql"
        sudo -u postgres pg_dump archivault > "$BACKUP_FILE"
        log "Database backed up to $BACKUP_FILE"
    fi
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS archivault;" 2>/dev/null || true
    sudo -u postgres psql -c "DROP USER IF EXISTS archivault;" 2>/dev/null || true
    log "Database and DB role dropped"
else
    warn "No 'archivault' database found — skipping"
fi

header "Step 3: Nginx Config"
if [ -f /etc/nginx/sites-enabled/archivault-api ] || [ -f /etc/nginx/sites-available/archivault-api ]; then
    rm -f /etc/nginx/sites-enabled/archivault-api
    rm -f /etc/nginx/sites-available/archivault-api
    if command -v nginx &>/dev/null && systemctl is-active --quiet nginx; then
        nginx -t 2>/dev/null && systemctl reload nginx || warn "nginx reload failed — check remaining config manually"
    fi
    log "Nginx site config removed"
else
    warn "No archivault-api nginx config found — skipping"
fi

header "Step 4: Application Files"
if [ -d "$APP_DIR" ]; then
    rm -rf "$APP_DIR"
    log "$APP_DIR removed"
else
    warn "$APP_DIR not found — skipping"
fi

if [ -d "$LOG_DIR" ]; then
    rm -rf "$LOG_DIR"
    log "$LOG_DIR removed"
else
    warn "$LOG_DIR not found — skipping"
fi

header "Step 5: System User"
if id "$APP_USER" &>/dev/null; then
    userdel "$APP_USER" 2>/dev/null || warn "Could not remove user $APP_USER (may still own files elsewhere) — check manually"
    log "System user '$APP_USER' removed"
else
    warn "System user '$APP_USER' not found — skipping"
fi

header "Step 6: Firewall Rules (optional)"
if command -v ufw &>/dev/null; then
    echo ""
    read -p "Remove any ufw rules opening the API port directly (only relevant if you used direct-expose mode)? Enter the port to remove, or leave blank to skip: " REMOVE_PORT
    if [ -n "$REMOVE_PORT" ]; then
        ufw delete allow "${REMOVE_PORT}/tcp" 2>/dev/null || warn "No matching ufw rule for ${REMOVE_PORT}/tcp"
        log "ufw rule for ${REMOVE_PORT}/tcp removed (if it existed)"
    else
        warn "Skipped firewall cleanup"
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        ArchiveVault API Uninstall Complete           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Not removed (shared system packages, left intact on purpose):"
echo "  • PostgreSQL server itself"
echo "  • Nginx itself"
echo "  • Python 3.12 / build-essential / other apt packages"
echo ""
echo "You can now re-clone the repo and run setup.sh for a clean install."
echo ""
