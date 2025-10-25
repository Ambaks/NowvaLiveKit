"""
Programs Router
Endpoints for program generation and status checking
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID

from api.models.requests import ProgramGenerationRequest
from api.models.responses import JobResponse, JobStatusResponse, ProgramResponse
from api.services.program_generator_v2 import generate_program_background  # V2: Structured outputs
from api.services.job_manager import create_job, get_job_status
from db.database import get_db
from db.models import UserGeneratedProgram, User

router = APIRouter()


@router.post("/generate", response_model=JobResponse, status_code=202)
async def start_program_generation(
    request: ProgramGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start generating a workout program.
    Returns immediately with a job_id to track progress.

    Returns:
        202 Accepted with job information
    """
    # Verify user exists
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {request.user_id} not found")

    # Create job record
    job = create_job(
        db=db,
        user_id=str(request.user_id),
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        goal_category=request.goal_category,
        goal_raw=request.goal_raw,
        duration_weeks=request.duration_weeks,
        days_per_week=request.days_per_week,
        fitness_level=request.fitness_level
    )

    # Start background task
    background_tasks.add_task(
        generate_program_background,
        job_id=str(job.id),
        user_id=str(request.user_id),
        params={
            "name": user.name,
            "height_cm": request.height_cm,
            "weight_kg": request.weight_kg,
            "goal_category": request.goal_category,
            "goal_raw": request.goal_raw,
            "duration_weeks": request.duration_weeks,
            "days_per_week": request.days_per_week,
            "fitness_level": request.fitness_level
        }
    )

    print(f"[API] Started program generation job {job.id} for user {user.name}")

    return JobResponse(
        job_id=str(job.id),
        status="pending",
        message="Program generation started"
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_generation_status(
    job_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Check the status of a program generation job.

    Args:
        job_id: UUID of the generation job

    Returns:
        Job status information

    Raises:
        404: Job not found
    """
    job = get_job_status(db, str(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = JobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )

    if job.status == "completed" and job.program_id:
        response.program_id = str(job.program_id)
    elif job.status == "failed":
        response.error_message = job.error_message

    return response


@router.get("/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a generated program by ID.

    Args:
        program_id: Integer ID of the program

    Returns:
        Program information

    Raises:
        404: Program not found
    """
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    return ProgramResponse(
        id=str(program.id),
        name=program.name,
        description=program.description,
        duration_weeks=program.duration_weeks,
        created_at=program.created_at
    )
