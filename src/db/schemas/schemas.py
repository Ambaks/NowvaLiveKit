from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel


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
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


# -------------------------
# Schedule
# -------------------------
class ScheduleBase(BaseModel):
    scheduled_date: date
    completed: bool = False


class ScheduleRead(ScheduleBase):
    id: int

    class Config:
        orm_mode = True
