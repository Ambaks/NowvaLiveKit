from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    Text, ForeignKey, DECIMAL, ARRAY, Float, Index
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
    athlete_params = Column(JSONB, nullable=True)
    baseline = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="calibrations")


# -------------------------
# Biomechanics Tracking (retention + cue-effectiveness flywheel)
# -------------------------
class BiomechanicsSession(Base):
    __tablename__ = "biomechanics_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise = Column(String(50), nullable=False, default="squat")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    total_reps = Column(Integer, default=0, nullable=False)
    total_sets = Column(Integer, default=0, nullable=False)
    mean_session_score = Column(Float, nullable=True)  # Mean of set mean_scores, 0-1
    calibration_snapshot = Column(JSONB, nullable=True)  # Thresholds active during this session
    session_causes = Column(JSONB, nullable=True)  # Accumulated session-level causes from diagnosis

    # Relationships
    user = relationship("User")
    sets = relationship("BiomechanicsSet", back_populates="session", cascade="all, delete-orphan")
    reps = relationship("BiomechanicsRep", back_populates="session", cascade="all, delete-orphan")
    cue_events = relationship("CueEvent", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_biomech_sessions_user_started", "user_id", "started_at"),
    )


class BiomechanicsSet(Base):
    __tablename__ = "biomechanics_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    set_number = Column(Integer, nullable=False)
    rep_count = Column(Integer, nullable=False)
    mean_score = Column(Float, nullable=True)  # 0-1 composite for the set
    depth_score_avg = Column(Float, nullable=True)
    trunk_score_avg = Column(Float, nullable=True)
    knee_score_avg = Column(Float, nullable=True)
    symmetry_score_avg = Column(Float, nullable=True)
    trend_slope = Column(Float, nullable=True)  # Score trend across reps (fatigue signal)
    best_rep_number = Column(Integer, nullable=True)
    worst_rep_number = Column(Integer, nullable=True)
    diagnosis = Column(JSONB, nullable=True)  # Full diagnosis payload (symptoms, causes, perturbation)
    scoring = Column(JSONB, nullable=True)  # Full scoring payload incl. per_rep_scores
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("BiomechanicsSession", back_populates="sets")
    reps = relationship("BiomechanicsRep", back_populates="set")
    cue_events = relationship("CueEvent", back_populates="set")

    __table_args__ = (
        Index("ix_biomech_sets_user_created", "user_id", "created_at"),
    )


class BiomechanicsRep(Base):
    __tablename__ = "biomechanics_reps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    set_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_sets.id", ondelete="SET NULL"), nullable=True, index=True)  # Backfilled at set end
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rep_number = Column(Integer, nullable=False)
    set_number = Column(Integer, nullable=True)
    is_clean = Column(Boolean, default=False, nullable=False)
    depth_class = Column(Integer, nullable=True)
    max_depth_angle = Column(Float, nullable=True)
    # Per-dimension scores (backfilled from set diagnosis)
    composite_score = Column(Float, nullable=True)
    depth_score = Column(Float, nullable=True)
    trunk_control_score = Column(Float, nullable=True)
    knee_tracking_score = Column(Float, nullable=True)
    symmetry_score = Column(Float, nullable=True)
    # Full detail for ML training
    kinematics = Column(JSONB, nullable=True)  # RepKinematicSummary dump
    faults = Column(JSONB, nullable=True)  # faults_detailed list
    timing = Column(JSONB, nullable=True)  # duration/descent/ascent
    bottom_kpts = Column(JSONB, nullable=True)  # 17x3 keypoints at squat bottom
    standing_kpts = Column(JSONB, nullable=True)  # 17x3 keypoints at standing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("BiomechanicsSession", back_populates="reps")
    set = relationship("BiomechanicsSet", back_populates="reps")

    __table_args__ = (
        Index("ix_biomech_reps_user_created", "user_id", "created_at"),
    )


class CueEvent(Base):
    __tablename__ = "cue_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    set_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_sets.id", ondelete="SET NULL"), nullable=True)  # Backfilled at set end
    rep_id = Column(UUID(as_uuid=True), ForeignKey("biomechanics_reps.id", ondelete="SET NULL"), nullable=True)  # Rep during which the cue fired
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rep_number = Column(Integer, nullable=True)
    fault_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=True)  # mild / moderate / severe
    severity_score = Column(Float, nullable=True)
    cue_key = Column(String(100), nullable=True)
    cue_source = Column(String(30), default="cached_fault", nullable=False)  # cached_fault | llm_diagnosis
    cause_id = Column(String(50), nullable=True)  # Diagnosis cause behind an LLM cue
    message = Column(Text, nullable=True)
    parameter_delta = Column(JSONB, nullable=True)
    delivered = Column(Boolean, default=False, nullable=False)  # Cue audio actually played to the user
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Outcome columns — backfilled when the next rep / next set completes
    present_next_rep = Column(Boolean, nullable=True)
    severity_next_rep = Column(Float, nullable=True)
    severity_next_set = Column(Float, nullable=True)
    effective = Column(Boolean, nullable=True)  # Fault gone or less severe on next rep

    # Relationships
    session = relationship("BiomechanicsSession", back_populates="cue_events")
    set = relationship("BiomechanicsSet", back_populates="cue_events")
    rep = relationship("BiomechanicsRep")

    __table_args__ = (
        Index("ix_cue_events_user_fault", "user_id", "fault_type"),
    )


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
