#!/usr/bin/env bash
# =============================================================================
# update.sh — ELLIE Trading hot-update script
# Pulls latest code, rebuilds the frontend, and restarts the service.
# Run from any machine that has SSH access to the server (or on the server).
#
# Usage (on the server as root or sudo):
#   sudo ./update.sh
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[ELLIE]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Run this script as root (sudo ./update.sh)."

APP_DIR="/home/ellie/app"
VENV_DIR="${APP_DIR}/.venv"

# =============================================================================
# 1. Pull latest code
# =============================================================================
info "Pulling latest code from git…"
sudo -u ellie git -C "${APP_DIR}" fetch --all
sudo -u ellie git -C "${APP_DIR}" reset --hard origin/main
info "Updated to: $(sudo -u ellie git -C "${APP_DIR}" log -1 --oneline)"

# =============================================================================
# 2. Install any new Python dependencies
# =============================================================================
info "Syncing Python dependencies…"
sudo -u ellie "${VENV_DIR}/bin/pip" install --upgrade pip --quiet
sudo -u ellie "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" alpaca-py --quiet

# =============================================================================
# 3. Rebuild React frontend
# =============================================================================
info "Rebuilding React frontend…"
sudo -u ellie bash -c "cd ${APP_DIR}/web && npm install --silent && npm run build"

# =============================================================================
# 4. Reload nginx (in case static files or nginx config changed)
# =============================================================================
info "Reloading nginx…"
nginx -t && systemctl reload nginx

# =============================================================================
# 5. Restart the FastAPI service
# =============================================================================
info "Restarting ellie.service…"
systemctl restart ellie.service

# Wait and verify
sleep 3
if systemctl is-active --quiet ellie.service; then
    info "ellie.service restarted successfully."
else
    error "ellie.service failed to restart. Check: journalctl -u ellie -n 50"
fi

# =============================================================================
# Done
# =============================================================================
echo ""
echo "======================================================================"
echo " Update complete!"
echo " Live logs: sudo journalctl -u ellie -f"
echo "======================================================================"
