#!/bin/bash
# Start all production services for NowvaLiveKit

set -e

echo "=========================================="
echo "Starting NowvaLiveKit Production Services"
echo "=========================================="

# Create logs directory
mkdir -p logs

# Start Redis
echo "Starting Redis..."
brew services start redis
sleep 2

# Start Celery workers
echo "Starting Celery workers..."
./start_celery_workers.sh

# Start Gunicorn
echo "Starting Gunicorn (FastAPI)..."
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"
PYTHONPATH='src' gunicorn -c gunicorn_config.py src.api.main:app

echo "=========================================="
echo "All services started!"
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo "=========================================="
