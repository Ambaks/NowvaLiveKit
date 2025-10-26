"""
Job Manager Service
Handles creation and status tracking of program generation jobs
"""
from sqlalchemy.orm import Session
from db.models import ProgramGenerationJob
import uuid
from datetime import datetime
from typing import Optional


def create_job(
    db: Session,
    user_id: str,
    height_cm: float,
    weight_kg: float,
    goal_category: str,
    goal_raw: str,
    duration_weeks: int,
    days_per_week: int,
    fitness_level: str,
    age: int,
    sex: str,
    session_duration: int = 60,
    injury_history: str = "none",
    specific_sport: str = "none",
    has_vbt_capability: bool = False,
    user_notes: str = None
) -> ProgramGenerationJob:
    """
    Create a new program generation job

    Args:
        db: Database session
        user_id: User UUID
        height_cm: User's height in centimeters
        weight_kg: User's weight in kilograms
        goal_category: Training goal (power, strength, hypertrophy, athletic_performance)
        goal_raw: User's goal description
        duration_weeks: Program duration
        days_per_week: Training frequency
        fitness_level: beginner, intermediate, or advanced
        age: User's age in years
        sex: Biological sex (M/F/male/female)
        session_duration: Available minutes per session (default: 60)
        injury_history: Current or past injuries (default: "none")
        specific_sport: Sport name or "none" (default: "none")
        has_vbt_capability: Whether user has VBT equipment (default: False)
        user_notes: Any additional user notes or preferences (default: None)

    Returns:
        ProgramGenerationJob instance
    """
    job = ProgramGenerationJob(
        id=uuid.uuid4(),
        user_id=user_id,
        status="pending",
        progress=0,
        height_cm=height_cm,
        weight_kg=weight_kg,
        goal_category=goal_category,
        goal_raw=goal_raw,
        duration_weeks=duration_weeks,
        days_per_week=days_per_week,
        fitness_level=fitness_level,
        age=age,
        sex=sex,
        session_duration=session_duration,
        injury_history=injury_history,
        specific_sport=specific_sport,
        has_vbt_capability=has_vbt_capability,
        user_notes=user_notes
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    print(f"[JOB MANAGER] Created job {job.id} for user {user_id}")
    print(f"[JOB MANAGER] Parameters: {age}{sex}, {goal_category}, {duration_weeks}w, {days_per_week}d/w, {fitness_level}")
    if has_vbt_capability:
        print(f"[JOB MANAGER] VBT capability: ENABLED")
    return job


def get_job_status(db: Session, job_id: str) -> Optional[ProgramGenerationJob]:
    """
    Get job by ID

    Args:
        db: Database session
        job_id: Job UUID as string

    Returns:
        ProgramGenerationJob instance or None
    """
    return db.query(ProgramGenerationJob).filter(
        ProgramGenerationJob.id == job_id
    ).first()


def update_job_status(
    db: Session,
    job_id: str,
    status: str,
    progress: Optional[int] = None,
    program_id: Optional[str] = None,
    error_message: Optional[str] = None
) -> Optional[ProgramGenerationJob]:
    """
    Update job status and related fields

    Args:
        db: Database session
        job_id: Job UUID as string
        status: New status (pending, in_progress, completed, failed)
        progress: Progress percentage (0-100)
        program_id: Generated program ID (for completed jobs)
        error_message: Error message (for failed jobs)

    Returns:
        Updated ProgramGenerationJob instance or None
    """
    job = get_job_status(db, job_id)
    if not job:
        print(f"[JOB MANAGER] ⚠️  Job {job_id} not found")
        return None

    job.status = status

    if progress is not None:
        job.progress = progress

    # Set started_at when status changes to in_progress
    if status == "in_progress" and not job.started_at:
        job.started_at = datetime.utcnow()

    # Set completed_at when job finishes (success or failure)
    if status in ["completed", "failed"] and not job.completed_at:
        job.completed_at = datetime.utcnow()

    if program_id:
        job.program_id = program_id

    if error_message:
        job.error_message = error_message

    try:
        # Flush changes to database before commit
        db.flush()
        # Commit the transaction - this makes changes visible to other sessions
        db.commit()
        print(f"[JOB MANAGER] ✅ Committed job update {job_id}: status={status}, progress={progress}%")
    except Exception as e:
        print(f"[JOB MANAGER] ⚠️  Failed to commit job update: {e}")
        db.rollback()
        raise

    return job


def get_user_jobs(db: Session, user_id: str, limit: int = 10) -> list[ProgramGenerationJob]:
    """
    Get recent jobs for a user

    Args:
        db: Database session
        user_id: User UUID as string
        limit: Maximum number of jobs to return

    Returns:
        List of ProgramGenerationJob instances
    """
    return db.query(ProgramGenerationJob).filter(
        ProgramGenerationJob.user_id == user_id
    ).order_by(
        ProgramGenerationJob.created_at.desc()
    ).limit(limit).all()
