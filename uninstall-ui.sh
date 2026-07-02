#!/bin/bash
# ============================================================
#  ArchiveVault UI — Uninstall Script (v2)
#  Removes everything deploy.sh created, for a clean reinstall test.
#  Run as: sudo bash uninstall-ui.sh
#
#  NOTE: The API URL / company name configured via the Setup screen
#  live in each visiting BROWSER's localStorage, not on this server.
#  This script can't clear that — see the printed note at the end for
#  how to reset it per-browser if you want a fully clean re-test.
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

if [ "$EUID" -ne 0 ]; then error "Please run as root: sudo bash uninstall-ui.sh"; fi

WEB_ROOT="/var/www/archivault-ui"

header "ArchiveVault UI — Uninstall"
echo ""
warn "This will PERMANENTLY remove:"
echo "  • $WEB_ROOT (built static files)"
echo "  • Nginx site config for archivault-ui"
echo ""
warn "Node.js and nginx itself are NOT removed (only the archivault-ui site)."
warn "Your git clone / source directory is also left untouched — only the"
warn "DEPLOYED build output and nginx config are removed."
echo ""

read -p "Type 'yes' to confirm you want to proceed: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted. Nothing was changed."
    exit 0
fi

header "Step 1: Nginx Config"
if [ -f /etc/nginx/sites-enabled/archivault-ui ] || [ -f /etc/nginx/sites-available/archivault-ui ]; then
    UI_PORT=$(grep -oP 'listen \K[0-9]+' /etc/nginx/sites-available/archivault-ui 2>/dev/null | head -1)
    rm -f /etc/nginx/sites-enabled/archivault-ui
    rm -f /etc/nginx/sites-available/archivault-ui
    if command -v nginx &>/dev/null && systemctl is-active --quiet nginx; then
        nginx -t 2>/dev/null && systemctl reload nginx || warn "nginx reload failed — check remaining config manually"
    fi
    log "Nginx site config removed"
else
    warn "No archivault-ui nginx config found — skipping"
fi

header "Step 2: Deployed Files"
if [ -d "$WEB_ROOT" ]; then
    rm -rf "$WEB_ROOT"
    log "$WEB_ROOT removed"
else
    warn "$WEB_ROOT not found — skipping"
fi

header "Step 3: Firewall Rule (optional)"
if command -v ufw &>/dev/null && [ -n "$UI_PORT" ]; then
    read -p "Remove the ufw rule for port ${UI_PORT}/tcp? [y/N]: " REMOVE_FW
    if [[ "$REMOVE_FW" =~ ^[Yy]$ ]]; then
        ufw delete allow "${UI_PORT}/tcp" 2>/dev/null || warn "No matching ufw rule for ${UI_PORT}/tcp"
        log "ufw rule for ${UI_PORT}/tcp removed (if it existed)"
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        ArchiveVault UI Uninstall Complete            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Not removed on purpose (source/tooling, not deployment artifacts):"
echo "  • The git clone / source directory this script was run from"
echo "  • node_modules (delete manually with: rm -rf node_modules dist)"
echo "  • Node.js and nginx themselves"
echo ""
echo -e "${YELLOW}IMPORTANT — browser-side state:${NC}"
echo "  The API URL / company name from the Setup screen are stored in"
echo "  each browser's localStorage, not on this server. To fully reset"
echo "  a test browser before reinstalling:"
echo "    • Open DevTools -> Application -> Local Storage -> clear the"
echo "      site's entries, OR"
echo "    • Visit the site in a fresh Incognito/Private window"
echo ""
echo "Re-run 'sudo bash deploy.sh' from the source directory for a clean install."
echo ""
