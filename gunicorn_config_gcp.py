"""
Gunicorn Configuration for GCP Free Tier (1GB RAM)
Optimized for e2-micro instance

IMPORTANT: This config uses only 2 workers instead of 4 to fit in 1GB RAM.
For e2-small (2GB RAM), you can increase workers to 4.
"""
# Server socket
bind = "127.0.0.1:8000"
backlog = 512  # Reduced from 2048 for low-memory server

# Worker processes - OPTIMIZED FOR 1GB RAM
# DO NOT INCREASE without monitoring memory usage
workers = 2  # Reduced from 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 500  # Reduced from 1000
max_requests = 500  # Restart workers after 500 requests to prevent memory leaks
max_requests_jitter = 25
timeout = 120  # 2 minutes timeout for long-running requests
keepalive = 5

# Logging - reduced verbosity to save resources
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "warning"  # Changed from "info" to reduce I/O
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "nowva_api_gcp"

# Server mechanics
daemon = False
pidfile = "logs/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# Preload app - CRITICAL for memory savings
# This loads the app once before forking, so worker processes share memory
preload_app = True

# Worker lifecycle
graceful_timeout = 30  # Time to wait for workers to finish during graceful shutdown

# Memory optimization
# Worker recycling helps prevent memory leaks
# With max_requests=500, each worker will restart after 500 requests
