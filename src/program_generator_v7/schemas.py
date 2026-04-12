from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from program_generator_v5.schemas import (
    AthleteProfile,
    BuiltProgram,
    ProgramStrategy,
    VolumeAllocation,
)


class DirectiveAthlete(BaseModel):
    user_id: str
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    training_level: str = "intermediate"
    training_age_years: Optional[float] = None
    sport: Optional[str] = None
    training_season: Optional[str] = None
    games_per_week: int = 0
    competition_date: Optional[str] = None
    recovery_capacity: str = "normal"
    vbt_capability: bool = False


class GoalStack(BaseModel):
    primary_goal: str
    secondary_goals: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    time_horizon_weeks: int = 4


class HardConstraints(BaseModel):
    equipment_tier: int = 1
    max_session_minutes: int = 60
    days_per_week: int = 4
    injury_history: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_exercise_ids: list[str] = Field(default_factory=list)
    forbidden_movement_patterns: list[str] = Field(default_factory=list)
    fixed_schedule_notes: list[str] = Field(default_factory=list)
    exercise_blacklist_keywords: list[str] = Field(default_factory=list)


class SoftPreferences(BaseModel):
    liked_exercise_ids: list[str] = Field(default_factory=list)
    disliked_exercise_ids: list[str] = Field(default_factory=list)
    preferred_implements: list[str] = Field(default_factory=list)
    preferred_movement_patterns: list[str] = Field(default_factory=list)
    preferred_split_bias: Optional[str] = None
    novelty_tolerance: str = "moderate"
    aesthetic_emphasis: list[str] = Field(default_factory=list)
    note_tags: list[str] = Field(default_factory=list)


class ProgramRequest(BaseModel):
    duration_weeks: int
    days_per_week: int
    goal_raw: str
    session_duration_minutes: int = 60
    desired_split_bias: Optional[str] = None
    session_emphasis_requests: list[str] = Field(default_factory=list)
    phase_emphasis: Optional[str] = None
    user_notes: Optional[str] = None
    send_email: bool = False
    generation_mode: str = "standard"


class DerivedContext(BaseModel):
    effective_goal: str
    sport_interference: str = "low"
    fatigue_sensitivity: str = "normal"
    max_difficulty: int = 5
    movement_priorities: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    graph_coverage_warnings: list[str] = Field(default_factory=list)
    preferred_prehab_ids: list[str] = Field(default_factory=list)
    excluded_canonical_ids: list[str] = Field(default_factory=list)
    parsed_note_preferences: dict[str, Any] = Field(default_factory=dict)


class ProgramDirectiveV7(BaseModel):
    version: str = "7.0"
    athlete: DirectiveAthlete
    goal_stack: GoalStack
    hard_constraints: HardConstraints
    soft_preferences: SoftPreferences
    program_request: ProgramRequest
    derived_context: DerivedContext
    raw_request: dict[str, Any] = Field(default_factory=dict)
    should_use_llm_planner: bool = False


class KGExercise(BaseModel):
    canonical_id: str
    name: str
    family_id: str
    equipment_min: int
    difficulty: int
    movement_pattern: str
    exercise_type: str
    rotation_group: str
    bilateral: bool = True
    vbt_eligible: bool = False
    tags: list[str] = Field(default_factory=list)
    fatigue: dict[str, Any] = Field(default_factory=dict)
    stimulus: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGExerciseRelation(BaseModel):
    src_id: str
    relation_type: str
    dst_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class KGSessionRole(BaseModel):
    role_id: str
    label: str
    session_type: str
    goal: str
    required_patterns: list[str] = Field(default_factory=list)
    optional_patterns: list[str] = Field(default_factory=list)
    target_muscles: list[str] = Field(default_factory=list)
    fatigue_budget: str = "moderate"
    slot_budget: int = 5
    sequencing_hints: list[str] = Field(default_factory=list)
    max_duration_minutes: int = 60
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGProgressionTemplate(BaseModel):
    family_id: str
    session_role: str
    goal_phase: str
    training_level: str
    default_sets_by_week: list[int] = Field(default_factory=list)
    rep_range: tuple[int, int] = (6, 10)
    target_rpe_range: tuple[float, float] = (7.0, 9.0)
    anchor_duration_weeks: int = 4
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGBlockTemplate(BaseModel):
    template_id: str
    goal: str
    phase: str
    duration_weeks: int
    days_per_week: int
    season_context: str
    periodization_model: str
    session_role_ids: list[str] = Field(default_factory=list)
    template: dict[str, Any] = Field(default_factory=dict)


class KGConstraintRule(BaseModel):
    rule_id: str
    rule_type: str
    subject_type: str
    subject_key: str
    config: dict[str, Any] = Field(default_factory=dict)


class KGSnapshot(BaseModel):
    version_id: str
    version_label: str
    exercises: dict[str, KGExercise] = Field(default_factory=dict)
    relations: list[KGExerciseRelation] = Field(default_factory=list)
    session_roles: dict[str, KGSessionRole] = Field(default_factory=dict)
    progression_templates: list[KGProgressionTemplate] = Field(default_factory=list)
    block_templates: list[KGBlockTemplate] = Field(default_factory=list)
    constraint_rules: list[KGConstraintRule] = Field(default_factory=list)


class SessionRoleAssignment(BaseModel):
    role_id: str
    label: str
    session_type: str
    target_muscles: list[str] = Field(default_factory=list)
    required_patterns: list[str] = Field(default_factory=list)
    optional_patterns: list[str] = Field(default_factory=list)
    fatigue_budget: str = "moderate"
    slot_budget: int = 5
    max_duration_minutes: int = 60
    rationale: str = ""


class SessionSlot(BaseModel):
    slot_id: str
    week_number: int
    day_number: int
    day_label: str
    session_type: str
    session_role_id: str
    slot_kind: str
    required_pattern: Optional[str] = None
    target_muscles: list[str] = Field(default_factory=list)
    preferred_family_ids: list[str] = Field(default_factory=list)
    preferred_canonical_ids: list[str] = Field(default_factory=list)
    min_sets: int = 2
    target_sets: int = 3
    max_sets: int = 5
    intensity_bucket: str = "moderate"
    fatigue_budget: str = "moderate"
    order_hint: int = 0
    notes: list[str] = Field(default_factory=list)
    rationale: str = ""


class WeekSessionSkeleton(BaseModel):
    week_number: int
    day_number: int
    day_label: str
    session_type: str
    session_role: SessionRoleAssignment
    slots: list[SessionSlot] = Field(default_factory=list)


class BlockWeekPlan(BaseModel):
    week_number: int
    phase_name: str
    goal_phase: str
    week_focus: str = ""
    deload: bool = False
    fatigue_budget: str = "moderate"
    anchor_family_ids: list[str] = Field(default_factory=list)
    movement_quotas: dict[str, int] = Field(default_factory=dict)
    session_roles: list[SessionRoleAssignment] = Field(default_factory=list)
    sessions: list[WeekSessionSkeleton] = Field(default_factory=list)
    rationale: str = ""


class BlockPlanV7(BaseModel):
    directive: ProgramDirectiveV7
    profile: AthleteProfile
    strategy: ProgramStrategy
    volume_allocation: VolumeAllocation
    weeks: list[BlockWeekPlan] = Field(default_factory=list)
    phase_sequence: list[str] = Field(default_factory=list)
    anchor_family_preferences: dict[str, list[str]] = Field(default_factory=dict)
    planner_notes: list[str] = Field(default_factory=list)
    llm_used: bool = False


class CandidateScore(BaseModel):
    canonical_id: str
    total: float
    components: dict[str, float] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)


class AssemblyTraceEntry(BaseModel):
    week_number: int
    day_number: int
    slot_id: str
    slot_kind: str = ""
    session_role_id: str
    selected_canonical_id: str
    selected_family_id: str
    selected_sets: int
    score: float
    candidate_scores: list[CandidateScore] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    rule_id: str
    severity: str
    scope: str
    message: str
    week: Optional[int] = None
    session: Optional[int] = None
    exercise_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    repair_ops: list[str] = Field(default_factory=list)


class RepairOperation(BaseModel):
    op_id: str
    op_type: str
    description: str
    week: Optional[int] = None
    session: Optional[int] = None
    source_exercise_id: Optional[str] = None
    target_exercise_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CritiqueIssue(BaseModel):
    severity: str
    message: str
    rationale: str
    scope: str
    week: Optional[int] = None
    session: Optional[int] = None


class CritiqueRepairSuggestion(BaseModel):
    op_type: str
    reason: str
    target_scope: str
    target_id: Optional[str] = None
    target_week: Optional[int] = None
    target_session: Optional[int] = None
    target_exercise_id: Optional[str] = None
    replacement_family_id: Optional[str] = None
    replacement_canonical_id: Optional[str] = None
    confidence: float = 0.0
    do_not_apply_if: list[str] = Field(default_factory=list)


class CritiqueV7(BaseModel):
    overall_grade: str = "B"
    issues: list[CritiqueIssue] = Field(default_factory=list)
    repair_suggestions: list[CritiqueRepairSuggestion] = Field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""


class ProgramArtifactV7(BaseModel):
    directive: ProgramDirectiveV7
    kg_version: str
    profile: AthleteProfile
    strategy: ProgramStrategy
    volume_allocation: VolumeAllocation
    block_plan: BlockPlanV7
    program: BuiltProgram
    assembly_trace: list[AssemblyTraceEntry] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    repair_log: list[RepairOperation] = Field(default_factory=list)
    critic: Optional[CritiqueV7] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = "v7.0"
