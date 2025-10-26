from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    Text, ForeignKey, DECIMAL
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


# -------------------------
# Users
# -------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    height_cm = Column(DECIMAL(5, 2), nullable=True)  # Height in centimeters
    weight_kg = Column(DECIMAL(5, 2), nullable=True)  # Weight in kilograms
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_generated_programs = relationship("UserGeneratedProgram", back_populates="user", cascade="all, delete-orphan")
    partner_programs = relationship("PartnerProgram", back_populates="user", cascade="all, delete-orphan")
    progress_logs = relationship("ProgressLog", back_populates="user", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="user", cascade="all, delete-orphan")


# -------------------------
# Program Templates
# -------------------------
class ProgramTemplate(Base):
    __tablename__ = "program_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    duration_weeks = Column(Integer)
    level = Column(String(50))   # Beginner, Intermediate, Advanced
    goal = Column(String(100))   # Strength, Hypertrophy, Endurance
    created_at = Column(DateTime, default=datetime.utcnow)


# -------------------------
# User Generated Programs (LLM-created)
# -------------------------
class UserGeneratedProgram(Base):
    __tablename__ = "user_generated_programs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    duration_weeks = Column(Integer)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="user_generated_programs")
    workouts = relationship("Workout", back_populates="user_generated_program", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="user_generated_program", cascade="all, delete-orphan")


# -------------------------
# Partner Programs (Pre-built)
# -------------------------
class PartnerProgram(Base):
    __tablename__ = "partner_programs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    duration_weeks = Column(Integer)
    partner_name = Column(String(255))  # Name of the partner/creator
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="partner_programs")
    workouts = relationship("Workout", back_populates="partner_program", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="partner_program", cascade="all, delete-orphan")


# -------------------------
# Workouts
# -------------------------
class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    user_generated_program_id = Column(Integer, ForeignKey("user_generated_programs.id", ondelete="CASCADE"), nullable=True)
    partner_program_id = Column(Integer, ForeignKey("partner_programs.id", ondelete="CASCADE"), nullable=True)
    week_number = Column(Integer, nullable=True)  # Week 1, Week 2, etc.
    day_number = Column(Integer)  # Day 1, Day 2, etc.
    phase = Column(String(50), nullable=True)  # Build, Deload, Peak, Taper, etc.
    name = Column(String(255))
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user_generated_program = relationship("UserGeneratedProgram", back_populates="workouts")
    partner_program = relationship("PartnerProgram", back_populates="workouts")
    workout_exercises = relationship("WorkoutExercise", back_populates="workout", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="workout", cascade="all, delete-orphan")


# -------------------------
# Exercises (global catalog)
# -------------------------
class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))       # Strength, Cardio, Mobility
    muscle_group = Column(String(100))   # Chest, Legs, etc.
    description = Column(Text)

    # Relationships
    workout_exercises = relationship("WorkoutExercise", back_populates="exercise")


# -------------------------
# Workout_Exercises (join table)
# -------------------------
class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id = Column(Integer, primary_key=True, index=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"))
    exercise_id = Column(Integer, ForeignKey("exercises.id"))
    order_number = Column(Integer)  # Position in workout
    notes = Column(Text)

    # Relationships
    workout = relationship("Workout", back_populates="workout_exercises")
    exercise = relationship("Exercise", back_populates="workout_exercises")
    sets = relationship("Set", back_populates="workout_exercise", cascade="all, delete-orphan")


# -------------------------
# Sets (per exercise)
# -------------------------
class Set(Base):
    __tablename__ = "sets"

    id = Column(Integer, primary_key=True, index=True)
    workout_exercise_id = Column(Integer, ForeignKey("workout_exercises.id", ondelete="CASCADE"))
    set_number = Column(Integer)
    reps = Column(Integer)
    weight = Column(DECIMAL(6, 2))  # Actual weight (null initially, user fills in)
    intensity_percent = Column(DECIMAL(5, 2), nullable=True)  # % of 1RM (e.g., 75.00)
    rpe = Column(DECIMAL(3, 1))
    rest_seconds = Column(Integer)

    # Velocity-Based Training (VBT) fields
    velocity_threshold = Column(DECIMAL(4, 2), nullable=True)  # Target velocity (m/s)
    velocity_min = Column(DECIMAL(4, 2), nullable=True)        # Minimum velocity threshold
    velocity_max = Column(DECIMAL(4, 2), nullable=True)        # Maximum velocity threshold

    # Relationships
    workout_exercise = relationship("WorkoutExercise", back_populates="sets")
    progress_logs = relationship("ProgressLog", back_populates="set", cascade="all, delete-orphan")


# -------------------------
# Progress Logs
# -------------------------
class ProgressLog(Base):
    __tablename__ = "progress_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    set_id = Column(Integer, ForeignKey("sets.id", ondelete="CASCADE"))
    performed_reps = Column(Integer)
    performed_weight = Column(DECIMAL(6, 2))
    rpe = Column(DECIMAL(3, 1))
    completed_at = Column(DateTime, default=datetime.utcnow)

    # VBT tracking fields
    measured_velocity = Column(DECIMAL(4, 2), nullable=True)   # Actual bar velocity (m/s)
    velocity_loss = Column(DECIMAL(5, 2), nullable=True)       # % velocity loss in set

    # Relationships
    user = relationship("User", back_populates="progress_logs")
    set = relationship("Set", back_populates="progress_logs")


# -------------------------
# Schedule
# -------------------------
class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_generated_program_id = Column(Integer, ForeignKey("user_generated_programs.id", ondelete="CASCADE"), nullable=True)
    partner_program_id = Column(Integer, ForeignKey("partner_programs.id", ondelete="CASCADE"), nullable=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"))
    scheduled_date = Column(Date, nullable=False)
    completed = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="schedule")
    user_generated_program = relationship("UserGeneratedProgram", back_populates="schedule")
    partner_program = relationship("PartnerProgram", back_populates="schedule")
    workout = relationship("Workout", back_populates="schedule")


# -------------------------
# Program Generation Jobs (for FastAPI background tasks)
# -------------------------
class ProgramGenerationJob(Base):
    __tablename__ = "program_generation_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)  # pending, in_progress, completed, failed
    progress = Column(Integer, default=0)  # 0-100

    # Input parameters (original)
    height_cm = Column(DECIMAL(5, 2))
    weight_kg = Column(DECIMAL(5, 2))
    goal_category = Column(String(50))
    goal_raw = Column(String(500))
    duration_weeks = Column(Integer)
    days_per_week = Column(Integer)
    fitness_level = Column(String(50))

    # Enhanced input parameters (for comprehensive programming)
    session_duration = Column(Integer, nullable=True, default=60)      # Minutes per session
    injury_history = Column(Text, nullable=True, default='none')       # Injury descriptions
    age = Column(Integer, nullable=True)                               # User age
    sex = Column(String(10), nullable=True)                            # M/F/male/female
    specific_sport = Column(String(100), nullable=True, default='none') # Sport name or "none"
    has_vbt_capability = Column(Boolean, nullable=True, default=False) # VBT equipment available
    user_notes = Column(Text, nullable=True)                           # Any additional user notes/preferences

    # Output
    program_id = Column(Integer, ForeignKey('user_generated_programs.id', ondelete="SET NULL"), nullable=True)
    error_message = Column(String(1000), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User")
    program = relationship("UserGeneratedProgram")
