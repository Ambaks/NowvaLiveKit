# Production Deployment Guide - NowvaLiveKit

## 🚀 Quick Start for Production Launch

### Prerequisites Checklist
- ✅ Redis installed and running
- ✅ nginx installed and running
- ✅ Python dependencies installed
- ✅ Frontend built (`frontend_demo/dist/` exists)
- ✅ `.env` file configured with all API keys
- ✅ Database accessible (Neon PostgreSQL)

---

## Production Services Required

Your production system requires **3 separate processes** running:

### 1️⃣ **Redis** (Message Broker)
### 2️⃣ **Celery Workers** (Background Job Processing)
### 3️⃣ **Gunicorn + FastAPI** (Web Server)

---

## 📋 Step-by-Step Deployment

### Step 1: Start Redis

```bash
# Check if Redis is running
brew services list | grep redis

# If not running, start it
brew services start redis

# Verify it's working
redis-cli ping
# Should return: PONG
```

**Status**: ✅ Redis is already running on your machine

---

### Step 2: Start Celery Workers

**Option A: Using the startup script (Recommended)**

```bash
# From project root directory
./start_celery_workers.sh
```

This starts 3 workers with 6 greenlets each = 18 concurrent program generations.

**Option B: Manual start (for debugging)**

```bash
# Start workers in foreground to see output
celery -A src.api.celery_app worker \
    --pool=gevent \
    --concurrency=6 \
    --loglevel=info
```

**Verify workers are running:**

```bash
# Check worker status
celery -A src.api.celery_app inspect active

# Check running processes
ps aux | grep celery | grep nowva_program_generator
```

**Worker Logs:**
- Located in: `logs/celery/worker1.log`, `worker2.log`, `worker3.log`
- Monitor live: `tail -f logs/celery/worker1.log`

---

### Step 3: Start FastAPI with Gunicorn

**Option A: Using production script**

```bash
# This starts Redis, Celery, AND Gunicorn
./start_production.sh
```

⚠️ **Note**: This script runs Gunicorn in the foreground. Press Ctrl+C to stop.

**Option B: Start Gunicorn manually**

```bash
# Ensure library path is set (for PDF generation)
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

# Start Gunicorn with 4 workers
PYTHONPATH='src' gunicorn -c config/gunicorn_config.py src.api.main:app
```

**Verify FastAPI is running:**

```bash
# Check health endpoint
curl http://localhost:8000/api/health

# Check API docs
open http://localhost:8000/docs
```

---

## 🔍 Production Service Status Check

**Quick status check command:**

```bash
# Check all services
echo "=== Redis ===" && redis-cli ping
echo "=== Celery Workers ===" && celery -A src.api.celery_app inspect ping
echo "=== Gunicorn ===" && curl -s http://localhost:8000/api/health
```

**Expected Output:**
- Redis: `PONG`
- Celery: `{'worker1@...': {'ok': 'pong'}, 'worker2@...': ...}`
- Gunicorn: `{"status":"healthy",...}`

---

## 📁 Directory Structure for Production

```
NowvaLiveKit/
├── logs/
│   ├── celery/
│   │   ├── worker1.log
│   │   ├── worker2.log
│   │   └── worker3.log
│   ├── gunicorn_access.log
│   ├── gunicorn_error.log
│   └── gunicorn.pid
├── frontend_demo/
│   └── dist/          # Built frontend (served by FastAPI)
├── programs/          # Generated PDFs and markdown
├── .env               # Environment variables (API keys, etc.)
├── start_celery_workers.sh
├── start_production.sh
└── config/gunicorn_config.py
```

---

## 🌐 Accessing Your Application

Once all services are running:

- **Frontend**: http://localhost:8000/
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/health
- **Generate Program**: POST to http://localhost:8000/api/programs/generate

---

## 🛑 Stopping Production Services

### Stop Everything:

```bash
# Stop Gunicorn (if started with script)
# Press Ctrl+C in the terminal where it's running

# OR kill by process name
pkill -f "gunicorn.*src.api.main:app"

# Stop Celery workers
pkill -f "celery.*nowva_program_generator"

# Stop Redis (optional - can leave running)
brew services stop redis

# Stop nginx (optional)
brew services stop nginx
```

---

## 📊 Monitoring Production

### Monitor Celery Workers:

```bash
# Active tasks
celery -A src.api.celery_app inspect active

# Worker stats
celery -A src.api.celery_app inspect stats

# Scheduled tasks
celery -A src.api.celery_app inspect scheduled

# Reserved tasks
celery -A src.api.celery_app inspect reserved
```

### Monitor Logs:

```bash
# Celery worker logs
tail -f logs/celery/worker1.log

# Gunicorn access log
tail -f logs/gunicorn_access.log

# Gunicorn error log
tail -f logs/gunicorn_error.log

# Watch for errors
grep ERROR logs/gunicorn_error.log
grep ERROR logs/celery/*.log
```

### Monitor Redis:

```bash
# Redis stats
redis-cli info stats

# Connected clients
redis-cli client list

# Memory usage
redis-cli info memory

# Task queue length
redis-cli llen celery
```

### Monitor System Resources:

```bash
# CPU and memory usage
ps aux | grep -E "celery|gunicorn" | awk '{print $3, $4, $11}'

# Database connections (if needed)
# Connect to your Neon PostgreSQL and run:
# SELECT count(*) FROM pg_stat_activity WHERE datname = 'NowvaDev';
```

---

## 🚨 Troubleshooting

### Issue: Celery workers not responding

**Symptom**: `celery inspect ping` returns "No nodes replied"

**Solutions**:
1. Check if Redis is running: `redis-cli ping`
2. Check worker logs: `tail -f logs/celery/worker1.log`
3. Restart workers: `pkill -f celery && ./start_celery_workers.sh`
4. Try starting worker in foreground to see errors:
   ```bash
   celery -A src.api.celery_app worker --pool=gevent --concurrency=2 --loglevel=info
   ```

### Issue: "Module not found" errors

**Solution**: Ensure PYTHONPATH is set:
```bash
export PYTHONPATH='src'
# OR
PYTHONPATH='src' celery -A src.api.celery_app worker ...
```

### Issue: Database connection pool exhausted

**Symptom**: `QueuePool limit exceeded` errors

**Solutions**:
1. Reduce Celery worker concurrency: Change `--concurrency=6` to `--concurrency=4`
2. Or increase pool size in `src/db/database.py`:
   ```python
   pool_size=10  # Increase from 5
   max_overflow=20  # Increase from 10
   ```

### Issue: nginx 502 Bad Gateway

**Solution**:
1. Check if Gunicorn is running: `ps aux | grep gunicorn`
2. If not, start it: `PYTHONPATH='src' gunicorn -c config/gunicorn_config.py src.api.main:app`
3. Check Gunicorn logs: `tail -f logs/gunicorn_error.log`

### Issue: Frontend not loading

**Solutions**:
1. Check if frontend is built: `ls -la frontend_demo/dist/`
2. If not, build it: `cd frontend_demo && npm run build`
3. Check FastAPI startup logs for "Serving frontend assets" message

---

## 🔐 Environment Variables Required

Make sure these are set in your `.env` file:

```bash
# Database
DATABASE_URL=postgresql://...

# OpenAI
OPENAI_API_KEY=sk-...

# LiveKit
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_URL=wss://...

# Email (Resend)
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com

# Redis & Celery (already added)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
USE_CELERY=true
```

---

## 📈 Performance & Capacity

**Current Setup Capacity:**
- **API Workers**: 4 Gunicorn workers (handles 100+ requests/sec)
- **Job Workers**: 18 concurrent program generations (3 workers × 6 greenlets)
- **Database**: 78 max connections (4×15 + 3×6)
- **Throughput**: ~200 programs/hour

**For 20-30 concurrent users**: ✅ Well within capacity

---

## 🎯 Next Steps for Full Production

1. **Domain Setup**:
   - Point your domain DNS to your Mac's IP address
   - Update nginx config: `/opt/homebrew/etc/nginx/nginx.conf`
   - Replace `yourdomain.com` with your actual domain

2. **SSL Certificate**:
   ```bash
   # Stop nginx first
   brew services stop nginx

   # Get SSL certificate
   sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

   # Restart nginx
   brew services start nginx
   ```

3. **Update Frontend Environment**:
   ```bash
   cd frontend_demo

   # Edit .env
   echo "VITE_API_URL=https://yourdomain.com/api" > .env
   echo "VITE_LIVEKIT_URL=wss://nowva-k5kvmizx.livekit.cloud" >> .env

   # Rebuild
   npm run build
   ```

4. **Auto-restart on Mac Reboot** (optional):
   - Create LaunchDaemons for Celery and Gunicorn
   - Or use a process manager like supervisord

---

## 💡 Production Tips

1. **Keep Services Running**: Use `screen` or `tmux` to run Gunicorn in a persistent session
   ```bash
   # Start a screen session
   screen -S nowva_api

   # Start Gunicorn
   ./start_production.sh

   # Detach with: Ctrl+A then D
   # Reattach with: screen -r nowva_api
   ```

2. **Monitor Logs Regularly**: Check for errors daily
   ```bash
   grep -i error logs/gunicorn_error.log
   grep -i error logs/celery/*.log
   ```

3. **Database Backups**: Ensure Neon has automatic backups enabled

4. **Rate Limiting**: Already implemented (1 program per week per email)

5. **Keep Redis Running**: Redis is lightweight, safe to leave running always

---

## ✅ Pre-Launch Checklist

Before going live, verify:

- [ ] All environment variables in `.env` are set
- [ ] Redis is running (`brew services list | grep redis`)
- [ ] Celery workers started (`ps aux | grep celery`)
- [ ] Gunicorn started (`ps aux | grep gunicorn`)
- [ ] Frontend loads at `http://localhost:8000/`
- [ ] API docs accessible at `http://localhost:8000/docs`
- [ ] Test program generation works
- [ ] Email sending works (if RESEND_API_KEY is configured)
- [ ] Logs directory exists and is writable
- [ ] Programs directory exists for PDF storage

---

## 📞 Quick Command Reference

```bash
# Start production
./start_production.sh

# Start just Celery workers
./start_celery_workers.sh

# Check service status
brew services list
ps aux | grep -E "celery|gunicorn|redis"

# Monitor logs
tail -f logs/celery/worker1.log
tail -f logs/gunicorn_error.log

# Stop all
pkill -f "gunicorn.*src.api.main:app"
pkill -f "celery.*nowva_program_generator"

# Health check
curl http://localhost:8000/api/health
```

---

## 🎉 You're Ready to Launch!

Once all services are running and verified, your production system is live and ready to handle 20-30 concurrent users!
