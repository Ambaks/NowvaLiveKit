"""
Celery Task Definitions
Wraps async service functions for Celery execution
"""
import asyncio
import os
from openai import AsyncOpenAI
from .celery_app import celery_app
import traceback


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


@celery_app.task(bind=True, name='generate_program_v5', max_retries=3)
def generate_program_v5_task(self, job_id: str, user_id: str, params: dict):
    """
    Generate a workout program using V5 6-layer architecture (Celery task wrapper)

    V5 features:
    - 6-layer pipeline: Profile → Strategy → Volume → Builder → Validator → Serializer
    - 100% deterministic with optional LLM review
    - Fast: <1s without LLM, 10-20s with LLM
    """
    from .services.v5_adapter import convert_request_to_v5_input, get_user_data_from_request
    from .services.program_saver_v5 import save_and_publish_v5_program
    from .models.requests import ProgramGenerationRequest
    from program_generator_v5 import generate_program_v5
    from services.email_service import send_program_email

    print(f"[CELERY TASK V5 {self.request.id}] Starting job {job_id}")

    # Create event loop for this greenlet
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Build request object for user data extraction
        request = ProgramGenerationRequest(
            user_id=params["user_id"],
            name=params["name"],
            email=params.get("email", ""),
            height_cm=params["height_cm"],
            weight_kg=params["weight_kg"],
            age=params["age"],
            sex=params["sex"],
            goal_category=params["goal_category"],
            goal_raw=params["goal_raw"],
            duration_weeks=params["duration_weeks"],
            days_per_week=params["days_per_week"],
            fitness_level=params["fitness_level"],
            session_duration=params.get("session_duration", 60),
            injury_history=params.get("injury_history", "none"),
            specific_sport=params.get("specific_sport", "none"),
            has_vbt_capability=params.get("has_vbt_capability", False),
            user_notes=params.get("user_notes"),
            send_email=params.get("send_email", False),
            # V6 fields
            training_season=params.get("training_season"),
            games_per_week=params.get("games_per_week", 0),
            competition_date=params.get("competition_date"),
            equipment_tier=params.get("equipment_tier", 1),
        )

        # Convert to V5 input format
        v5_input = convert_request_to_v5_input(request)
        user_data = get_user_data_from_request(request)

        # Update job status
        from db.database import SessionLocal
        from .services.job_manager import update_job_status

        db = SessionLocal()
        try:
            update_job_status(db, job_id, "in_progress", progress=10)
        finally:
            db.close()

        # Generate program with V5 (6-layer architecture)
        v5_output = loop.run_until_complete(
            generate_program_v5(
                input_data=v5_input,
                openai_client=AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")),
                use_llm=True,
                input_type="structured"
            )
        )

        print(f"[CELERY TASK V5 {self.request.id}] V5 generation complete")
        print(f"  - Unique exercises: {v5_output.get('stats', {}).get('unique_exercises', 0)}")
        print(f"  - Generation time: {v5_output.get('stats', {}).get('generation_time_seconds', 0):.2f}s")

        # Save to database, create schedule, generate PDF
        db = SessionLocal()
        try:
            result = save_and_publish_v5_program(
                db=db,
                v5_output=v5_output,
                params=params,
                job_id=job_id,
                user_data=user_data
            )

            # Send email if requested
            if params.get("send_email") and result.get("pdf_path"):
                try:
                    print(f"[CELERY TASK V5 {self.request.id}] 📧 Sending email...")
                    email_result = send_program_email(
                        to_email=params.get("email"),
                        user_name=params.get("name"),
                        program_id=result["program_id"],
                        pdf_path=result["pdf_path"]
                    )
                    if email_result:
                        print(f"[CELERY TASK V5 {self.request.id}] ✅ Email sent!")
                    else:
                        print(f"[CELERY TASK V5 {self.request.id}] ⚠️  Email failed")
                except Exception as email_error:
                    print(f"[CELERY TASK V5 {self.request.id}] ⚠️  Email error: {email_error}")

            # Mark as completed (100%)
            update_job_status(db, job_id, "completed", progress=100, program_id=str(result['program_id']), error_message=None)

            print(f"[CELERY TASK V5 {self.request.id}] ✅ Completed job {job_id}")
            print(f"  - Program ID: {result['program_id']}")
            print(f"  - Schedule entries: {result['schedule_count']}")
            print(f"  - PDF: {result['pdf_path']}")

        except Exception as save_error:
            print(f"[CELERY TASK V5 {self.request.id}] ⚠️  Save/publish failed: {save_error}")
            traceback.print_exc()
            update_job_status(db, job_id, "failed", error_message=str(save_error)[:1000])
            raise
        finally:
            db.close()

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_msg = str(e)
        print(f"[CELERY TASK V5 {self.request.id}] ERROR: {error_msg}")
        print(traceback.format_exc())

        # Retry logic for rate limits
        if "rate_limit" in error_msg.lower() or "429" in error_msg:
            print("[CELERY TASK V5] Rate limit hit, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)

        # Retry for transient API errors
        elif any(code in error_msg for code in ["500", "502", "503"]):
            print("[CELERY TASK V5] API error, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)

        # Retry for database errors
        elif "database" in error_msg.lower() or "connection" in error_msg.lower():
            print("[CELERY TASK V5] Database error, retrying in 30s...")
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


@celery_app.task(bind=True, name='generate_program_v7', max_retries=3)
def generate_program_v7_task(self, job_id: str, user_id: str, params: dict):
    """
    Generate a workout program using the V7 architecture.

    V7 features:
    - Schema-first directive compiler
    - Postgres-backed knowledge graph
    - Deterministic block planning, assembly, validation, and repair
    - Optional bounded LLM planner/critic
    """
    from .models.requests import ProgramGenerationRequest
    from .services.program_saver_v7 import save_and_publish_v7_program
    from .services.v7_adapter import convert_request_to_v7_input, get_user_data_from_request
    from program_generator_v7 import generate_program_v7
    from services.email_service import send_program_email

    print(f"[CELERY TASK V7 {self.request.id}] Starting job {job_id}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        request = ProgramGenerationRequest(
            user_id=params["user_id"],
            name=params["name"],
            email=params.get("email", ""),
            height_cm=params["height_cm"],
            weight_kg=params["weight_kg"],
            age=params["age"],
            sex=params["sex"],
            goal_category=params["goal_category"],
            goal_raw=params["goal_raw"],
            duration_weeks=params["duration_weeks"],
            days_per_week=params["days_per_week"],
            fitness_level=params["fitness_level"],
            session_duration=params.get("session_duration", 60),
            injury_history=params.get("injury_history", "none"),
            specific_sport=params.get("specific_sport", "none"),
            has_vbt_capability=params.get("has_vbt_capability", False),
            user_notes=params.get("user_notes"),
            send_email=params.get("send_email", False),
            training_season=params.get("training_season"),
            games_per_week=params.get("games_per_week", 0),
            competition_date=params.get("competition_date"),
            equipment_tier=params.get("equipment_tier", 1),
        )

        v7_input = convert_request_to_v7_input(request)
        user_data = get_user_data_from_request(request)

        from db.database import SessionLocal
        from .services.job_manager import update_job_status

        db = SessionLocal()
        try:
            update_job_status(db, job_id, "in_progress", progress=10)
        finally:
            db.close()

        v7_output = loop.run_until_complete(
            generate_program_v7(
                input_data=v7_input,
                openai_client=AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")),
                use_llm=True,
            )
        )

        print(f"[CELERY TASK V7 {self.request.id}] V7 generation complete")
        print(f"  - Unique exercises: {v7_output.get('stats', {}).get('unique_exercises', 0)}")
        print(f"  - Generation time: {v7_output.get('stats', {}).get('generation_time_seconds', 0):.2f}s")
        print(f"  - KG version: {v7_output.get('overview', {}).get('kg_version')}")

        db = SessionLocal()
        try:
            result = save_and_publish_v7_program(
                db=db,
                v7_output=v7_output,
                params=params,
                job_id=job_id,
                user_data=user_data,
            )

            if params.get("send_email") and result.get("pdf_path"):
                try:
                    print(f"[CELERY TASK V7 {self.request.id}] 📧 Sending email...")
                    email_result = send_program_email(
                        to_email=params.get("email"),
                        user_name=params.get("name"),
                        program_id=result["program_id"],
                        pdf_path=result["pdf_path"],
                    )
                    if email_result:
                        print(f"[CELERY TASK V7 {self.request.id}] ✅ Email sent!")
                    else:
                        print(f"[CELERY TASK V7 {self.request.id}] ⚠️  Email failed")
                except Exception as email_error:
                    print(f"[CELERY TASK V7 {self.request.id}] ⚠️  Email error: {email_error}")

            update_job_status(
                db,
                job_id,
                "completed",
                progress=100,
                program_id=str(result["program_id"]),
                error_message=None,
            )
            print(f"[CELERY TASK V7 {self.request.id}] ✅ Completed job {job_id}")
        except Exception as save_error:
            print(f"[CELERY TASK V7 {self.request.id}] ⚠️  Save/publish failed: {save_error}")
            traceback.print_exc()
            update_job_status(db, job_id, "failed", error_message=str(save_error)[:1000])
            raise
        finally:
            db.close()

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_msg = str(e)
        print(f"[CELERY TASK V7 {self.request.id}] ERROR: {error_msg}")
        print(traceback.format_exc())

        if "rate_limit" in error_msg.lower() or "429" in error_msg:
            print("[CELERY TASK V7] Rate limit hit, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)
        elif any(code in error_msg for code in ["500", "502", "503"]):
            print("[CELERY TASK V7] API error, retrying in 60s...")
            raise self.retry(exc=e, countdown=60)
        elif "database" in error_msg.lower() or "connection" in error_msg.lower():
            print("[CELERY TASK V7] Database error, retrying in 30s...")
            raise self.retry(exc=e, countdown=30)
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
