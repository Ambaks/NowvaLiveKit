"""
Portable Database Module for Fitness/Workout Tracking
This module can be imported into any project that needs the same database structure.
"""

from .database import engine, SessionLocal, get_db, init_db
from .models import (
    Base,
    User,
    ProgramTemplate,
    UserGeneratedProgram,
    PartnerProgram,
    Workout,
    Exercise,
    WorkoutExercise,
    Set,
    ProgressLog,
    Schedule
)

__all__ = [
    # Database utilities
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",

    # Models
    "Base",
    "User",
    "ProgramTemplate",
    "UserGeneratedProgram",
    "PartnerProgram",
    "Workout",
    "Exercise",
    "WorkoutExercise",
    "Set",
    "ProgressLog",
    "Schedule",
]

__version__ = "1.0.0"
