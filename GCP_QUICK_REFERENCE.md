# GCP Free Tier - Quick Reference Card

## 🚀 Initial Deployment

### 1. On Your Local Machine:
```bash
# Build frontend
cd frontend_demo && npm run build && cd ..

# Run deployment script
./deploy_to_gcp.sh
```

### 2. First-Time Server Setup:
```bash
# SSH into VM
gcloud compute ssh YOUR-VM-NAME --zone=YOUR-ZONE

# Follow GCP_FREE_TIER_DEPLOYMENT.md steps 1-10
```

---

## 📋 Daily Operations

### Start All Services:
```bash
sudo systemctl start redis-server nowva-api nowva-celery nginx
```

### Stop All Services:
```bash
sudo systemctl stop nowva-api nowva-celery
```

### Restart After Code Update:
```bash
sudo systemctl restart nowva-api nowva-celery
```

### View Service Status:
```bash
sudo systemctl status nowva-api nowva-celery
```

---

## 📊 Monitoring

### Check Server Health:
```bash
# Run monitoring script
~/nowva/server_monitor.sh

# Or manually:
free -h                          # Memory usage
sudo systemctl status nowva-api  # API status
curl localhost:8000/api/health   # Health check
```

### View Logs:
```bash
# Real-time API logs
sudo journalctl -u nowva-api -f

# Real-time Celery logs
tail -f ~/nowva/logs/celery/worker.log

# Recent errors only
sudo journalctl -u nowva-api --grep ERROR -n 50
```

### Monitor Memory:
```bash
# Watch memory in real-time
watch -n 1 free -h

# Top memory consumers
ps aux --sort=-%mem | head -10

# If using htop
htop
```

---

## 🔧 Troubleshooting

### Service Won't Start:
```bash
# Check logs for errors
sudo journalctl -u nowva-api -n 100 --no-pager
sudo journalctl -u nowva-celery -n 100 --no-pager

# Check if port is in use
sudo lsof -i :8000

# Kill stuck processes
pkill -f gunicorn
pkill -f celery
sudo systemctl restart nowva-api nowva-celery
```

### Out of Memory:
```bash
# Check OOM events
sudo dmesg | grep -i "killed process"

# Check swap usage
swapon --show
free -h

# Reduce workers if needed (edit systemd files)
sudo nano /etc/systemd/system/nowva-api.service
# Change workers to 1 in gunicorn config

sudo systemctl daemon-reload
sudo systemctl restart nowva-api
```

### Celery Not Responding:
```bash
# Check Redis
redis-cli ping

# Restart Celery
sudo systemctl restart nowva-celery

# Test Celery workers
cd ~/nowva
source venv/bin/activate
celery -A src.api.celery_app inspect ping
```

### nginx 502 Error:
```bash
# Check if Gunicorn is running
sudo systemctl status nowva-api
sudo ss -tlnp | grep :8000

# Check nginx error log
sudo tail -f /var/log/nginx/error.log

# Restart API
sudo systemctl restart nowva-api
```

---

## 🔄 Updating Your Code

### Quick Update (using script):
```bash
# From your local machine
./deploy_to_gcp.sh
```

### Manual Update:
```bash
# 1. On local machine - build and upload
cd frontend_demo && npm run build && cd ..
tar -czf update.tar.gz src/ frontend_demo/dist/
gcloud compute scp update.tar.gz YOUR-VM:~ --zone=YOUR-ZONE

# 2. On server - extract and restart
ssh YOUR-VM
cd ~/nowva
tar -xzf ~/update.tar.gz
sudo systemctl restart nowva-api nowva-celery
```

---

## 🔐 SSL Certificate Management

### Get Certificate (first time):
```bash
sudo systemctl stop nginx
sudo certbot certonly --standalone -d nowvasports.com -d www.nowvasports.com
sudo systemctl start nginx
```

### Renew Certificate:
```bash
# Manual renewal
sudo certbot renew

# Check renewal status
sudo certbot certificates

# Auto-renewal is handled by systemd timer
sudo systemctl status certbot.timer
```

---

## 📁 Important File Locations

| What | Where |
|------|-------|
| Application code | `/home/USER/nowva/src/` |
| Virtual environment | `/home/USER/nowva/venv/` |
| Environment variables | `/home/USER/nowva/.env` |
| API logs | `/home/USER/nowva/logs/gunicorn_*.log` |
| Celery logs | `/home/USER/nowva/logs/celery/worker.log` |
| Systemd service files | `/etc/systemd/system/nowva-*.service` |
| Nginx config | `/etc/nginx/sites-available/nowva` |
| SSL certificates | `/etc/letsencrypt/live/DOMAIN/` |
| Redis config | `/etc/redis/redis.conf` |

---

## ⚙️ Configuration Files to Edit

### Reduce Memory If Needed:

**Gunicorn workers:**
```bash
sudo nano /etc/systemd/system/nowva-api.service
# In ExecStart line, add: --workers 1
sudo systemctl daemon-reload
sudo systemctl restart nowva-api
```

**Celery concurrency:**
```bash
sudo nano /etc/systemd/system/nowva-celery.service
# Change: --concurrency=3 to --concurrency=2
sudo systemctl daemon-reload
sudo systemctl restart nowva-celery
```

**Redis memory:**
```bash
sudo nano /etc/redis/redis.conf
# Set: maxmemory 50mb
sudo systemctl restart redis-server
```

---

## 🔍 Useful Commands

```bash
# Check all service status
systemctl is-active redis-server nowva-api nowva-celery nginx

# View all logs together
sudo journalctl -u nowva-api -u nowva-celery -f

# Check disk space
df -h

# Check network ports
sudo ss -tlnp

# Check process tree
pstree -p

# Find large files
du -h --max-depth=1 ~/nowva | sort -hr

# Clean old logs
find ~/nowva/logs -type f -name "*.log" -mtime +30 -delete

# Restart everything
sudo systemctl restart redis-server nowva-api nowva-celery nginx
```

---

## 🎯 Performance Tuning

### If memory is consistently >90%:
1. Reduce Gunicorn workers to 1
2. Reduce Celery concurrency to 2
3. Set Redis maxmemory to 50MB
4. Check for memory leaks in logs

### If CPU is maxed out:
1. Check for infinite loops in logs
2. Reduce request timeout
3. Consider upgrading to e2-small

### If disk is filling up:
1. Set up log rotation
2. Clean old program PDFs
3. Check database size

---

## ⚠️ Red Flags to Watch For

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Swap usage >50% | Not enough RAM | Reduce workers |
| API responding slow | High memory/CPU | Check logs, reduce workers |
| Celery tasks timing out | Low concurrency | Check worker logs |
| 502 errors | Gunicorn crashed | Check memory, restart service |
| Redis connection errors | Redis out of memory | Increase maxmemory limit |
| Disk 100% full | Logs too big | Set up log rotation |

---

## 📞 Emergency Procedures

### Server Completely Unresponsive:
```bash
# Reboot VM from local machine
gcloud compute instances reset YOUR-VM --zone=YOUR-ZONE

# Services will auto-start (systemd enabled them)
# Wait 2-3 minutes, then check status
gcloud compute ssh YOUR-VM --zone=YOUR-ZONE --command="systemctl is-active nowva-api"
```

### Database Connection Issues:
```bash
# Check DATABASE_URL in .env
cat ~/nowva/.env | grep DATABASE_URL

# Test connection
cd ~/nowva
source venv/bin/activate
python -c "from sqlalchemy import create_engine; import os; engine = create_engine(os.getenv('DATABASE_URL')); print('✓ Connected')"
```

### Everything Broken, Start Fresh:
```bash
# Stop all services
sudo systemctl stop nowva-api nowva-celery nginx

# Clear logs
rm -rf ~/nowva/logs/*
mkdir -p ~/nowva/logs/celery

# Restart services
sudo systemctl start nowva-api nowva-celery nginx

# Check status
sudo journalctl -u nowva-api -n 50
```

---

## 📈 Scaling Up (When You Outgrow Free Tier)

### Upgrade to e2-small (2GB RAM):
```bash
# Stop VM
gcloud compute instances stop YOUR-VM --zone=YOUR-ZONE

# Change machine type
gcloud compute instances set-machine-type YOUR-VM \
  --machine-type=e2-small \
  --zone=YOUR-ZONE

# Start VM
gcloud compute instances start YOUR-VM --zone=YOUR-ZONE

# Update configs to use more workers
# Edit systemd files to increase workers/concurrency
```

**Cost:** ~$13/month (not free, but cheap)

**Benefits:**
- 2× memory (2GB)
- Handle 20-30 concurrent users
- Run 2 Celery workers with 6 greenlets each
- Run 4 Gunicorn workers

---

## ✅ Pre-Flight Checklist

Before deploying a new version:

- [ ] Frontend builds successfully (`npm run build`)
- [ ] All tests pass (if you have tests)
- [ ] `.env` file has all required variables
- [ ] Database migrations complete (if any)
- [ ] Backup current deployment
- [ ] Check available disk space on server (`df -h`)
- [ ] Check server memory usage (`free -h`)
- [ ] Review recent error logs
- [ ] Have SSH access to server
- [ ] Know how to rollback (keep previous tar.gz)

---

## 🎉 Success Indicators

Your deployment is healthy if:

- ✅ `curl localhost:8000/api/health` returns 200 OK
- ✅ `systemctl is-active nowva-api nowva-celery` shows active
- ✅ `celery -A src.api.celery_app inspect ping` gets response
- ✅ Memory usage <70%
- ✅ Swap usage <30%
- ✅ No errors in `journalctl -u nowva-api -n 50`
- ✅ Frontend loads in browser
- ✅ Can generate a test program successfully

---

**Questions? Issues? Check the full guide: [GCP_FREE_TIER_DEPLOYMENT.md](GCP_FREE_TIER_DEPLOYMENT.md)**
