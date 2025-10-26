"""
Pydantic schemas for structured program generation using OpenAI's structured outputs.
These schemas guarantee valid JSON responses from the LLM.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class SetSchema(BaseModel):
    """Schema for a single set within an exercise"""
    set_number: int = Field(ge=1, description="Set number (1, 2, 3...)")
    reps: int = Field(ge=1, le=50, description="Target repetitions")
    intensity_percent: float = Field(ge=0, le=100, description="Percentage of 1RM (e.g., 75.0 for 75%)")
    rir: int = Field(ge=0, le=5, description="Reps in reserve (0=failure, 3=easy)")
    rest_seconds: int = Field(ge=30, le=600, description="Rest time between sets in seconds")
    notes: Optional[str] = Field(default=None, description="Optional set-specific notes")

    # VBT (Velocity-Based Training) fields - only populated if VBT is enabled
    velocity_threshold: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=3.0,
        description="Target bar velocity in m/s (VBT only, for power/Olympic lifts)"
    )
    velocity_min: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=3.0,
        description="Minimum acceptable velocity in m/s (stop set if below this)"
    )
    velocity_max: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=3.0,
        description="Maximum target velocity in m/s"
    )


class ExerciseSchema(BaseModel):
    """Schema for an exercise within a workout"""
    exercise_name: str = Field(description="Full exercise name (e.g., 'Barbell Back Squat')")
    category: str = Field(description="Exercise category: Strength, Hypertrophy, or Power")
    muscle_group: str = Field(description="Primary muscle group (e.g., Quads, Chest, Back)")
    order: int = Field(ge=1, description="Exercise order in the workout (1=first, 2=second, etc.)")
    sets: List[SetSchema] = Field(min_length=1, max_length=10, description="All sets for this exercise")
    notes: Optional[str] = Field(
        default=None,
        description="Exercise-specific notes (setup, safety, technique cues, VBT instructions)"
    )


class WorkoutSchema(BaseModel):
    """Schema for a single workout day"""
    day_number: int = Field(ge=1, le=7, description="Day number within the week (1-7)")
    name: str = Field(description="Workout name (e.g., 'Upper Push', 'Lower Power')")
    description: str = Field(description="Brief description of workout focus and goals")
    exercises: List[ExerciseSchema] = Field(
        min_length=1,
        max_length=12,
        description="All exercises in this workout, in order"
    )


class WeekSchema(BaseModel):
    """Schema for a single week of training"""
    week_number: int = Field(ge=1, description="Week number in the program")
    phase: str = Field(description="Training phase: Build, Deload, Peak, or Taper")
    workouts: List[WorkoutSchema] = Field(description="All workouts for this week")
    notes: Optional[str] = Field(
        default=None,
        description="Week-specific notes (e.g., 'This is a deload week, reduce volume by 40%')"
    )


class ProgramMetadataSchema(BaseModel):
    """Schema for high-level program metadata (generated first, before weeks)"""
    program_name: str = Field(description="Descriptive program name")
    description: str = Field(description="Program overview and what it achieves")
    duration_weeks: int = Field(ge=1, le=52, description="Total program duration in weeks")
    goal: str = Field(description="Primary training goal (Strength, Hypertrophy, Power)")
    progression_strategy: str = Field(
        description="Detailed explanation of how intensity and volume progress week-to-week"
    )
    overall_notes: str = Field(
        description="Important notes about warm-ups, form, recovery, deloads, etc."
    )


class FullProgramSchema(BaseModel):
    """Complete program schema (for reference - not used in generation)"""
    program_name: str
    description: str
    duration_weeks: int
    goal: str
    progression_strategy: str
    overall_notes: str
    weeks: List[WeekSchema]


class ProgramBatchSchema(BaseModel):
    """Schema for generating 4-week batches of training

    Used for Cache-Augmented Generation (CAG):
    - Generates 4 weeks at a time instead of 1 week (4x faster)
    - System prompt gets cached by OpenAI (3,000 tokens)
    - Batch 1: Weeks 1-4 (cache miss, full cost) - includes metadata
    - Batch 2: Weeks 5-8 (cache hit, 50% cost + faster) - metadata optional
    - Batch 3: Weeks 9-12 (cache hit, 50% cost + faster) - metadata optional
    """
    program_name: str = Field(description="Descriptive program name (required for first batch)")
    description: str = Field(description="Program overview and what it achieves (required for first batch)")
    duration_weeks: int = Field(ge=1, le=52, description="Total program duration in weeks (required for first batch)")
    goal: str = Field(description="Primary training goal: Strength, Hypertrophy, or Power (required for first batch)")
    progression_strategy: str = Field(
        description="Detailed explanation of how intensity and volume progress week-to-week (required for first batch)"
    )
    overall_notes: str = Field(
        description="Important notes about warm-ups, form, recovery, deloads, etc. (required for first batch)"
    )

    # VBT metadata (optional, only if has_vbt_capability = true)
    vbt_enabled: Optional[bool] = Field(
        default=False,
        description="Whether this program uses velocity-based training"
    )
    vbt_setup_notes: Optional[str] = Field(
        default=None,
        description="VBT equipment setup and usage instructions (if vbt_enabled)"
    )

    # Program-level metadata
    deload_schedule: Optional[str] = Field(
        default=None,
        description="Which weeks are deloads and how to implement them"
    )
    injury_accommodations: Optional[str] = Field(
        default=None,
        description="List of exercise substitutions made due to injury history"
    )

    weeks: List[WeekSchema] = Field(
        min_length=1,
        max_length=4,
        description="Up to 4 consecutive weeks of training in this batch"
    )
