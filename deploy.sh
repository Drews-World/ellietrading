#!/usr/bin/env bash
# =============================================================================
# deploy.sh — ELLIE Trading initial server setup
# Target: Ubuntu 24.04 (fresh DigitalOcean droplet), run as root
#
# Usage:
#   chmod +x deploy.sh
#   sudo ./deploy.sh
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

[[ $EUID -eq 0 ]] || error "Run this script as root (sudo ./deploy.sh)."

APP_DIR="/home/ellie/app"
VENV_DIR="${APP_DIR}/.venv"
REPO_URL="https://github.com/Drews-World/ellietrading.git"

# =============================================================================
# 1. System update
# =============================================================================
info "Updating system packages…"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# =============================================================================
# 2. Install system dependencies
# =============================================================================
info "Installing system dependencies…"
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    curl \
    ca-certificates \
    build-essential

# =============================================================================
# 3. Install Node 20 via NodeSource
# =============================================================================
info "Installing Node.js 20…"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
node --version
npm --version

# =============================================================================
# 4. Create non-root user: ellie
# =============================================================================
if id "ellie" &>/dev/null; then
    info "User 'ellie' already exists — skipping creation."
else
    info "Creating user 'ellie'…"
    useradd --create-home --home-dir /home/ellie --shell /bin/bash ellie
fi

# =============================================================================
# 5. Clone repository
# =============================================================================
info "Cloning repository to ${APP_DIR}…"
if [[ -d "${APP_DIR}/.git" ]]; then
    warn "Repository already cloned. Pulling latest…"
    sudo -u ellie git -C "${APP_DIR}" pull
else
    sudo -u ellie git clone "${REPO_URL}" "${APP_DIR}"
fi

# =============================================================================
# 6. Create .env placeholder
# =============================================================================
info "Creating .env placeholder…"
cat > "${APP_DIR}/.env" <<'ENV'
# =============================================================================
# ELLIE Trading — environment variables
# Fill in all values before starting the service.
# =============================================================================

# ── Alpaca ────────────────────────────────────────────────────────────────────
APCA_API_KEY_ID=
APCA_API_SECRET_KEY=
# Use paper-api for paper trading, api for live:
APCA_BASE_URL=https://paper-api.alpaca.markets

# ── OpenAI / LLM ─────────────────────────────────────────────────────────────
OPENAI_API_KEY=

# ── Optional: other providers ─────────────────────────────────────────────────
# ANTHROPIC_API_KEY=
# GOOGLE_API_KEY=
# FINNHUB_API_KEY=
# POLYGON_API_KEY=

# ── App settings ──────────────────────────────────────────────────────────────
# SECRET_KEY=changeme
ENV

chown ellie:ellie "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"
info ".env created at ${APP_DIR}/.env — fill in your API keys."

# =============================================================================
# 7. Python virtual environment + dependencies
# =============================================================================
info "Setting up Python virtual environment…"
sudo -u ellie python3.12 -m venv "${VENV_DIR}"

info "Installing Python dependencies…"
sudo -u ellie "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u ellie "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" alpaca-py

# =============================================================================
# 8. Build React frontend
# =============================================================================
info "Building React frontend…"
sudo -u ellie bash -c "cd ${APP_DIR}/web && npm install && npm run build"

# =============================================================================
# 9. Configure nginx
# =============================================================================
info "Writing nginx configuration…"

# Remove default site if present
rm -f /etc/nginx/sites-enabled/default

cat > /etc/nginx/sites-available/ellie <<'NGINX'
# =============================================================================
# ELLIE Trading — nginx configuration
# Replace _ with your domain once DNS is set up, e.g.:
#   server_name ellie.example.com;
# Then run: sudo certbot --nginx -d ellie.example.com
# =============================================================================

# Redirect HTTP → HTTPS (uncomment after certbot has run)
# server {
#     listen 80;
#     server_name ellie.example.com;
#     return 301 https://$host$request_uri;
# }

server {
    listen 80;
    # Replace _ with your domain once DNS is set up
    server_name _;

    # ── Gzip compression ───────────────────────────────────────────────────
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/atom+xml image/svg+xml;

    # ── Security headers ───────────────────────────────────────────────────
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # ── React static frontend ──────────────────────────────────────────────
    root /home/ellie/app/web/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache hashed static assets aggressively
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ── API proxy — FastAPI backend on localhost:8000 ──────────────────────
    location ~ ^/(analyze|portfolio|settings|market-data|discover|monitor|scout|run|alpaca|health) {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Required for SSE (Server-Sent Events) streaming
        proxy_set_header   Connection "";
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3600s;

        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/ellie /etc/nginx/sites-enabled/ellie

nginx -t || error "nginx config test failed — check /etc/nginx/sites-available/ellie"
systemctl enable nginx
systemctl restart nginx
info "nginx configured and restarted."

# =============================================================================
# 10. systemd service
# =============================================================================
info "Creating systemd service…"

cat > /etc/systemd/system/ellie.service <<SERVICE
[Unit]
Description=ELLIE Trading — FastAPI backend
After=network.target

[Service]
Type=simple
User=ellie
Group=ellie
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

# Give the process time to shut down cleanly
TimeoutStopSec=30

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

# =============================================================================
# 11. Enable and start the service
# =============================================================================
info "Enabling and starting ellie.service…"
systemctl daemon-reload
systemctl enable ellie.service
systemctl start ellie.service

# Wait a moment and check the service is actually running
sleep 3
if systemctl is-active --quiet ellie.service; then
    info "ellie.service is running."
else
    warn "ellie.service may not have started — check: journalctl -u ellie -n 50"
fi

# =============================================================================
# 12. Done — final instructions
# =============================================================================
echo ""
echo "======================================================================"
echo " ELLIE Trading is deployed!"
echo "======================================================================"
echo ""
echo " Next steps:"
echo ""
echo "  1. Fill in your API keys:"
echo "       sudo nano ${APP_DIR}/.env"
echo ""
echo "  2. Restart the service after editing .env:"
echo "       sudo systemctl restart ellie"
echo ""
echo "  3. Point your domain DNS A record to this server's IP, then run:"
echo "       sudo certbot --nginx -d your-domain.com"
echo "     and update server_name in /etc/nginx/sites-available/ellie"
echo ""
echo "  4. View live logs:"
echo "       sudo journalctl -u ellie -f"
echo ""
echo " Now fill in ${APP_DIR}/.env with your API keys, then:"
echo "   sudo systemctl restart ellie"
echo "======================================================================"
