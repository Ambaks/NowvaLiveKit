"""
Programs Router
Endpoints for program generation and status checking
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID

from api.models.requests import ProgramGenerationRequest, ProgramUpdateRequest
from api.models.responses import (
    JobResponse,
    JobStatusResponse,
    ProgramResponse,
    ProgramListResponse,
    ProgramSummary,
    UpdateStatusResponse
)
from api.services.program_generator_v2 import generate_program_background  # V2: Structured outputs
from api.services.program_updater import (
    update_program_background,
    validate_program_change_with_llm,
    _get_current_program_as_json
)
from api.services.job_manager import create_job, get_job_status
from db.database import get_db
from db.models import UserGeneratedProgram, User
from db.program_utils import get_program_summary_list

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
        fitness_level=request.fitness_level,
        age=request.age,
        sex=request.sex,
        session_duration=request.session_duration,
        injury_history=request.injury_history,
        specific_sport=request.specific_sport,
        has_vbt_capability=request.has_vbt_capability,
        user_notes=request.user_notes
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
            "fitness_level": request.fitness_level,
            "age": request.age,
            "sex": request.sex,
            "session_duration": request.session_duration,
            "injury_history": request.injury_history,
            "specific_sport": request.specific_sport,
            "has_vbt_capability": request.has_vbt_capability,
            "user_notes": request.user_notes
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


@router.get("/list/{user_id}", response_model=ProgramListResponse)
async def list_user_programs(
    user_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get a list of all programs for a user.

    Args:
        user_id: UUID of the user

    Returns:
        List of program summaries

    Raises:
        404: User not found
    """
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Get program summaries
    summaries = get_program_summary_list(db, str(user_id))

    return ProgramListResponse(
        programs=[ProgramSummary(**s) for s in summaries],
        total_count=len(summaries)
    )


@router.post("/{program_id}/update", response_model=JobResponse, status_code=202)
async def start_program_update(
    program_id: int,
    request: ProgramUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start updating an existing workout program.
    Returns immediately with a job_id to track progress.

    Args:
        program_id: ID of the program to update
        request: Update request with change description and user profile

    Returns:
        202 Accepted with job information

    Raises:
        404: Program not found
    """
    # Verify program exists and get its user_id
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        raise HTTPException(status_code=404, detail=f"Program {program_id} not found")

    user_id = str(program.user_id)

    # Create job record
    job = create_job(
        db=db,
        user_id=user_id,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        goal_category="update",  # Special marker for update jobs
        goal_raw=request.change_request,
        duration_weeks=program.duration_weeks,  # Current duration
        days_per_week=0,  # Not applicable for updates
        fitness_level=request.fitness_level,
        age=request.age,
        sex=request.sex,
        session_duration=None,
        injury_history=None,
        specific_sport=None,
        has_vbt_capability=False,
        user_notes=f"UPDATE: {request.change_request}"
    )

    # Build user profile for update
    user_profile = {
        "age": request.age,
        "sex": request.sex,
        "height_cm": request.height_cm,
        "weight_kg": request.weight_kg,
        "fitness_level": request.fitness_level
    }

    # Start background task
    background_tasks.add_task(
        update_program_background,
        job_id=str(job.id),
        user_id=user_id,
        program_id=program_id,
        change_request=request.change_request,
        user_profile=user_profile
    )

    print(f"[API] Started program update job {job.id} for program {program_id}")

    return JobResponse(
        job_id=str(job.id),
        status="pending",
        message="Program update started"
    )


@router.get("/update-status/{job_id}", response_model=UpdateStatusResponse)
async def get_update_status(
    job_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Check the status of a program update job.

    Args:
        job_id: UUID of the update job

    Returns:
        Update job status information including diff

    Raises:
        404: Job not found
    """
    job = get_job_status(db, str(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = UpdateStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )

    if job.status == "completed" and job.program_id:
        response.program_id = str(job.program_id)

        # Extract diff from metadata if available
        if hasattr(job, 'metadata') and job.metadata:
            import json
            try:
                metadata = json.loads(job.metadata) if isinstance(job.metadata, str) else job.metadata
                response.diff = metadata.get("diff", [])
            except:
                pass

    elif job.status == "failed":
        response.error_message = job.error_message

    return response


@router.post("/{program_id}/validate")
async def validate_program_change(
    program_id: int,
    request: ProgramUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Validate a proposed program change without applying it.
    Returns whether the change is risky and suggests alternatives.

    Args:
        program_id: ID of the program to validate against
        request: Update request with change description and user profile

    Returns:
        Validation result with warning and alternative if risky

    Raises:
        404: Program not found
    """
    # Verify program exists
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        raise HTTPException(status_code=404, detail=f"Program {program_id} not found")

    # Get current program structure
    current_program = _get_current_program_as_json(db, program_id)

    if not current_program:
        raise HTTPException(status_code=500, detail="Failed to load program")

    # Build user profile
    user_profile = {
        "age": request.age,
        "sex": request.sex,
        "height_cm": request.height_cm,
        "weight_kg": request.weight_kg,
        "fitness_level": request.fitness_level
    }

    # Run validation
    validation_result = await validate_program_change_with_llm(
        current_program=current_program,
        change_request=request.change_request,
        user_profile=user_profile
    )

    return validation_result
