from datetime import datetime, date
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# -------------------------
# User
# -------------------------
class UserBase(BaseModel):
    name: str
    email: str
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Program Templates
# -------------------------
class ProgramTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_weeks: Optional[int] = None
    level: Optional[str] = None
    goal: Optional[str] = None


class ProgramTemplateRead(ProgramTemplateBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Sets
# -------------------------
class SetBase(BaseModel):
    set_number: int
    reps: Optional[int]
    weight: Optional[float]
    rpe: Optional[float]
    rest_seconds: Optional[int]


class SetRead(SetBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Exercises
# -------------------------
class ExerciseBase(BaseModel):
    name: str
    category: Optional[str]
    muscle_group: Optional[str]
    description: Optional[str]


class ExerciseRead(ExerciseBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Workout Exercises
# -------------------------
class WorkoutExerciseBase(BaseModel):
    order_number: int
    notes: Optional[str]


class WorkoutExerciseRead(WorkoutExerciseBase):
    id: int
    exercise: ExerciseRead
    sets: List[SetRead] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Workouts
# -------------------------
class WorkoutBase(BaseModel):
    name: Optional[str]
    description: Optional[str]
    day_number: Optional[int]


class WorkoutRead(WorkoutBase):
    id: int
    workout_exercises: List[WorkoutExerciseRead] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# User Generated Programs
# -------------------------
class UserGeneratedProgramBase(BaseModel):
    name: str
    description: Optional[str]
    duration_weeks: Optional[int]
    is_public: bool = False


class UserGeneratedProgramRead(UserGeneratedProgramBase):
    id: int
    workouts: List[WorkoutRead] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Partner Programs
# -------------------------
class PartnerProgramBase(BaseModel):
    name: str
    description: Optional[str]
    duration_weeks: Optional[int]
    partner_name: Optional[str]
    is_public: bool = False


class PartnerProgramRead(PartnerProgramBase):
    id: int
    workouts: List[WorkoutRead] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Progress Logs
# -------------------------
class ProgressLogBase(BaseModel):
    performed_reps: Optional[int]
    performed_weight: Optional[float]
    rpe: Optional[float]


class ProgressLogRead(ProgressLogBase):
    id: int
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Schedule
# -------------------------
class ScheduleBase(BaseModel):
    scheduled_date: date
    completed: bool = False


class ScheduleRead(ScheduleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
