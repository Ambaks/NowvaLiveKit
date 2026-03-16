# Deploy nowvasports.com - Quick Guide

## ✅ Pre-Deployment Checklist

Your production services are already running:
- ✅ Redis: Running
- ✅ Celery Workers: 3 workers (18 concurrent capacity)
- ✅ Gunicorn: 4 workers
- ✅ Frontend: Built and serving

---

## 🚀 Deployment Steps

### **Step 1: Configure DNS (Do this first!)**

Go to your domain registrar for `nowvasports.com` and add:

**A Record:**
- Name: `@`
- Type: `A`
- Value: `[Your Mac's Public IP]` ← Get this from https://whatismyipaddress.com
- TTL: `3600`

**Optional CNAME for www:**
- Name: `www`
- Type: `CNAME`
- Value: `nowvasports.com`

⏰ **DNS propagation takes 5 minutes to 24 hours**

---

### **Step 2: Set Up Port Forwarding (If Behind Router)**

Log into your router and forward these ports to your Mac's local IP:
- Port `80` → Your Mac's local IP → Port `80`
- Port `443` → Your Mac's local IP → Port `443`

Get your Mac's local IP:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

---

### **Step 3: Install nginx Config**

```bash
# Copy the configuration
sudo cp nginx_production.conf /opt/homebrew/etc/nginx/servers/nowva.conf

# Test configuration
sudo nginx -t

# Start nginx
brew services start nginx
```

---

### **Step 4: Test HTTP Access (Before SSL)**

For initial testing without SSL, temporarily enable HTTP-only mode:

```bash
# Edit nginx config
nano nginx_production.conf
```

**Comment out the HTTPS server block (lines 25-100)** and **uncomment the HTTP-only block at the bottom (lines 104-115)**

Then:
```bash
# Copy updated config
sudo cp nginx_production.conf /opt/homebrew/etc/nginx/servers/nowva.conf

# Reload nginx
brew services restart nginx

# Test
curl -I http://nowvasports.com
```

If DNS has propagated, you should see a response!

---

### **Step 5: Get SSL Certificate**

Once HTTP is working:

```bash
# Stop nginx
brew services stop nginx

# Get SSL certificate
sudo certbot certonly --standalone \
  -d nowvasports.com \
  -d www.nowvasports.com \
  --email your-email@example.com \
  --agree-tos

# Verify certificates
ls -la /etc/letsencrypt/live/nowvasports.com/
```

---

### **Step 6: Enable HTTPS**

```bash
# Edit nginx config
nano nginx_production.conf
```

**Uncomment the HTTPS server block (lines 25-100)** and **comment out the HTTP-only block**

```bash
# Copy updated config
sudo cp nginx_production.conf /opt/homebrew/etc/nginx/servers/nowva.conf

# Test configuration
sudo nginx -t

# Start nginx
brew services start nginx

# Test HTTPS
curl -I https://nowvasports.com
```

---

### **Step 7: Update Frontend Environment**

```bash
cd frontend_demo

# Create/edit .env
cat > .env << 'EOF'
VITE_API_URL=https://nowvasports.com/api
VITE_LIVEKIT_URL=wss://nowva-k5kvmizx.livekit.cloud
EOF

# Rebuild frontend
npm run build

# Restart Gunicorn
cd ..
pkill -f "gunicorn.*src.api.main:app"

export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"
export PYTHONPATH='src'
nohup gunicorn -c gunicorn_config.py src.api.main:app > logs/gunicorn_startup.log 2>&1 &
```

---

### **Step 8: Set Up SSL Auto-Renewal**

```bash
# Test renewal
sudo certbot renew --dry-run

# Add cron job for auto-renewal
sudo crontab -e
```

Add this line:
```
0 2 * * * certbot renew --quiet --post-hook "brew services reload nginx"
```

---

## 🎯 Final Verification

```bash
# Check all services
echo "=== DNS Resolution ==="
dig nowvasports.com

echo "=== HTTP Redirect ==="
curl -I http://nowvasports.com

echo "=== HTTPS Response ==="
curl -I https://nowvasports.com

echo "=== API Health ==="
curl https://nowvasports.com/api/health

echo "=== Production Services ==="
echo "Redis: $(redis-cli ping)"
echo "Celery Workers: $(ps aux | grep 'celery.*worker' | grep -v grep | wc -l | tr -d ' ')"
echo "Gunicorn: $(ps aux | grep 'gunicorn' | grep -v grep | wc -l | tr -d ' ')"
```

**Open in browser:**
- Frontend: https://nowvasports.com
- API Docs: https://nowvasports.com/docs

---

## 🔧 Troubleshooting

### DNS not resolving
```bash
# Check propagation status
dig nowvasports.com

# Or use online tool
open https://dnschecker.org/#A/nowvasports.com
```

### Can't access from outside
- Verify port forwarding (80 & 443)
- Check firewall: `sudo pfctl -s all`
- Test from phone (cellular data, not WiFi)

### nginx 502 Bad Gateway
```bash
# Check Gunicorn is running
ps aux | grep gunicorn

# Check nginx logs
tail -f /opt/homebrew/var/log/nginx/error.log
```

### SSL certificate issues
```bash
# Check certificate
sudo certbot certificates

# Renew manually
sudo certbot renew --force-renewal
```

---

## 📊 Your Production Stack

```
nowvasports.com (DNS) → Your Public IP
        ↓
    Router (Port Forwarding 80/443)
        ↓
    nginx (SSL Termination + Reverse Proxy)
        ↓
    Gunicorn :8000 (FastAPI + React Frontend)
        ↓
    Celery Workers (18 concurrent) ← Redis
        ↓
    PostgreSQL (Neon)
```

**Capacity:** Handles 20-30 concurrent users generating programs ✅

---

## 🎉 Launch Checklist

- [ ] DNS points to your IP
- [ ] Port forwarding configured (if needed)
- [ ] nginx configured and running
- [ ] HTTP access works
- [ ] SSL certificate obtained
- [ ] HTTPS works with valid certificate
- [ ] Frontend loads at https://nowvasports.com
- [ ] API responds at https://nowvasports.com/api/health
- [ ] API docs at https://nowvasports.com/docs
- [ ] SSL auto-renewal configured
- [ ] All production services running (Redis, Celery, Gunicorn)

---

## 🚨 Quick Commands

```bash
# Check all services status
./start_celery_workers.sh  # Start Celery if needed
ps aux | grep gunicorn     # Check Gunicorn
brew services list         # Check nginx & Redis

# View logs
tail -f logs/gunicorn_error.log
tail -f logs/celery/worker1.log
tail -f /opt/homebrew/var/log/nginx/error.log

# Restart services
brew services restart nginx
pkill -f gunicorn && nohup gunicorn -c gunicorn_config.py src.api.main:app &
```

---

## 🌐 Your Application URLs

**Production:**
- Website: https://nowvasports.com
- API: https://nowvasports.com/api
- API Docs: https://nowvasports.com/docs
- Health Check: https://nowvasports.com/api/health

**Local Development:**
- Website: http://localhost:8000
- API: http://localhost:8000/api
- API Docs: http://localhost:8000/docs

---

**Ready to launch! 🚀**
