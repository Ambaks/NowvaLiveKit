#!/bin/bash
# Start Celery Workers for NowvaLiveKit Program Generation
# Uses gevent pool for I/O-bound async operations

set -e

# Load environment variables
if [ -f .env ]; then
    source .env
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Celery Workers for Program Generation...${NC}"

# Check Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Redis is not running!${NC}"
    echo "Start Redis with: brew services start redis"
    exit 1
fi

echo -e "${GREEN}✓ Redis is running${NC}"

# Create logs directory
mkdir -p logs/celery

# Kill existing workers (cleanup)
pkill -f "celery.*nowva_program_generator" || true
sleep 2

# Export PYTHONPATH for all workers
export PYTHONPATH='src'

# Start Worker 1
echo -e "${BLUE}Starting Worker 1...${NC}"
nohup celery -A src.api.celery_app worker \
    --pool=gevent \
    --concurrency=6 \
    --hostname=worker1@%h \
    --loglevel=info \
    --logfile=logs/celery/worker1.log \
    > /dev/null 2>&1 &

# Start Worker 2
echo -e "${BLUE}Starting Worker 2...${NC}"
nohup celery -A src.api.celery_app worker \
    --pool=gevent \
    --concurrency=6 \
    --hostname=worker2@%h \
    --loglevel=info \
    --logfile=logs/celery/worker2.log \
    > /dev/null 2>&1 &

# Start Worker 3
echo -e "${BLUE}Starting Worker 3...${NC}"
nohup celery -A src.api.celery_app worker \
    --pool=gevent \
    --concurrency=6 \
    --hostname=worker3@%h \
    --loglevel=info \
    --logfile=logs/celery/worker3.log \
    > /dev/null 2>&1 &

# Wait for workers to initialize
sleep 5

echo ""
echo -e "${GREEN}✓ All workers started successfully${NC}"
echo ""
echo "Worker status:"
celery -A src.api.celery_app inspect active

echo ""
echo "Monitor workers with:"
echo "  tail -f logs/celery/worker1.log"
echo "  celery -A src.api.celery_app inspect active"
echo "  celery -A src.api.celery_app inspect stats"
echo ""
echo "Stop workers with:"
echo "  pkill -f 'celery.*nowva_program_generator'"
