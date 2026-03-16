# Deployment Overview - All Resources

## 📚 Documentation Files

### Primary Deployment Guide
- **[GCP_FREE_TIER_DEPLOYMENT.md](GCP_FREE_TIER_DEPLOYMENT.md)** - Complete step-by-step deployment guide
  - Full walkthrough from VM creation to running app
  - Memory optimization strategies for 1GB RAM
  - systemd service configuration
  - Nginx setup with optional SSL
  - Troubleshooting guide

### Quick Reference
- **[GCP_QUICK_REFERENCE.md](GCP_QUICK_REFERENCE.md)** - Quick command reference card
  - Common commands for daily operations
  - Troubleshooting quick fixes
  - Emergency procedures
  - File locations

### Existing Guides (Mac-focused)
- [DEPLOY_NOWVASPORTS.md](DEPLOY_NOWVASPORTS.md) - Original Mac deployment guide
- [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) - Mac production setup

---

## 🛠️ Automation Scripts

### Local Machine Scripts
Run these from your **local development machine**:

1. **[deploy_to_gcp.sh](deploy_to_gcp.sh)** - One-command deployment
   - Builds frontend
   - Creates deployment archive
   - Uploads to server
   - Restarts services
   - **Usage:** `./deploy_to_gcp.sh` (edit VM_NAME and ZONE first)

### Server Scripts
Run these **on the GCP VM**:

2. **[server_setup.sh](server_setup.sh)** - Automated initial server setup
   - Creates swap space
   - Installs all dependencies
   - Configures Redis, Nginx
   - Creates systemd services
   - Starts all services
   - **Usage:** `./server_setup.sh` (run once during initial setup)

3. **[server_monitor.sh](server_monitor.sh)** - Server health monitoring
   - Shows memory/swap/disk usage
   - Service status
   - Recent errors
   - API health check
   - **Usage:** `./server_monitor.sh` (run anytime to check status)

### Existing Scripts (Mac-focused)
- [start_production.sh](start_production.sh) - Mac production startup
- [start_celery_workers.sh](start_celery_workers.sh) - Mac Celery startup

---

## ⚙️ Configuration Files

### Server-Optimized Configs
- **[gunicorn_config_gcp.py](gunicorn_config_gcp.py)** - GCP-optimized Gunicorn config
  - 2 workers (vs 4 on Mac)
  - Reduced backlog and connections
  - Preload app for memory savings

- **[requirements-server.txt](requirements-server.txt)** - Minimal server dependencies
  - Excludes heavy libraries (torch, opencv, mmpose)
  - Only includes what's needed for API
  - Saves ~300-500 MB memory

### Existing Configs
- [gunicorn_config.py](gunicorn_config.py) - Mac configuration (4 workers)
- [nginx_production.conf](nginx_production.conf) - Mac Nginx config
- [requirements.txt](requirements.txt) - Full requirements (includes pose estimation)

---

## 📋 Deployment Workflow

### First-Time Deployment

1. **On Local Machine:**
   ```bash
   # Build frontend
   cd frontend_demo && npm run build && cd ..

   # Create archive
   tar -czf nowva-deploy.tar.gz \
     src/ frontend_demo/dist/ gunicorn_config_gcp.py \
     requirements-server.txt .env

   # Upload to server
   gcloud compute scp nowva-deploy.tar.gz YOUR-VM:~ --zone=YOUR-ZONE
   ```

2. **On GCP VM:**
   ```bash
   # Copy and extract archive
   mv ~/nowva-deploy.tar.gz ~/nowva/

   # Run automated setup
   ./server_setup.sh
   ```

3. **Done!** Your app is now running at `http://YOUR-EXTERNAL-IP/`

### Subsequent Updates

**Option A: Automated (Recommended)**
```bash
# From local machine
./deploy_to_gcp.sh
```

**Option B: Manual**
```bash
# Local: Build and upload
cd frontend_demo && npm run build && cd ..
tar -czf update.tar.gz src/ frontend_demo/dist/
gcloud compute scp update.tar.gz YOUR-VM:~/nowva/ --zone=YOUR-ZONE

# Server: Extract and restart
ssh YOUR-VM
cd ~/nowva
tar -xzf update.tar.gz
sudo systemctl restart nowva-api nowva-celery
```

---

## 🎯 Quick Start (30 minutes)

### Prerequisites
- GCP account with Free Tier e2-micro VM created
- Static external IP assigned
- Firewall allows ports 80, 443
- Domain DNS pointed to external IP (optional, for SSL)

### Steps

1. **Configure deployment script** (2 min)
   ```bash
   # Edit deploy_to_gcp.sh
   nano deploy_to_gcp.sh
   # Update VM_NAME and ZONE
   ```

2. **Run deployment** (5 min)
   ```bash
   ./deploy_to_gcp.sh
   ```

3. **SSH to server and run setup** (20 min)
   ```bash
   gcloud compute ssh YOUR-VM --zone=YOUR-ZONE
   cd nowva
   ./server_setup.sh
   ```

4. **Verify** (3 min)
   ```bash
   ./server_monitor.sh
   curl http://localhost:8000/api/health
   ```

5. **Access your app**
   - Frontend: `http://YOUR-EXTERNAL-IP/`
   - API Docs: `http://YOUR-EXTERNAL-IP/docs`
   - Health: `http://YOUR-EXTERNAL-IP/api/health`

---

## 🔧 Architecture Comparison

### Mac Development (Current)
```
├── Gunicorn: 4 workers
├── Celery: 3 workers × 6 greenlets = 18 concurrent
├── Redis: Unlimited memory
├── Frontend: Served by FastAPI
└── Total Memory: ~800MB-1.2GB (safe on 16GB+ Mac)
```

### GCP Free Tier (Optimized)
```
├── Gunicorn: 2 workers (50% reduction)
├── Celery: 1 worker × 3 greenlets = 3 concurrent (83% reduction)
├── Redis: 100MB limit
├── Frontend: Served by FastAPI (same)
└── Total Memory: ~440-720MB (safe on 1GB VM)
   └── 2GB Swap for safety
```

### Performance Impact
- **Mac:** 20-30 concurrent users, 18 concurrent generations
- **GCP Free Tier:** 10-15 concurrent users, 3 concurrent generations
- **Recommended for production:** GCP e2-small (2GB RAM, ~$13/mo)

---

## 📊 Resource Usage Breakdown

### 1GB RAM Allocation
| Service | Memory | Notes |
|---------|--------|-------|
| Gunicorn (2 workers) | 150-250 MB | FastAPI + Uvicorn workers |
| Celery (1 worker) | 80-150 MB | Gevent pool, 3 greenlets |
| Redis | 50-100 MB | 100MB maxmemory limit |
| Nginx | 10-20 MB | Lightweight reverse proxy |
| System | 150-200 MB | Ubuntu 22.04 overhead |
| **Total** | **440-720 MB** | Leaves 280-560 MB headroom |
| **Swap** | 2 GB | Safety net for spikes |

---

## ⚠️ Important Limitations

### What's NOT Included
❌ **Pose Estimation Libraries** (torch, opencv, mmpose)
- Excluded to save ~500 MB memory
- Only affects pose detection features
- Program generation API works fine without them

❌ **Docker/Kubernetes**
- Not needed for simple deployment
- Would add overhead on 1GB RAM

❌ **Node.js on Server**
- Frontend pre-built and uploaded
- Saves ~100-200 MB memory

### What IS Included
✅ **Program Generation API** (FastAPI + Celery)
✅ **Voice Agent** (LiveKit + OpenAI)
✅ **RAG System** (ChromaDB + Voyage + Cohere)
✅ **Email Service** (Resend)
✅ **PDF Generation** (WeasyPrint)
✅ **Database** (PostgreSQL - Neon cloud)

---

## 🔐 Security Notes

1. **Firewall:** GCP firewall rules limit ingress to ports 80/443 only
2. **SSL:** Use Let's Encrypt (free) for HTTPS
3. **Environment Variables:** Never commit `.env` to git
4. **Database:** Using Neon cloud PostgreSQL (not exposed)
5. **API Keys:** All stored in `.env`, loaded at runtime
6. **Updates:** Run `sudo apt update && sudo apt upgrade` monthly

---

## 📈 Scaling Path

### Current: Free Tier (e2-micro, 1GB RAM)
- **Cost:** $0/month
- **Users:** 10-15 concurrent
- **Programs:** 3 concurrent generations

### Upgrade 1: e2-small (2GB RAM)
- **Cost:** ~$13/month
- **Users:** 20-30 concurrent
- **Programs:** 12 concurrent generations (2 workers × 6 greenlets)
- **Change:** Edit systemd files to increase workers

### Upgrade 2: e2-medium (4GB RAM)
- **Cost:** ~$27/month
- **Users:** 50-100 concurrent
- **Programs:** 18 concurrent generations (3 workers × 6 greenlets)
- **Change:** Match Mac configuration

### Upgrade 3: Managed Services
- **Cloud Run** (serverless, auto-scaling)
- **GKE** (Kubernetes, high availability)
- **Load Balancer** (multiple instances)
- **Cost:** $100-500/month depending on traffic

---

## 🎓 Learning Resources

### Understanding the Stack
- **FastAPI:** [fastapi.tiangolo.com](https://fastapi.tiangolo.com)
- **Celery:** [docs.celeryq.dev](https://docs.celeryq.dev)
- **Gunicorn:** [docs.gunicorn.org](https://docs.gunicorn.org)
- **systemd:** `man systemd.service` on your server

### Monitoring & Operations
- **Memory:** `man free`, `man htop`
- **Logs:** `man journalctl`
- **Nginx:** [nginx.org/en/docs](https://nginx.org/en/docs)
- **GCP:** [cloud.google.com/compute/docs](https://cloud.google.com/compute/docs)

---

## 💡 Pro Tips

1. **Monitor Daily:** Run `./server_monitor.sh` daily for first week
2. **Set Up Alerts:** Use GCP monitoring for memory >90%
3. **Log Rotation:** Set up logrotate for `/home/USER/nowva/logs/`
4. **Backup `.env`:** Keep secure backup of environment variables
5. **Test Locally:** Always test changes on Mac before deploying
6. **Gradual Rollout:** Deploy to dev VM first, then production
7. **Keep Swap:** Even with 2GB RAM, keep 2GB swap for safety
8. **Update Regularly:** `sudo apt update && sudo apt upgrade` monthly

---

## 🆘 Getting Help

### Check These First
1. [GCP_QUICK_REFERENCE.md](GCP_QUICK_REFERENCE.md) - Common fixes
2. Server logs: `sudo journalctl -u nowva-api -n 100`
3. Memory usage: `free -h`
4. Service status: `sudo systemctl status nowva-api nowva-celery`

### Common Issues
| Problem | Solution |
|---------|----------|
| 502 Bad Gateway | `sudo systemctl restart nowva-api` |
| Out of Memory | Reduce workers, check `free -h` |
| Celery not responding | `sudo systemctl restart nowva-celery` |
| Slow performance | Check swap usage, consider upgrade |
| Can't SSH | Check GCP Console, VM might be OOM crashed |

### Still Stuck?
1. Run `./server_monitor.sh` and save output
2. Check all logs: `sudo journalctl -u nowva-api -n 500 > debug.log`
3. Review [GCP_FREE_TIER_DEPLOYMENT.md](GCP_FREE_TIER_DEPLOYMENT.md) troubleshooting section

---

## ✅ Final Checklist

Before going live:

- [ ] VM created and accessible via SSH
- [ ] Static external IP assigned
- [ ] Firewall rules configured (ports 80, 443)
- [ ] Domain DNS points to external IP (if using custom domain)
- [ ] Frontend built successfully (`npm run build`)
- [ ] `.env` file configured with all API keys
- [ ] `deploy_to_gcp.sh` updated with VM name and zone
- [ ] `server_setup.sh` completed without errors
- [ ] All services running (`systemctl is-active nowva-api nowva-celery`)
- [ ] Health endpoint returns 200 (`curl localhost:8000/api/health`)
- [ ] Frontend loads in browser
- [ ] Can generate test program successfully
- [ ] SSL certificate obtained (if using HTTPS)
- [ ] Monitoring script works (`./server_monitor.sh`)
- [ ] Know how to view logs and restart services
- [ ] Have backup of `.env` file

---

**Ready to deploy? Start with [GCP_FREE_TIER_DEPLOYMENT.md](GCP_FREE_TIER_DEPLOYMENT.md)!**
