"""
API endpoints for workout sessions, scheduling, and progress tracking
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timedelta

from db.database import get_db
from db.models import User
from db.schedule_utils import (
    get_todays_workout,
    get_upcoming_workouts,
    mark_workout_completed,
    reschedule_workout,
    get_user_schedule_range
)
from db.progress_utils import (
    log_completed_set,
    get_exercise_progress,
    get_personal_records,
    get_recent_activity_summary,
    get_workout_completion_rate
)
from auth.security import get_current_user
from ..schemas.workout_schemas import (
    SetCompletionRequest,
    SetCompletionResponse,
    GetTodaysWorkoutResponse,
    WorkoutDetail,
    GetScheduleResponse,
    ScheduleEntry,
    RescheduleRequest,
    RescheduleResponse,
    GetProgressResponse,
    ProgressEntry,
    GetPersonalRecordsResponse,
    PersonalRecord,
    ActivitySummary,
    CompletionRate
)

router = APIRouter(prefix="/workouts", tags=["workouts"])


def _check_user_access(current_user: User, user_id: str):
    """Raise 403 unless the authenticated user matches user_id (service accounts bypass)."""
    if getattr(current_user, "is_service", False):
        return
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")


# ===== TODAY'S WORKOUT =====

@router.get("/{user_id}/today", response_model=GetTodaysWorkoutResponse)
async def get_today_workout(user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Get today's scheduled workout for a user with full structure.
    Returns None if no workout is scheduled for today.
    """
    _check_user_access(current_user, user_id)
    try:
        workout_data = get_todays_workout(db, user_id)

        if not workout_data:
            return GetTodaysWorkoutResponse(
                has_workout=False,
                message="No workout scheduled for today"
            )

        # Convert to response model
        workout_detail = WorkoutDetail(**workout_data)

        return GetTodaysWorkoutResponse(
            has_workout=True,
            workout=workout_detail
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve today's workout: {str(e)}")


# ===== SCHEDULE =====

@router.get("/{user_id}/upcoming", response_model=GetScheduleResponse)
async def get_upcoming_schedule(
    user_id: str,
    days_ahead: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get upcoming scheduled workouts for the next N days.
    Default: 7 days
    """
    _check_user_access(current_user, user_id)
    try:
        workouts = get_upcoming_workouts(db, user_id, days_ahead)

        schedule_entries = [ScheduleEntry(**w) for w in workouts]

        return GetScheduleResponse(workouts=schedule_entries)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve schedule: {str(e)}")


@router.get("/{user_id}/schedule", response_model=GetScheduleResponse)
async def get_schedule_range(
    user_id: str,
    start_date: date,
    end_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get scheduled workouts within a date range.
    Useful for calendar views.
    """
    _check_user_access(current_user, user_id)
    try:
        if end_date < start_date:
            raise HTTPException(status_code=400, detail="end_date must be after start_date")

        workouts = get_user_schedule_range(db, user_id, start_date, end_date)

        schedule_entries = [ScheduleEntry(**w) for w in workouts]

        return GetScheduleResponse(workouts=schedule_entries)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve schedule: {str(e)}")


@router.post("/{user_id}/reschedule", response_model=RescheduleResponse)
async def reschedule_workout_endpoint(
    user_id: str,
    request: RescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Reschedule a workout to a different date.
    """
    _check_user_access(current_user, user_id)
    try:
        success = reschedule_workout(db, request.schedule_id, request.new_date)

        if not success:
            raise HTTPException(status_code=404, detail="Schedule entry not found")

        return RescheduleResponse(
            success=True,
            message="Workout rescheduled successfully",
            schedule_id=request.schedule_id,
            new_date=request.new_date.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reschedule workout: {str(e)}")


@router.post("/{user_id}/complete/{schedule_id}")
async def complete_workout(
    user_id: str,
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark a scheduled workout as completed.
    Usually called automatically by end_workout() in voice agent.
    """
    _check_user_access(current_user, user_id)
    try:
        success = mark_workout_completed(db, schedule_id)

        if not success:
            raise HTTPException(status_code=404, detail="Schedule entry not found")

        return {
            "success": True,
            "message": "Workout marked as completed",
            "schedule_id": schedule_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark workout complete: {str(e)}")


# ===== SET LOGGING =====

@router.post("/log-set", response_model=SetCompletionResponse)
async def log_set(
    request: SetCompletionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Log a completed set during an active workout.
    """
    _check_user_access(current_user, request.user_id)
    try:
        progress_log = log_completed_set(
            db=db,
            user_id=request.user_id,
            set_id=request.set_id,
            performed_reps=request.performed_reps,
            performed_weight=request.performed_weight,
            rpe=request.rpe,
            measured_velocity=request.measured_velocity,
            velocity_loss=request.velocity_loss
        )

        return SetCompletionResponse(
            success=True,
            progress_log_id=progress_log.id,
            message="Set logged successfully"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log set: {str(e)}")


# ===== PROGRESS =====

@router.get("/{user_id}/progress/{exercise_name}", response_model=GetProgressResponse)
async def get_exercise_progress_history(
    user_id: str,
    exercise_name: str,
    days_back: int = 90,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get progress history for a specific exercise.
    Shows all logged sets for that exercise over the specified time period.
    """
    _check_user_access(current_user, user_id)
    try:
        entries = get_exercise_progress(db, user_id, exercise_name, days_back)

        progress_entries = [ProgressEntry(**e) for e in entries]

        return GetProgressResponse(
            exercise_name=exercise_name,
            entries=progress_entries
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve progress: {str(e)}")


@router.get("/{user_id}/records", response_model=GetPersonalRecordsResponse)
async def get_user_records(
    user_id: str,
    exercise_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get personal records for a user.
    If exercise_name provided, returns PRs for that exercise only.
    Otherwise, returns PRs for all exercises.
    """
    _check_user_access(current_user, user_id)
    try:
        records = get_personal_records(db, user_id, exercise_name)

        pr_entries = [PersonalRecord(**r) for r in records]

        return GetPersonalRecordsResponse(records=pr_entries)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve records: {str(e)}")


@router.get("/{user_id}/activity", response_model=ActivitySummary)
async def get_activity(
    user_id: str,
    days_back: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a summary of recent workout activity.
    Includes total sets, reps, volume, exercises, and completion rate.
    """
    _check_user_access(current_user, user_id)
    try:
        summary = get_recent_activity_summary(db, user_id, days_back)

        return ActivitySummary(**summary)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve activity summary: {str(e)}")


@router.get("/{user_id}/completion-rate", response_model=CompletionRate)
async def get_completion(
    user_id: str,
    days_back: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get workout completion rate statistics.
    Shows scheduled vs. completed workouts over the specified period.
    """
    _check_user_access(current_user, user_id)
    try:
        stats = get_workout_completion_rate(db, user_id, days_back)

        return CompletionRate(**stats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve completion rate: {str(e)}")
