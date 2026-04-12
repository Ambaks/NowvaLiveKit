from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    Text, ForeignKey, DECIMAL, ARRAY
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    age = Column(Integer, nullable=True)  # User age
    sex = Column(String(10), nullable=True)  # "male" or "female"
    extra_info = Column(Text, nullable=True)  # Free-form user-volunteered context captured during voice onboarding
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_generated_programs = relationship("UserGeneratedProgram", back_populates="user", cascade="all, delete-orphan")
    partner_programs = relationship("PartnerProgram", back_populates="user", cascade="all, delete-orphan")
    progress_logs = relationship("ProgressLog", back_populates="user", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="user", cascade="all, delete-orphan")
    calibrations = relationship("UserCalibration", back_populates="user", cascade="all, delete-orphan")


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
    generator_version = Column(String(20), nullable=False, default="v5")
    artifact_ref = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="user_generated_programs")
    workouts = relationship("Workout", back_populates="user_generated_program", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="user_generated_program", cascade="all, delete-orphan")
    v7_artifact = relationship("ProgramArtifactV7Record", back_populates="program", uselist=False, cascade="all, delete-orphan")


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
    canonical_id = Column(String(255), nullable=True, unique=True, index=True)
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
    canonical_exercise_id = Column(String(255), nullable=True, index=True)
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

    # V6: Advanced set type
    set_type = Column(String(20), nullable=True, default="standard")  # standard, cluster, rest_pause, myo_rep, drop_set, back_off, amrap, wave

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

    # Schedule modification fields
    skipped = Column(Boolean, default=False, nullable=False)
    skipped_at = Column(DateTime, nullable=True)
    skip_reason = Column(String(500), nullable=True)
    is_deload = Column(Boolean, default=False, nullable=False)
    deload_intensity_modifier = Column(DECIMAL(4, 2), nullable=True, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    generator_version = Column(String(20), nullable=False, default="v5")

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
    training_season = Column(String(50), nullable=True)                # off_season, pre_season, in_season, post_season
    games_per_week = Column(Integer, nullable=True, default=0)         # Games/competitions per week
    equipment_tier = Column(Integer, nullable=True, default=1)         # 1=Basic, 2=Full Gym, 3=Specialty

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


# -------------------------
# V7 Knowledge Graph
# -------------------------
class KnowledgeGraphVersion(Base):
    __tablename__ = "kg_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_label = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    exercises = relationship("KnowledgeGraphExercise", back_populates="version", cascade="all, delete-orphan")
    relations = relationship("KnowledgeGraphExerciseRelation", back_populates="version", cascade="all, delete-orphan")
    session_roles = relationship("KnowledgeGraphSessionRole", back_populates="version", cascade="all, delete-orphan")
    progression_templates = relationship("KnowledgeGraphProgressionTemplate", back_populates="version", cascade="all, delete-orphan")
    block_templates = relationship("KnowledgeGraphBlockTemplate", back_populates="version", cascade="all, delete-orphan")
    constraint_rules = relationship("KnowledgeGraphConstraintRule", back_populates="version", cascade="all, delete-orphan")


class KnowledgeGraphExercise(Base):
    __tablename__ = "kg_exercises"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    family_id = Column(String(255), nullable=False, index=True)
    equipment_min = Column(Integer, nullable=False, default=1)
    difficulty = Column(Integer, nullable=False, default=3)
    movement_pattern = Column(String(100), nullable=False, index=True)
    exercise_type = Column(String(100), nullable=False)
    rotation_group = Column(String(255), nullable=False, index=True)
    bilateral = Column(Boolean, nullable=False, default=True)
    vbt_eligible = Column(Boolean, nullable=False, default=False)
    tags = Column(ARRAY(String), nullable=True)
    fatigue_json = Column(JSONB, nullable=True)
    stimulus_json = Column(JSONB, nullable=True)
    constraints_json = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)

    version = relationship("KnowledgeGraphVersion", back_populates="exercises")


class KnowledgeGraphExerciseRelation(Base):
    __tablename__ = "kg_exercise_relations"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    src_id = Column(String(255), nullable=False, index=True)
    relation_type = Column(String(100), nullable=False, index=True)
    dst_id = Column(String(255), nullable=False, index=True)
    payload_json = Column(JSONB, nullable=True)

    version = relationship("KnowledgeGraphVersion", back_populates="relations")


class KnowledgeGraphSessionRole(Base):
    __tablename__ = "kg_session_roles"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(String(255), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    session_type = Column(String(100), nullable=False, index=True)
    goal = Column(String(50), nullable=False, index=True)
    config_json = Column(JSONB, nullable=False)

    version = relationship("KnowledgeGraphVersion", back_populates="session_roles")


class KnowledgeGraphProgressionTemplate(Base):
    __tablename__ = "kg_progression_templates"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id = Column(String(255), nullable=False, index=True)
    session_role = Column(String(255), nullable=False, index=True)
    goal_phase = Column(String(100), nullable=False, index=True)
    training_level = Column(String(50), nullable=False, index=True)
    template_json = Column(JSONB, nullable=False)

    version = relationship("KnowledgeGraphVersion", back_populates="progression_templates")


class KnowledgeGraphBlockTemplate(Base):
    __tablename__ = "kg_block_templates"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(255), nullable=False, index=True)
    goal = Column(String(50), nullable=False, index=True)
    phase = Column(String(100), nullable=False, index=True)
    duration_weeks = Column(Integer, nullable=False)
    days_per_week = Column(Integer, nullable=False)
    season_context = Column(String(50), nullable=False, default="standard")
    periodization_model = Column(String(100), nullable=False)
    template_json = Column(JSONB, nullable=False)

    version = relationship("KnowledgeGraphVersion", back_populates="block_templates")


class KnowledgeGraphConstraintRule(Base):
    __tablename__ = "kg_constraint_rules"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("kg_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String(255), nullable=False, index=True)
    rule_type = Column(String(100), nullable=False, index=True)
    subject_type = Column(String(100), nullable=False)
    subject_key = Column(String(255), nullable=False, index=True)
    config_json = Column(JSONB, nullable=False)

    version = relationship("KnowledgeGraphVersion", back_populates="constraint_rules")


class ProgramArtifactV7Record(Base):
    __tablename__ = "program_artifacts_v7"

    id = Column(Integer, primary_key=True, index=True)
    user_generated_program_id = Column(Integer, ForeignKey("user_generated_programs.id", ondelete="CASCADE"), nullable=False, unique=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("program_generation_jobs.id", ondelete="SET NULL"), nullable=True)
    directive_json = Column(JSONB, nullable=False)
    block_plan_json = Column(JSONB, nullable=False)
    assembly_trace_json = Column(JSONB, nullable=False)
    validation_json = Column(JSONB, nullable=False)
    critic_json = Column(JSONB, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    kg_version = Column(String(100), nullable=False)
    prompt_version = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    program = relationship("UserGeneratedProgram", back_populates="v7_artifact")


# -------------------------
# Schedule Change History (Undo System)
# -------------------------
class ScheduleChangeHistory(Base):
    __tablename__ = "schedule_change_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    change_type = Column(String(50), nullable=False)  # move, swap, skip, add_rest, repeat, deload, clear, reschedule
    description = Column(Text, nullable=False)  # Human-readable description
    affected_schedule_ids = Column(ARRAY(Integer))  # List of schedule IDs affected
    before_state = Column(JSONB, nullable=False)  # Full snapshot before change
    after_state = Column(JSONB, nullable=False)   # Full snapshot after change
    created_at = Column(DateTime, default=datetime.utcnow)
    function_name = Column(String(100))  # Function that made the change
    is_undone = Column(Boolean, default=False)
    undone_at = Column(DateTime, nullable=True)
    undo_change_id = Column(Integer, ForeignKey("schedule_change_history.id"), nullable=True)

    # Relationships
    user = relationship("User")


# -------------------------
# Training Load Metrics (Deload System)
# -------------------------
class TrainingLoadMetrics(Base):
    __tablename__ = "training_load_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start_date = Column(Date, nullable=False)
    week_end_date = Column(Date, nullable=False)

    # Volume metrics
    total_sets = Column(Integer, default=0)
    total_reps = Column(Integer, default=0)
    total_volume_kg = Column(DECIMAL(10, 2), default=0)

    # Intensity metrics
    avg_rpe = Column(DECIMAL(3, 1))
    high_rpe_sets = Column(Integer, default=0)

    # Velocity metrics
    avg_velocity = Column(DECIMAL(4, 2))
    velocity_decline_percent = Column(DECIMAL(5, 2))

    # Fatigue indicators
    fatigue_score = Column(DECIMAL(5, 2))
    deload_recommended = Column(Boolean, default=False)

    calculated_at = Column(DateTime, default=datetime.utcnow)
    workouts_completed = Column(Integer, default=0)

    # Relationships
    user = relationship("User")


# -------------------------
# Deload History
# -------------------------
class UserCalibration(Base):
    __tablename__ = "user_calibrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movement_pattern = Column(String(50), nullable=False)  # "squat", "hip_hinge", etc.
    peaks = Column(JSONB, nullable=False)
    thresholds = Column(JSONB, nullable=False)
    calibration_reps = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="calibrations")


class DeloadHistory(Base):
    __tablename__ = "deload_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start_date = Column(Date, nullable=False)
    week_end_date = Column(Date, nullable=False)
    intensity_modifier = Column(DECIMAL(4, 2), default=0.7)
    trigger_reason = Column(Text)
    fatigue_score_at_trigger = Column(DECIMAL(5, 2))
    applied = Column(Boolean, default=False)
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
