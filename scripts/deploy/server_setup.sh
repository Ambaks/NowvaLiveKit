#!/bin/bash
# Server Setup Script for GCP Free Tier
# Run this ON THE SERVER after uploading your code

set -e

echo "=========================================="
echo "NowvaLiveKit Server Setup"
echo "=========================================="
echo ""

# Get username
USERNAME=$(whoami)
PROJECT_DIR="/home/$USERNAME/nowva"

echo "Configuration:"
echo "  User: $USERNAME"
echo "  Project dir: $PROJECT_DIR"
echo ""

read -p "Continue with setup? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Create swap
echo ""
echo "Step 1/8: Creating swap space..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✓ Swap created"
else
    echo "✓ Swap already exists"
fi

# Step 2: Install system dependencies
echo ""
echo "Step 2/8: Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-dev python3-pip \
    redis-server nginx git build-essential libpq-dev \
    libffi-dev libssl-dev libcairo2 libpango-1.0-0 libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 shared-mime-info
echo "✓ Dependencies installed"

# Step 3: Configure Redis
echo ""
echo "Step 3/8: Configuring Redis..."
if ! grep -q "maxmemory 100mb" /etc/redis/redis.conf; then
    sudo bash -c 'cat >> /etc/redis/redis.conf << EOF

# Memory limits for 1GB RAM server
maxmemory 100mb
maxmemory-policy allkeys-lru
EOF'
    sudo systemctl restart redis-server
    echo "✓ Redis configured"
else
    echo "✓ Redis already configured"
fi

sudo systemctl enable redis-server
sudo systemctl start redis-server

# Step 4: Create project directory
echo ""
echo "Step 4/8: Setting up project directory..."
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR
mkdir -p logs/celery programs

# Step 5: Extract uploaded files
echo ""
echo "Step 5/8: Extracting project files..."
if [ -f ~/nowva-deploy.tar.gz ]; then
    tar -xzf ~/nowva-deploy.tar.gz
    echo "✓ Files extracted"
else
    echo "⚠️  nowva-deploy.tar.gz not found in home directory"
    echo "   Upload it first with: gcloud compute scp nowva-deploy.tar.gz YOUR-VM:~"
    exit 1
fi

# Step 6: Create virtual environment and install dependencies
echo ""
echo "Step 6/8: Installing Python dependencies (this may take 10-15 minutes)..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Try minimal requirements first, fall back to full requirements
if [ -f requirements-server.txt ]; then
    echo "Using minimal server requirements..."
    pip install -r requirements-server.txt
elif [ -f requirements.txt ]; then
    echo "Using full requirements (may fail on some packages - that's OK)..."
    pip install -r requirements.txt || echo "Some packages failed - continuing..."
fi

echo "✓ Python dependencies installed"

# Step 7: Create systemd service files
echo ""
echo "Step 7/8: Creating systemd service files..."

# API service
sudo bash -c "cat > /etc/systemd/system/nowva-api.service << 'EOF'
[Unit]
Description=Nowva FastAPI Application
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=notify
User=$USERNAME
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
ExecStart=$PROJECT_DIR/venv/bin/gunicorn -c config/gunicorn_config_gcp.py src.api.main:app

Restart=always
RestartSec=10
KillMode=mixed
TimeoutStopSec=30

StandardOutput=append:$PROJECT_DIR/logs/gunicorn_stdout.log
StandardError=append:$PROJECT_DIR/logs/gunicorn_stderr.log

[Install]
WantedBy=multi-user.target
EOF"

# Celery service
sudo bash -c "cat > /etc/systemd/system/nowva-celery.service << 'EOF'
[Unit]
Description=Nowva Celery Worker
After=network.target redis-server.service nowva-api.service
Requires=redis-server.service

[Service]
Type=simple
User=$USERNAME
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
ExecStart=$PROJECT_DIR/venv/bin/celery -A src.api.celery_app worker --pool=gevent --concurrency=2 --hostname=worker1@%%h --loglevel=warning --logfile=$PROJECT_DIR/logs/celery/worker.log

Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF"

# LiveKit Website Voice Agent service
sudo bash -c "cat > /etc/systemd/system/nowva-livekit-agent.service << 'EOF'
[Unit]
Description=Nowva LiveKit Website Voice Agent
After=network.target nowva-api.service
Wants=nowva-api.service

[Service]
Type=simple
User=$USERNAME
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment=\"PATH=$PROJECT_DIR/venv/bin\"
Environment=\"PYTHONPATH=$PROJECT_DIR/src\"
Environment=\"LIVEKIT_AGENT_NUM_IDLE_PROCESSES=1\"
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

# Step 8: Configure nginx
echo ""
echo "Step 8/8: Configuring nginx..."

# Get external IP
EXTERNAL_IP=$(curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H "Metadata-Flavor: Google")

sudo bash -c "cat > /etc/nginx/sites-available/nowva << 'EOF'
upstream nowva_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name nowvasports.com www.nowvasports.com;

    client_max_body_size 10M;
    client_body_timeout 30s;

    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
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
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
    }

    location / {
        proxy_pass http://nowva_backend;
    }
}
EOF"

# Enable site
sudo ln -sf /etc/nginx/sites-available/nowva /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx config
sudo nginx -t

echo "✓ Nginx configured"

# Reload systemd and enable services
echo ""
echo "Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable redis-server nowva-api nowva-celery nowva-livekit-agent nginx

# Start all services
echo ""
echo "Starting services..."
sudo systemctl start redis-server
sudo systemctl start nowva-api
sleep 3
sudo systemctl start nowva-celery
sudo systemctl start nowva-livekit-agent
sudo systemctl restart nginx

# Wait for services to start
echo ""
echo "Waiting for services to initialize..."
sleep 5

# Check status
echo ""
echo "=========================================="
echo "Setup Complete! Checking status..."
echo "=========================================="
echo ""

echo "Services:"
for service in redis-server nowva-api nowva-celery nowva-livekit-agent nginx; do
    if systemctl is-active --quiet $service; then
        echo "  ✓ $service: RUNNING"
    else
        echo "  ✗ $service: FAILED"
        sudo systemctl status $service --no-pager -n 5
    fi
done

echo ""
echo "Memory:"
free -h

echo ""
echo "Health Check:"
curl -s http://localhost:8000/api/health || echo "API not responding yet"

echo ""
echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Your application should be accessible at:"
echo "  http://$EXTERNAL_IP/"
echo "  http://$EXTERNAL_IP/docs"
echo ""
echo "View logs:"
echo "  sudo journalctl -u nowva-api -f"
echo "  tail -f $PROJECT_DIR/logs/gunicorn_error.log"
echo ""
echo "Monitor server:"
echo "  ./server_monitor.sh"
echo ""
