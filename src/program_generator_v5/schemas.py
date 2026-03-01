"""
V5 Program Generator — All Pydantic models and enums.
Every other file in this package imports from here.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class EquipmentTier(int, Enum):
    TIER_1 = 1  # Barbell + rack + bench + pull-up bar + floor space
    TIER_2 = 2  # + Dumbbells
    TIER_3 = 3  # + Bands


class MuscleRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    STABILIZER = "stabilizer"


class ExerciseType(str, Enum):
    HEAVY_COMPOUND = "heavy_compound"   # Squat, Bench, Deadlift, OHP
    LIGHT_COMPOUND = "light_compound"   # Rows, Lunges, Pull-ups, Hip Thrusts
    ISOLATION = "isolation"             # Curls, Lateral Raises, Extensions
    POWER = "power"                     # Cleans, Snatches, Explosive movements
    PLYOMETRIC = "plyometric"           # Jumps, Bounds, Clap Push-ups


class MovementPattern(str, Enum):
    HORIZONTAL_PUSH = "horizontal_push"   # Bench press, push-ups
    HORIZONTAL_PULL = "horizontal_pull"   # Rows
    VERTICAL_PUSH = "vertical_push"       # OHP, DB press
    VERTICAL_PULL = "vertical_pull"       # Pull-ups, lat pulldown
    HIP_HINGE = "hip_hinge"              # Deadlifts, RDL, Good mornings
    SQUAT = "squat"                       # Squats, leg press
    LUNGE = "lunge"                       # Lunges, split squats, step-ups
    ISOLATION_PUSH = "isolation_push"     # Tricep extensions, lateral raises
    ISOLATION_PULL = "isolation_pull"     # Curls, face pulls, rear delt work
    CORE = "core"                         # Planks, rollouts, crunches
    POWER_LOWER = "power_lower"           # Cleans, jumps, explosive squats
    POWER_UPPER = "power_upper"           # Push press, explosive rows, clap push-ups
    CARRY = "carry"                       # Farmer's carries, overhead carries
    ROTATION = "rotation"                 # Woodchops, rotational throws


class MuscleGroup(str, Enum):
    # Chest
    CHEST = "chest"             # Pectoralis major (general)
    UPPER_CHEST = "upper_chest" # Clavicular head
    LOWER_CHEST = "lower_chest" # Sternal head

    # Back
    LATS = "lats"
    UPPER_BACK = "upper_back"   # Rhomboids, mid traps
    TRAPS = "traps"             # Upper trapezius
    ERECTORS = "erectors"       # Spinal erectors

    # Shoulders
    FRONT_DELTS = "front_delts"
    SIDE_DELTS = "side_delts"
    REAR_DELTS = "rear_delts"

    # Arms
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"

    # Lower Body
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ADDUCTORS = "adductors"

    # Core
    ABS = "abs"
    OBLIQUES = "obliques"


# ─────────────────────────────────────────────────────────────────────────────
# EXERCISE LIBRARY MODELS
# ─────────────────────────────────────────────────────────────────────────────

class MuscleActivation(BaseModel):
    muscle: MuscleGroup
    role: MuscleRole
    # How much a set of this exercise "counts" toward volume for this muscle.
    # Primary = 1.0, Secondary = 0.5, Stabilizer = 0.0
    volume_credit: float = Field(ge=0.0, le=1.0)


class Exercise(BaseModel):
    id: str                                     # Unique snake_case ID
    name: str                                   # Display name
    equipment_tier: EquipmentTier               # Minimum tier required
    exercise_type: ExerciseType
    movement_pattern: MovementPattern
    muscle_activations: list[MuscleActivation]

    # Prescription constraints
    min_reps: int                               # Lowest reasonable rep count
    max_reps: int                               # Highest reasonable rep count
    min_sets_per_session: int = 2
    max_sets_per_session: int = 5               # Hard cap per session

    # Fatigue profile
    is_axial_loading: bool = False              # Spinal compression load
    systemic_fatigue: str = "moderate"          # "low", "moderate", "high"
    grip_intensive: bool = False

    # Difficulty & suitability
    difficulty: int = Field(ge=1, le=5)         # 1=beginner, 5=advanced
    requires_proficiency: bool = False          # True for Olympic lifts, etc.
    bilateral: bool = True                      # False for unilateral

    # SFR — higher is better for hypertrophy
    sfr_rating: float = Field(ge=1.0, le=10.0, default=5.0)

    # Coaching
    cues: list[str] = []
    common_mistakes: list[str] = []

    # Variation / rotation
    rotation_group: str                         # Interchangeable exercises share group
    variation_tags: list[str] = []             # ["incline", "close_grip", "pause"]


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — ATHLETE PROFILE
# ─────────────────────────────────────────────────────────────────────────────

class AthleteProfile(BaseModel):
    user_id: str
    name: str

    # Demographics
    age: Optional[int] = None
    sex: Optional[str] = None
    body_weight_kg: Optional[float] = None

    # Training context
    training_goal: str                          # "hypertrophy", "strength", "power"
    sport: Optional[str] = None                 # "basketball", "mma", etc.
    training_level: str                         # "beginner", "intermediate", "advanced"
    training_age_years: Optional[float] = None

    # Program parameters
    program_duration_weeks: int
    training_days_per_week: int                 # 2–6
    session_duration_minutes: int = 60

    # Equipment
    equipment_tier: EquipmentTier

    # Constraints
    injuries: list[dict] = []                   # [{"area": "left_shoulder", "avoid": [...]}]
    exercises_to_avoid: list[str] = []
    exercises_to_include: list[str] = []

    # Recovery
    recovery_capacity: str = "normal"           # "low", "normal", "high"

    # Emphasis
    weak_points: list[str] = []                 # Muscle group names to prioritize

    # Derived (computed by Layer 1)
    effective_goal: str = ""                    # After sport mapping
    sport_adjustments: Optional[dict] = None
    available_exercises: list[str] = []         # Exercise IDs after filtering
    exercise_coverage_warnings: list[str] = []  # Muscle groups with sparse options


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — STRATEGY
# ─────────────────────────────────────────────────────────────────────────────

class SessionTemplate(BaseModel):
    day_label: str                              # "Upper A", "Lower B", "Push", etc.
    session_type: str = ""                      # "upper_a", "lower_b", "push", "full_body"
    muscle_groups: list[MuscleGroup]
    required_movement_patterns: list[MovementPattern]
    optional_movement_patterns: list[MovementPattern]
    max_exercises: int = 7
    max_duration_minutes: int = 60
    is_primary: bool = True                     # Primary sessions get more volume


class SplitTemplate(BaseModel):
    split_id: str
    name: str
    sessions_per_week: list[SessionTemplate]
    suitable_levels: list[str]
    suitable_goals: list[str]


class WeekProfile(BaseModel):
    week_number: int
    mesocycle_number: int                       # 1-indexed mesocycle
    week_in_mesocycle: int                      # Position within mesocycle (1-4)
    phase_name: str                             # "Introduction", "Building", "Overreaching", "Deload"
    volume_multiplier: float                    # Relative to mesocycle baseline
    intensity_modifier: str                     # "light", "moderate", "moderate_heavy", "heavy", "deload"
    rpe_range: tuple[float, float]
    rir_range: tuple[int, int]
    is_deload: bool = False
    notes: str = ""


class ProgramStrategy(BaseModel):
    split: SplitTemplate
    week_profiles: list[WeekProfile]
    periodization_model: str                    # "volume_ramp", "linear_intensity", "concurrent"
    volume_modifier: float = 1.0               # Global scaling from sport adjustments
    emphasis_muscles: list[MuscleGroup] = []
    deemphasis_muscles: list[MuscleGroup] = []
    mesocycle_count: int                        # How many mesocycles in the program


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3 — VOLUME ALLOCATION
# ─────────────────────────────────────────────────────────────────────────────

class SessionVolumeTarget(BaseModel):
    day_label: str
    muscle_volumes: dict[str, int]              # {"chest": 4, "triceps": 3, ...}
    total_sets: int
    movement_pattern_requirements: dict[str, int]  # {"horizontal_push": 4, ...}


class WeekVolumeAllocation(BaseModel):
    week_number: int
    is_deload: bool
    sessions: list[SessionVolumeTarget]
    weekly_totals: dict[str, float]             # Total volume credit per muscle
    below_mev: list[str] = []                  # MUST be empty for non-deload weeks
    above_mrv: list[str] = []                  # MUST always be empty


class VolumeAllocation(BaseModel):
    weeks: list[WeekVolumeAllocation]


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4 — PROGRAM BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class PrescribedSet(BaseModel):
    set_number: int
    reps: int
    rpe: Optional[float] = None
    rir: Optional[int] = None
    intensity_percent: Optional[float] = None
    rest_seconds: int
    tempo: Optional[str] = None
    notes: str = ""


class PrescribedExercise(BaseModel):
    exercise_id: str
    exercise_name: str
    exercise_type: ExerciseType
    movement_pattern: MovementPattern
    sets: list[PrescribedSet]
    total_sets: int
    muscle_contributions: dict[str, float]      # {"chest": 3.0, "triceps": 1.5}
    superset_group: Optional[str] = None
    order_in_session: int
    rationale: str = ""


class BuiltWorkout(BaseModel):
    day_number: int
    day_label: str
    session_type: str = ""
    exercises: list[PrescribedExercise]
    total_sets: int
    estimated_duration_minutes: int
    volume_check: dict[str, float]
    volume_delivered: dict[str, float] = {}     # Alias: same as volume_check
    warmup_notes: str = ""


class BuiltWeek(BaseModel):
    week_number: int
    mesocycle: int = 1
    phase: str = ""
    phase_name: str = ""
    workouts: list[BuiltWorkout]
    weekly_volume_actual: dict[str, float]
    weekly_volume_target: dict[str, float] = {}
    volume_adherence: dict[str, float] = {}     # actual/target ratio


class MutationLog(BaseModel):
    mutations_attempted: int = 0
    mutations_applied: int = 0
    mutations_rejected: int = 0
    mutations_rolled_back: int = 0


class BuiltProgram(BaseModel):
    profile: AthleteProfile
    strategy: ProgramStrategy
    volume_allocation: Optional[VolumeAllocation] = None
    weeks: list[BuiltWeek]
    mutation_log: list[dict] = []
    unique_exercises_used: int = 0
    total_sets: int = 0
    total_workouts: int = 0
    generation_time_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# MUTATION MODELS (for program editing / repair engine)
# ─────────────────────────────────────────────────────────────────────────────

class MutationRequest(BaseModel):
    mutation_type: str                          # "swap_exercise", "add_exercise", "remove_exercise",
                                                # "add_sets", "remove_sets", "reorder_session",
                                                # "move_exercise", "replace_prescription"
    week_number: Optional[int] = None
    session_day: Optional[int] = None
    exercise_id: Optional[str] = None           # Target exercise to mutate
    new_exercise_id: Optional[str] = None       # Replacement exercise (for swaps/adds)
    new_sets: Optional[int] = None              # For set-count adjustments
    new_order: Optional[list[str]] = None       # For reorders (exercise_id list)
    target_session_day: Optional[int] = None    # Destination session (for move_exercise)
    source: str = "unknown"                     # "validator_auto_fix", "llm_week_review", "llm_full_review"
    rationale: str = ""


class MutationResult(BaseModel):
    success: bool
    mutation_type: str
    description: str
    volume_before: dict[str, float] = {}
    volume_after: dict[str, float] = {}
    constraint_violations: list[str] = []
    rollback_applied: bool = False
