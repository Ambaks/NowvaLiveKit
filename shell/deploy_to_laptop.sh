#!/bin/bash
# ==========================================================================
# NowvaLiveKit - Deploy to Linux Laptop (Fedora)
# Master script: handles first-time setup AND redeployment
# Run this from your LOCAL machine (Mac)
#
# Usage:
#   First time:  ./shell/deploy_to_laptop.sh --setup
#   Redeploy:    ./shell/deploy_to_laptop.sh
# ==========================================================================

set -e

# ==========================================================================
# CONFIGURATION — Edit these
# ==========================================================================
LAPTOP_USER="ambaks"                          # SSH username on the laptop
LAPTOP_HOST="100.120.236.20"                              # Tailscale IP or hostname (set after Tailscale install)
REMOTE_DIR="/home/$LAPTOP_USER/nowva"       # Project directory on laptop
# ==========================================================================

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse flags
SETUP=false
if [[ "$1" == "--setup" ]]; then
    SETUP=true
fi

# Validate config
if [[ -z "$LAPTOP_HOST" ]]; then
    echo -e "${RED}ERROR: Set LAPTOP_HOST in this script first (Tailscale IP or hostname)${NC}"
    echo "  1. Install Tailscale on the laptop: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up"
    echo "  2. Get the IP: tailscale ip -4"
    echo "  3. Set LAPTOP_HOST in this script"
    exit 1
fi

SSH_TARGET="$LAPTOP_USER@$LAPTOP_HOST"

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}NowvaLiveKit - Deploy to Laptop (Fedora)${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo "  Target:     $SSH_TARGET"
echo "  Remote dir:  $REMOTE_DIR"
if $SETUP; then
    echo -e "  Mode:        ${YELLOW}FIRST-TIME SETUP + DEPLOY${NC}"
else
    echo "  Mode:        Redeploy (code update only)"
fi
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# ==========================================================================
# PHASE 1: Build locally (runs on Mac)
# ==========================================================================
echo ""
echo -e "${BLUE}=== Phase 1: Building locally ===${NC}"

echo "Building frontend..."
cd "$(dirname "$0")/.."
cd frontend_demo
npm run build
cd ..

echo "Creating deployment archive..."
tar --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='.DS_Store' \
    --exclude='venv' \
    --exclude='*.db' \
    -czf nowva-deploy.tar.gz \
    src/ \
    frontend_demo/dist/ \
    gunicorn_config.py \
    requirements-server.txt \
    requirements.txt \
    .env \
    shell/server_monitor.sh \
    models/ \
    config/ \
    programs/

echo -e "${GREEN}Archive size: $(du -h nowva-deploy.tar.gz | cut -f1)${NC}"

# ==========================================================================
# PHASE 2: Upload to laptop
# ==========================================================================
echo ""
echo -e "${BLUE}=== Phase 2: Uploading to laptop ===${NC}"

scp nowva-deploy.tar.gz "$SSH_TARGET:~/"
echo -e "${GREEN}✓ Upload complete${NC}"

# ==========================================================================
# PHASE 3: First-time server setup (only with --setup)
# ==========================================================================
if $SETUP; then
echo ""
echo -e "${BLUE}=== Phase 3: First-time server setup ===${NC}"

# Write setup script to temp file, upload it, then run with -t for sudo
SETUP_TMP=$(mktemp /tmp/nowva_setup.XXXXXX.sh)
cat > "$SETUP_TMP" << 'SETUP_SCRIPT'
#!/bin/bash
set -e

USERNAME="$1"
PROJECT_DIR="$2"

echo "==========================================="
echo "Server Setup — Fedora"
echo "==========================================="

# --- Disable sleep/suspend ---
echo ""
echo "[1/8] Disabling sleep/suspend..."
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
echo "✓ Sleep disabled"

# --- Install system dependencies ---
echo ""
echo "[2/8] Installing system dependencies..."
sudo dnf install -y \
    python3 python3-devel python3-pip \
    redis nginx git gcc gcc-c++ make \
    libpq-devel libffi-devel openssl-devel \
    cairo pango gdk-pixbuf2 \
    shared-mime-info \
    openssh-server
sudo systemctl enable --now sshd
echo "✓ Dependencies installed"

# --- Install Node.js 20 (for any server-side needs) ---
echo ""
echo "[3/8] Installing Node.js..."
if ! command -v node &> /dev/null; then
    sudo dnf install -y nodejs
fi
echo "✓ Node.js $(node --version) installed"

# --- Configure Redis ---
echo ""
echo "[4/8] Configuring Redis..."
# Fedora redis config is at /etc/redis/redis.conf or /etc/redis.conf
REDIS_CONF="/etc/redis/redis.conf"
if [ ! -f "$REDIS_CONF" ]; then
    REDIS_CONF="/etc/redis.conf"
fi

if ! grep -q "maxmemory 512mb" "$REDIS_CONF" 2>/dev/null; then
    sudo bash -c "cat >> $REDIS_CONF << EOF

# Memory limits for 8GB RAM laptop
maxmemory 512mb
maxmemory-policy allkeys-lru
EOF"
    echo "✓ Redis configured (512mb max)"
else
    echo "✓ Redis already configured"
fi

sudo systemctl enable --now redis
echo "✓ Redis running"

# --- Create project directory ---
echo ""
echo "[5/8] Setting up project directory..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
mkdir -p logs/celery programs

# --- Extract uploaded files ---
echo ""
echo "[6/8] Extracting project files..."
if [ -f ~/nowva-deploy.tar.gz ]; then
    tar -xzf ~/nowva-deploy.tar.gz -C "$PROJECT_DIR"
    echo "✓ Files extracted"
else
    echo "ERROR: nowva-deploy.tar.gz not found"
    exit 1
fi

# --- Python virtual environment ---
echo ""
echo "[7/8] Installing Python dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 8GB RAM — can install full requirements, but server requirements are sufficient
if [ -f requirements-server.txt ]; then
    echo "Installing server requirements..."
    pip install -r requirements-server.txt
elif [ -f requirements.txt ]; then
    echo "Installing full requirements..."
    pip install -r requirements.txt || echo "Some packages failed — continuing..."
fi
echo "✓ Python dependencies installed"

# --- Create systemd services ---
echo ""
echo "[8/8] Creating systemd services..."

# Gunicorn API service
sudo bash -c "cat > /etc/systemd/system/nowva-api.service << EOF
[Unit]
Description=Nowva FastAPI Application
After=network.target redis.service
Wants=redis.service

[Service]
Type=notify
User=$USERNAME
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/gunicorn -c gunicorn_config.py src.api.main:app

Restart=always
RestartSec=10
KillMode=mixed
TimeoutStopSec=30

StandardOutput=append:$PROJECT_DIR/logs/gunicorn_stdout.log
StandardError=append:$PROJECT_DIR/logs/gunicorn_stderr.log

[Install]
WantedBy=multi-user.target
EOF"

# Celery worker service (more resources than GCP — 3 workers, concurrency 4 each)
sudo bash -c "cat > /etc/systemd/system/nowva-celery.service << EOF
[Unit]
Description=Nowva Celery Worker
After=network.target redis.service nowva-api.service
Requires=redis.service

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/celery -A src.api.celery_app worker --pool=gevent --concurrency=4 --hostname=worker1@%%h --loglevel=info --logfile=$PROJECT_DIR/logs/celery/worker.log

Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF"

# LiveKit Website Voice Agent service
sudo bash -c "cat > /etc/systemd/system/nowva-livekit-agent.service << EOF
[Unit]
Description=Nowva LiveKit Website Voice Agent
After=network.target nowva-api.service
Wants=nowva-api.service

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
EnvironmentFile=$PROJECT_DIR/.env
Environment=\"LIVEKIT_AGENT_NUM_IDLE_PROCESSES=2\"
ExecStart=$PROJECT_DIR/venv/bin/python3 src/agents/website_voice_agent.py start

Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30

StandardOutput=append:$PROJECT_DIR/logs/livekit_agent_stdout.log
StandardError=append:$PROJECT_DIR/logs/livekit_agent_stderr.log

[Install]
WantedBy=multi-user.target
EOF"

echo "✓ Systemd services created"

# --- Configure Nginx ---
echo ""
echo "Configuring Nginx..."

sudo tee /etc/nginx/conf.d/nowva.conf > /dev/null << 'NGINXEOF'
upstream nowva_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name nowvasports.com www.nowvasports.com;

    client_max_body_size 10M;
    client_body_timeout 30s;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;

    location /api/ {
        proxy_pass http://nowva_backend;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }

    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://nowva_backend;
    }

    location /ws {
        proxy_pass http://nowva_backend;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://nowva_backend;
    }
}
NGINXEOF

# Fedora: remove default welcome page if it exists
sudo rm -f /etc/nginx/conf.d/default.conf
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Open firewall ports
if command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
    echo "✓ Firewall ports opened"
fi

sudo nginx -t
echo "✓ Nginx configured"

# --- Install Cloudflare Tunnel ---
echo ""
echo "Installing Cloudflare Tunnel..."
if ! command -v cloudflared &> /dev/null; then
    sudo dnf install -y https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm || {
        echo "RPM install failed, trying binary..."
        curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
        sudo install /tmp/cloudflared /usr/local/bin/cloudflared
    }
fi
echo "✓ cloudflared installed"
echo ""
echo "==========================================="
echo "⚠️  MANUAL STEP: Set up Cloudflare Tunnel"
echo "==========================================="
echo ""
echo "SSH into the laptop and run:"
echo "  cloudflared tunnel login"
echo "  cloudflared tunnel create nowva"
echo ""
echo "Then create ~/.cloudflared/config.yml:"
echo "  tunnel: nowva"
echo "  credentials-file: /home/$USERNAME/.cloudflared/<TUNNEL_ID>.json"
echo ""
echo "  ingress:"
echo "    - hostname: nowvasports.com"
echo "      service: http://localhost:80"
echo "    - hostname: www.nowvasports.com"
echo "      service: http://localhost:80"
echo "    - service: http_status:404"
echo ""
echo "Then run:"
echo "  cloudflared tunnel route dns nowva nowvasports.com"
echo "  cloudflared tunnel route dns nowva www.nowvasports.com"
echo "  sudo cloudflared service install"
echo "  sudo systemctl enable --now cloudflared"
echo "==========================================="

# --- Enable and start all services ---
echo ""
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable redis nginx nowva-api nowva-celery nowva-livekit-agent

sudo systemctl start redis
sudo systemctl start nginx
sudo systemctl start nowva-api
sleep 3
sudo systemctl start nowva-celery
sudo systemctl start nowva-livekit-agent

sleep 5

echo ""
echo "==========================================="
echo "Service Status:"
echo "==========================================="
for service in redis nginx nowva-api nowva-celery nowva-livekit-agent; do
    if systemctl is-active --quiet $service; then
        echo "  ✓ $service: RUNNING"
    else
        echo "  ✗ $service: FAILED"
        sudo systemctl status $service --no-pager -n 3
    fi
done

echo ""
echo "Memory:"
free -h

echo ""
echo "Health Check:"
curl -s http://localhost:8000/api/health || echo "API not responding yet — check logs"

echo ""
echo "==========================================="
echo "✓ First-time setup complete!"
echo "==========================================="

SETUP_SCRIPT

scp "$SETUP_TMP" "$SSH_TARGET:/tmp/nowva_setup.sh"
ssh -t "$SSH_TARGET" "bash /tmp/nowva_setup.sh '$LAPTOP_USER' '$REMOTE_DIR'"
rm -f "$SETUP_TMP"

fi  # end --setup block


# ==========================================================================
# PHASE 4: Deploy code (runs every time — setup or redeploy)
# ==========================================================================
if ! $SETUP; then
echo ""
echo -e "${BLUE}=== Deploying code update ===${NC}"

DEPLOY_TMP=$(mktemp /tmp/nowva_deploy.XXXXXX.sh)
cat > "$DEPLOY_TMP" << 'DEPLOY_SCRIPT'
#!/bin/bash
set -e

PROJECT_DIR="$1"
cd "$PROJECT_DIR"

echo "Extracting archive..."
tar -xzf ~/nowva-deploy.tar.gz -C "$PROJECT_DIR"

echo "Activating venv..."
source venv/bin/activate

echo "Checking for new dependencies..."
pip install -q -r requirements-server.txt 2>/dev/null

echo "Restarting services..."
sudo systemctl restart nowva-api
sudo systemctl restart nowva-celery
sudo systemctl restart nowva-livekit-agent

echo "Waiting for services..."
sleep 5

echo "Checking service status..."
for service in redis nginx nowva-api nowva-celery nowva-livekit-agent; do
    if systemctl is-active --quiet $service; then
        echo "  ✓ $service: RUNNING"
    else
        echo "  ✗ $service: FAILED"
    fi
done

echo ""
echo "Health check:"
curl -s http://localhost:8000/api/health || echo "API not responding — check logs"

echo ""
echo "✓ Deployment complete!"
DEPLOY_SCRIPT

scp "$DEPLOY_TMP" "$SSH_TARGET:/tmp/nowva_deploy.sh"
ssh -t "$SSH_TARGET" "bash /tmp/nowva_deploy.sh '$REMOTE_DIR'"
rm -f "$DEPLOY_TMP"

fi  # end deploy block

# ==========================================================================
# Cleanup
# ==========================================================================
rm -f nowva-deploy.tar.gz

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}✓ Done!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Your app is live at: https://nowvasports.com"
echo ""
echo "Useful commands:"
echo "  ssh $SSH_TARGET                                    # SSH into laptop"
echo "  ssh $SSH_TARGET 'sudo journalctl -u nowva-api -f'  # API logs"
echo "  ssh $SSH_TARGET 'bash $REMOTE_DIR/shell/server_monitor.sh'  # Full status"
echo ""
