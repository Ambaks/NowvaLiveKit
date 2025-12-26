"""
Pydantic schemas for workout and schedule API endpoints
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date, datetime


# ===== SET COMPLETION =====

class SetCompletionRequest(BaseModel):
    """Request to log a completed set during workout"""
    user_id: str = Field(..., description="User UUID")
    set_id: int = Field(..., description="Set ID from the workout")
    performed_reps: int = Field(..., description="Actual reps completed")
    performed_weight: Optional[float] = Field(None, description="Actual weight used (kg or lbs)")
    rpe: Optional[float] = Field(None, description="Rate of Perceived Exertion (1-10)", ge=1, le=10)
    measured_velocity: Optional[float] = Field(None, description="Bar velocity in m/s")
    velocity_loss: Optional[float] = Field(None, description="Velocity loss percentage")
    notes: Optional[str] = Field(None, description="Optional notes about the set")


class SetCompletionResponse(BaseModel):
    """Response after logging a set"""
    success: bool
    progress_log_id: int
    message: str


# ===== WORKOUT SESSION =====

class StartWorkoutRequest(BaseModel):
    """Request to start a workout session"""
    user_id: str = Field(..., description="User UUID")


class StartWorkoutResponse(BaseModel):
    """Response when starting a workout"""
    success: bool
    message: str
    schedule_id: Optional[int] = None
    workout_id: Optional[int] = None
    workout_name: Optional[str] = None
    first_exercise: Optional[str] = None


class EndWorkoutRequest(BaseModel):
    """Request to end a workout session"""
    user_id: str = Field(..., description="User UUID")


class EndWorkoutResponse(BaseModel):
    """Response when ending a workout"""
    success: bool
    message: str
    total_sets: int
    completed_sets: int
    duration_minutes: Optional[float] = None


# ===== SCHEDULE =====

class ScheduleEntry(BaseModel):
    """A single scheduled workout entry"""
    schedule_id: int
    scheduled_date: str  # ISO format date
    completed: bool
    workout_id: int
    workout_name: str
    week_number: Optional[int]
    day_number: int
    phase: Optional[str]
    description: Optional[str] = None


class GetScheduleResponse(BaseModel):
    """Response for schedule queries"""
    workouts: List[ScheduleEntry]


class RescheduleRequest(BaseModel):
    """Request to reschedule a workout"""
    schedule_id: int = Field(..., description="Schedule entry ID")
    new_date: date = Field(..., description="New scheduled date")


class RescheduleResponse(BaseModel):
    """Response after rescheduling"""
    success: bool
    message: str
    schedule_id: int
    new_date: str  # ISO format


# ===== WORKOUT DETAILS =====

class SetDetail(BaseModel):
    """Detailed information about a set"""
    set_id: int
    set_number: int
    reps: int
    intensity_percent: Optional[float]
    rpe: Optional[float]
    rest_seconds: int
    velocity_threshold: Optional[float]
    velocity_min: Optional[float]
    velocity_max: Optional[float]


class ExerciseDetail(BaseModel):
    """Detailed information about an exercise in a workout"""
    workout_exercise_id: int
    exercise_id: int
    exercise_name: str
    muscle_group: Optional[str]
    category: Optional[str]
    order_number: int
    notes: Optional[str]
    sets: List[SetDetail]


class WorkoutDetail(BaseModel):
    """Complete workout structure"""
    schedule_id: int
    workout_id: int
    workout_name: str
    description: Optional[str]
    week_number: Optional[int]
    day_number: int
    phase: Optional[str]
    exercises: List[ExerciseDetail]


class GetTodaysWorkoutResponse(BaseModel):
    """Response for today's workout"""
    has_workout: bool
    workout: Optional[WorkoutDetail] = None
    message: Optional[str] = None


# ===== PROGRESS =====

class ProgressEntry(BaseModel):
    """A progress log entry"""
    date: str  # ISO format
    completed_at: str  # ISO format with time
    reps: int
    weight: Optional[float]
    rpe: Optional[float]
    velocity: Optional[float]
    velocity_loss: Optional[float]
    set_number: int
    workout_name: str
    week_number: Optional[int]
    day_number: int


class GetProgressResponse(BaseModel):
    """Response for progress history"""
    exercise_name: str
    entries: List[ProgressEntry]


class PersonalRecord(BaseModel):
    """A personal record"""
    exercise_name: str
    max_weight: float
    reps: int
    estimated_1rm: Optional[float]
    date: str  # ISO format


class GetPersonalRecordsResponse(BaseModel):
    """Response for personal records"""
    records: List[PersonalRecord]


class ActivitySummary(BaseModel):
    """Summary of recent activity"""
    total_sets: int
    total_reps: int
    total_volume: float
    unique_exercises: int
    workouts_completed: int
    average_rpe: Optional[float]
    period_days: int


class CompletionRate(BaseModel):
    """Workout completion statistics"""
    total_scheduled: int
    total_completed: int
    completion_rate: float
    missed_workouts: int
    period_days: int
