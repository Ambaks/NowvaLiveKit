#!/bin/bash
# Server monitoring script - run this ON THE SERVER

echo "=========================================="
echo "NowvaLiveKit Server Status"
echo "=========================================="
echo ""

# Memory usage
echo "=== MEMORY USAGE ==="
free -h
echo ""

# Swap usage
echo "=== SWAP USAGE ==="
swapon --show
echo ""

# Disk usage
echo "=== DISK USAGE ==="
df -h / | tail -1
echo ""

# Service status
echo "=== SERVICES ==="
for service in redis-server nowva-api nowva-celery nginx; do
  if systemctl is-active --quiet $service; then
    echo "✓ $service: RUNNING"
  else
    echo "✗ $service: STOPPED"
  fi
done
echo ""

# Process memory
echo "=== TOP MEMORY CONSUMERS ==="
ps aux --sort=-%mem | head -6
echo ""

# Redis stats
echo "=== REDIS ==="
redis-cli info memory | grep -E "used_memory_human|maxmemory_human"
echo ""

# Celery workers
echo "=== CELERY WORKERS ==="
cd /home/$USER/nowva
source venv/bin/activate
celery -A src.api.celery_app inspect ping 2>/dev/null || echo "No workers responding"
echo ""

# Recent errors
echo "=== RECENT ERRORS (last 10) ==="
sudo journalctl -u nowva-api -u nowva-celery --no-pager -n 10 --grep ERROR || echo "No recent errors"
echo ""

# API health
echo "=== API HEALTH ==="
curl -s http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || echo "API not responding"
echo ""

echo "=========================================="
echo "Monitor logs in real-time:"
echo "  sudo journalctl -u nowva-api -f"
echo "  tail -f ~/nowva/logs/gunicorn_error.log"
echo "=========================================="
