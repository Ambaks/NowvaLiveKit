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
    day_number = Column(Integer)  # Day 1, Day 2, etc.
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
    weight = Column(DECIMAL(6, 2))
    rpe = Column(DECIMAL(3, 1))
    rest_seconds = Column(Integer)

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
