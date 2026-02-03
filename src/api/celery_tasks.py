"""
Celery Task Definitions
Wraps async service functions for Celery execution
"""
import asyncio
from .celery_app import celery_app
import traceback


@celery_app.task(bind=True, name='generate_program', max_retries=3)
def generate_program_task(self, job_id: str, user_id: str, params: dict):
    """
    Generate a workout program (Celery task wrapper)
    Handles async-to-sync conversion for gevent workers
    """
    from .services.program_generator_v2 import generate_program_background

    print(f"[CELERY TASK {self.request.id}] Starting job {job_id}")

    # Create event loop for this greenlet
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            generate_program_background(job_id, user_id, params)
        )
        print(f"[CELERY TASK {self.request.id}] Completed job {job_id}")
        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_msg = str(e)
        print(f"[CELERY TASK {self.request.id}] ERROR: {error_msg}")
        print(traceback.format_exc())

        # Retry logic for OpenAI rate limits
        if "rate_limit" in error_msg.lower() or "429" in error_msg:
            print("[CELERY TASK] Rate limit hit, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)

        # Retry for transient API errors
        elif any(code in error_msg for code in ["500", "502", "503"]):
            print("[CELERY TASK] API error, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)

        # Retry for database errors
        elif "database" in error_msg.lower() or "connection" in error_msg.lower():
            print("[CELERY TASK] Database error, retrying in 30s...")
            raise self.retry(exc=e, countdown=30)

        else:
            # Mark job as failed
            from db.database import SessionLocal
            from .services.job_manager import update_job_status

            db = SessionLocal()
            try:
                update_job_status(db, job_id, "failed", error_message=error_msg[:1000])
            finally:
                db.close()
            raise

    finally:
        loop.close()


@celery_app.task(bind=True, name='update_program', max_retries=3)
def update_program_task(self, job_id: str, user_id: str, program_id: int,
                       change_request: str, user_profile: dict):
    """Update an existing workout program"""
    from .services.program_updater import update_program_background

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            update_program_background(job_id, user_id, program_id,
                                     change_request, user_profile)
        )
        return {"status": "completed", "job_id": job_id}
    except Exception as e:
        # Same retry logic as generate_program_task
        error_msg = str(e)
        if "rate_limit" in error_msg.lower() or "429" in error_msg:
            raise self.retry(exc=e, countdown=60)
        elif any(code in error_msg for code in ["500", "502", "503"]):
            raise self.retry(exc=e, countdown=60)
        else:
            from db.database import SessionLocal
            from .services.job_manager import update_job_status
            db = SessionLocal()
            try:
                update_job_status(db, job_id, "failed", error_message=error_msg[:1000])
            finally:
                db.close()
            raise
    finally:
        loop.close()
