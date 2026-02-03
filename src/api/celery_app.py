"""
Celery Application for Program Generation Tasks
Uses gevent pool for efficient I/O-bound async API calls
"""
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
import os
from dotenv import load_dotenv

load_dotenv()

# Celery app instance
celery_app = Celery(
    'nowva_program_generator',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    include=['src.api.celery_tasks']
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Retry settings
    task_default_retry_delay=60,
    task_max_retries=3,

    # Rate limiting (20 programs/min max)
    task_annotations={
        'src.api.celery_tasks.generate_program_task': {
            'rate_limit': '20/m'
        }
    },

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,

    # Result backend settings
    result_expires=3600,  # 1 hour

    # Worker settings (optimize for gevent)
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# Database connection lifecycle
@worker_process_init.connect
def init_worker(**kwargs):
    from db.database import engine
    engine.dispose()
    print("[CELERY WORKER] Initialized - DB connections ready")

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    from db.database import engine
    engine.dispose()
    print("[CELERY WORKER] Shutdown - DB connections closed")
