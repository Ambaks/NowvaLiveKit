# Google Cloud Free Tier Deployment Guide
**NowvaLiveKit on e2-micro (1GB RAM, 2 vCPU)**

---

## ⚠️ CRITICAL: Memory Optimization for 1GB RAM

Your project stack normally requires ~800MB-1.2GB under load. This guide optimizes it to run reliably within 1GB RAM by:

- **Reducing Gunicorn workers**: 4 → 2 (saves ~100-200 MB)
- **Reducing Celery workers**: 3 → 1 (saves ~100-200 MB)
- **Reducing Celery concurrency**: 6 → 3 (saves ~50-100 MB)
- **Redis memory limit**: 100MB max
- **Adding swap space**: 2GB (slow but prevents OOM crashes)
- **Pre-building frontend**: No Node.js on server

**Expected memory usage:**
- Gunicorn (2 workers): ~150-250 MB
- Celery (1 worker, 3 greenlets): ~80-150 MB
- Redis: ~50-100 MB
- Nginx: ~10-20 MB
- System: ~150-200 MB
- **Total: ~440-720 MB** (leaves headroom for spikes)

---

## 📋 Prerequisites

### On Your Local Machine (Before Deploying):
1. Build the frontend:
   ```bash
   cd frontend_demo
   npm run build
   cd ..
   ```

2. Create a deployment archive:
   ```bash
   tar -czf nowva-deploy.tar.gz \
     src/ \
     frontend_demo/dist/ \
     gunicorn_config.py \
     requirements.txt \
     .env
   ```

### On Google Cloud:
1. Create e2-micro VM (Ubuntu 22.04 LTS, US region)
2. Reserve a static external IP (Free Tier eligible)
3. Configure firewall rules:
   ```
   Allow ingress: TCP 80, 443 (HTTP/HTTPS)
   Allow egress: All
   ```

---

## 🚀 DEPLOYMENT STEPS

### **Step 1: Initial Server Setup**

SSH into your VM:
```bash
gcloud compute ssh YOUR-VM-NAME --zone=YOUR-ZONE
```

Update system and install dependencies:
```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install Python 3.11 and system dependencies
sudo apt install -y \
  python3.11 \
  python3.11-venv \
  python3.11-dev \
  python3-pip \
  redis-server \
  nginx \
  git \
  build-essential \
  libpq-dev \
  libffi-dev \
  libssl-dev \
  libcairo2 \
  libpango-1.0-0 \
  libgdk-pixbuf2.0-0 \
  libffi-dev \
  shared-mime-info

# Verify installations
python3.11 --version
redis-cli --version
nginx -v
```

---

### **Step 2: Create Swap Space (CRITICAL for 1GB RAM)**

```bash
# Create 2GB swap file
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify swap
free -h
# Should show 2GB swap
```

**Why swap?** Without it, your server will crash with OOM (Out Of Memory) errors under load. With swap, it will slow down but stay online.

---

### **Step 3: Configure Redis (Memory-Optimized)**

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf
```

Add/modify these lines:
```
maxmemory 100mb
maxmemory-policy allkeys-lru
save ""
```

Restart Redis:
```bash
sudo systemctl restart redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping
# Should return: PONG
```

---

### **Step 4: Upload and Extract Your Project**

From your **local machine**, upload the archive:
```bash
gcloud compute scp nowva-deploy.tar.gz YOUR-VM-NAME:~ --zone=YOUR-ZONE
```

Back on the **server**:
```bash
# Create project directory
mkdir -p /home/$USER/nowva
cd /home/$USER/nowva

# Extract
tar -xzf ~/nowva-deploy.tar.gz

# Create required directories
mkdir -p logs/celery programs
```

---

### **Step 5: Install Python Dependencies**

```bash
cd /home/$USER/nowva

# Create virtual environment
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (this may take 10-15 minutes)
pip install -r requirements.txt

# Verify critical packages
python -c "import fastapi, celery, redis, weasyprint; print('✓ All critical packages installed')"
```

**IMPORTANT**: If you see errors about `mmpose`, `opencv`, or `torch`, **ignore them**. The program generation API doesn't need pose estimation libraries. Only install what's actually needed:

```bash
# If requirements.txt fails, install core dependencies only:
pip install fastapi uvicorn gunicorn sqlalchemy psycopg2-binary \
  celery[redis] redis gevent openai tiktoken weasyprint \
  jinja2 resend chromadb voyageai cohere anthropic python-dotenv
```

---

### **Step 6: Configure Environment Variables**

```bash
nano .env
```

Ensure these are set (copy from your local `.env`):
```bash
# Database
DATABASE_URL=postgresql://user:pass@host/db

# OpenAI
OPENAI_API_KEY=sk-...

# LiveKit
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_URL=wss://...

# Email
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@nowvasports.com

# Redis & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
USE_CELERY=true

# Program generation model (optional - use faster/cheaper model)
PROGRAM_CREATION_MODEL=claude-sonnet-4-5-20250929
```

---

### **Step 7: Create Optimized Gunicorn Config**

```bash
nano /home/$USER/nowva/gunicorn_config_gcp.py
```

Paste this **memory-optimized** configuration:
```python
"""
Gunicorn Configuration for GCP Free Tier (1GB RAM)
Optimized for e2-micro instance
"""
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 512  # Reduced from 2048

# Worker processes (2 for 1GB RAM - DO NOT INCREASE)
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 500  # Reduced from 1000
max_requests = 500  # Restart workers after 500 requests
max_requests_jitter = 25
timeout = 120
keepalive = 5

# Logging
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "warning"  # Less verbose logging

# Process naming
proc_name = "nowva_api_gcp"

# Server mechanics
daemon = False
pidfile = "logs/gunicorn.pid"
preload_app = True  # Load app before forking (saves memory)

# Worker lifecycle
graceful_timeout = 30
```

---

### **Step 8: Create systemd Service Files**

#### **8.1: Gunicorn Service**

```bash
sudo nano /etc/systemd/system/nowva-api.service
```

```ini
[Unit]
Description=Nowva FastAPI Application
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=notify
User=YOUR-USERNAME
Group=www-data
WorkingDirectory=/home/YOUR-USERNAME/nowva
Environment="PATH=/home/YOUR-USERNAME/nowva/venv/bin"
Environment="PYTHONPATH=/home/YOUR-USERNAME/nowva/src"
ExecStart=/home/YOUR-USERNAME/nowva/venv/bin/gunicorn \
  -c gunicorn_config_gcp.py \
  src.api.main:app

# Process management
Restart=always
RestartSec=10
KillMode=mixed
TimeoutStopSec=30

# Logging
StandardOutput=append:/home/YOUR-USERNAME/nowva/logs/gunicorn_stdout.log
StandardError=append:/home/YOUR-USERNAME/nowva/logs/gunicorn_stderr.log

[Install]
WantedBy=multi-user.target
```

**Replace `YOUR-USERNAME` with your actual username** (run `whoami` to check).

#### **8.2: Celery Worker Service**

```bash
sudo nano /etc/systemd/system/nowva-celery.service
```

```ini
[Unit]
Description=Nowva Celery Worker (Program Generation)
After=network.target redis-server.service nowva-api.service
Requires=redis-server.service

[Service]
Type=simple
User=YOUR-USERNAME
Group=www-data
WorkingDirectory=/home/YOUR-USERNAME/nowva
Environment="PATH=/home/YOUR-USERNAME/nowva/venv/bin"
Environment="PYTHONPATH=/home/YOUR-USERNAME/nowva/src"

# OPTIMIZED: 1 worker with 3 greenlets (not 3 workers × 6)
ExecStart=/home/YOUR-USERNAME/nowva/venv/bin/celery \
  -A src.api.celery_app worker \
  --pool=gevent \
  --concurrency=3 \
  --hostname=worker1@%%h \
  --loglevel=warning \
  --logfile=/home/YOUR-USERNAME/nowva/logs/celery/worker.log

# Process management
Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

**Replace `YOUR-USERNAME`** again.

---

### **Step 9: Configure Nginx**

```bash
sudo nano /etc/nginx/sites-available/nowva
```

```nginx
upstream nowva_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

# HTTP Server (for initial setup)
server {
    listen 80;
    server_name YOUR-EXTERNAL-IP nowvasports.com www.nowvasports.com;

    # Client settings
    client_max_body_size 10M;
    client_body_timeout 30s;

    # Proxy settings
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;

    # API endpoints
    location /api/ {
        proxy_pass http://nowva_backend;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }

    # API docs
    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://nowva_backend;
    }

    # WebSocket
    location /ws {
        proxy_pass http://nowva_backend;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Frontend
    location / {
        proxy_pass http://nowva_backend;
    }
}
```

Enable the site:
```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/nowva /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

### **Step 10: Start All Services**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable redis-server
sudo systemctl enable nowva-api
sudo systemctl enable nowva-celery
sudo systemctl enable nginx

# Start services
sudo systemctl start redis-server
sudo systemctl start nowva-api
sudo systemctl start nowva-celery
sudo systemctl start nginx

# Check status
sudo systemctl status redis-server
sudo systemctl status nowva-api
sudo systemctl status nowva-celery
sudo systemctl status nginx
```

---

### **Step 11: Verify Everything Works**

```bash
# Check memory usage
free -h

# Check service status
systemctl is-active redis-server nowva-api nowva-celery nginx

# Test Redis
redis-cli ping

# Test API
curl http://localhost:8000/api/health

# Test from outside
curl http://YOUR-EXTERNAL-IP/api/health

# Check logs
tail -f logs/gunicorn_error.log
tail -f logs/celery/worker.log

# Monitor Celery workers
source venv/bin/activate
celery -A src.api.celery_app inspect active
```

**Expected response from health check:**
```json
{"status":"healthy","timestamp":"2026-01-21T..."}
```

---

## 🔐 OPTIONAL: SSL with Let's Encrypt

Once your domain DNS points to your VM's IP:

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Stop nginx temporarily
sudo systemctl stop nginx

# Get certificate
sudo certbot certonly --standalone \
  -d nowvasports.com \
  -d www.nowvasports.com \
  --email your-email@example.com \
  --agree-tos \
  --non-interactive

# Update nginx config
sudo nano /etc/nginx/sites-available/nowva
```

Add HTTPS server block:
```nginx
server {
    listen 443 ssl http2;
    server_name nowvasports.com www.nowvasports.com;

    ssl_certificate /etc/letsencrypt/live/nowvasports.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nowvasports.com/privkey.pem;

    # Copy all location blocks from port 80 server above
    # ...
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name nowvasports.com www.nowvasports.com;
    return 301 https://$server_name$request_uri;
}
```

```bash
# Test and restart nginx
sudo nginx -t
sudo systemctl start nginx

# Auto-renew setup
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## 📊 Monitoring & Maintenance

### Check Memory Usage:
```bash
# Real-time memory monitoring
free -h
# OR
htop

# Check process memory
ps aux --sort=-%mem | head -10
```

### View Logs:
```bash
# API logs
tail -f ~/nowva/logs/gunicorn_error.log

# Celery logs
tail -f ~/nowva/logs/celery/worker.log

# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Systemd journal
sudo journalctl -u nowva-api -f
sudo journalctl -u nowva-celery -f
```

### Restart Services:
```bash
sudo systemctl restart nowva-api
sudo systemctl restart nowva-celery
sudo systemctl restart redis-server
sudo systemctl restart nginx
```

### Monitor Celery:
```bash
cd ~/nowva
source venv/bin/activate

# Active tasks
celery -A src.api.celery_app inspect active

# Worker stats
celery -A src.api.celery_app inspect stats

# Ping workers
celery -A src.api.celery_app inspect ping
```

---

## 🚨 Troubleshooting

### Service won't start:
```bash
# Check logs
sudo journalctl -u nowva-api -n 50 --no-pager
sudo journalctl -u nowva-celery -n 50 --no-pager

# Check if port is in use
sudo lsof -i :8000

# Kill rogue processes
pkill -f gunicorn
pkill -f celery
```

### Out of Memory (OOM):
```bash
# Check OOM events
sudo dmesg | grep -i "out of memory"

# If OOM happens, reduce workers further:
# Edit /etc/systemd/system/nowva-api.service
# Change workers=2 to workers=1 in gunicorn config

# OR reduce Celery concurrency:
# Edit /etc/systemd/system/nowva-celery.service
# Change --concurrency=3 to --concurrency=2
```

### Celery workers not responding:
```bash
# Check Redis
redis-cli ping

# Restart Celery
sudo systemctl restart nowva-celery

# Check logs
tail -f ~/nowva/logs/celery/worker.log
```

### nginx 502 Bad Gateway:
```bash
# Check if Gunicorn is running
sudo systemctl status nowva-api

# Check if it's listening
sudo ss -tlnp | grep :8000

# Restart API
sudo systemctl restart nowva-api
```

---

## 📈 Performance Expectations

With this optimized setup on 1GB RAM:

- **Concurrent Users**: 10-15 simultaneous users
- **Program Generations**: 3 concurrent (1 worker × 3 greenlets)
- **API Requests**: ~50-100 req/sec
- **Memory Usage**: 440-720 MB (peaks to ~900 MB under load)
- **Swap Usage**: Expect 100-300 MB swap usage during peaks

**To handle 20-30 users**, you would need to upgrade to **e2-small** (2GB RAM), which costs ~$13/month.

---

## ✅ Deployment Checklist

- [ ] VM created and SSH access working
- [ ] 2GB swap file created and enabled
- [ ] Redis installed and configured with 100MB limit
- [ ] Python 3.11 + venv created
- [ ] Dependencies installed
- [ ] `.env` file configured
- [ ] Frontend built and uploaded
- [ ] Gunicorn systemd service created
- [ ] Celery systemd service created
- [ ] Nginx configured and running
- [ ] All services started and enabled
- [ ] Health endpoint returns 200 OK
- [ ] Celery workers respond to ping
- [ ] DNS pointed to VM IP (if using custom domain)
- [ ] SSL certificate obtained (if using HTTPS)
- [ ] Logs directory writable
- [ ] Firewall allows ports 80/443

---

## 🎯 Quick Command Reference

```bash
# Start all services
sudo systemctl start redis-server nowva-api nowva-celery nginx

# Stop all services
sudo systemctl stop nowva-api nowva-celery nginx

# Restart everything
sudo systemctl restart redis-server nowva-api nowva-celery nginx

# Check status
sudo systemctl status nowva-api nowva-celery

# View logs
sudo journalctl -u nowva-api -f
tail -f ~/nowva/logs/gunicorn_error.log

# Monitor memory
watch -n 1 free -h

# Health check
curl http://localhost:8000/api/health
```

---

## 🎉 You're Live!

Once deployed:
- **Frontend**: http://YOUR-EXTERNAL-IP/ or https://nowvasports.com
- **API Docs**: http://YOUR-EXTERNAL-IP/docs
- **Health Check**: http://YOUR-EXTERNAL-IP/api/health

Your application will automatically restart if it crashes and will survive server reboots.

---

## ⚠️ IMPORTANT WARNINGS

1. **Do NOT increase worker counts** without monitoring memory
2. **Monitor swap usage** - if consistently high, reduce workers
3. **1GB RAM is tight** - expect slowdowns under load
4. **Backup your `.env`** - it contains all secrets
5. **Monitor disk space** - 20GB fills up with logs
6. **Set up log rotation** - logs can grow quickly
7. **Test before going live** - generate a test program to ensure it works

---

**For production with 20-30 concurrent users, upgrade to e2-small (2GB RAM) at minimum.**
