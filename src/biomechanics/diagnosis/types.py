from __future__ import annotations

from pydantic import BaseModel


class RepKinematicSummary(BaseModel):
    rep_number: int
    trunk_pitch_at_bottom: float
    knee_valgus_l: float
    knee_valgus_r: float
    ankle_df_l_max: float
    ankle_df_r_max: float
    hip_y_l_at_bottom: float
    hip_y_r_at_bottom: float
    knee_y_l_at_bottom: float
    knee_y_r_at_bottom: float
    stance_width_ratio: float
    foot_direction_angle_l: float
    foot_direction_angle_r: float
    depth_class_int: int
    hip_y_l_at_top: float = 0.0
    hip_y_r_at_top: float = 0.0
    knee_y_l_at_top: float = 0.0
    knee_y_r_at_top: float = 0.0


class SetFeatures(BaseModel):
    user_id: int
    set_id: str
    rep_count: int
    per_rep_kinematics: list[RepKinematicSummary]
    anthropometry: dict[str, float]
    rom: dict[str, float]


class DetectedSymptom(BaseModel):
    symptom_id: str
    severity: float
    contributing_reps: list[int]


class HypothesizedCause(BaseModel):
    cause_id: str
    tier: int
    score: float
    evidence_score: float
    prior: float
    implicated_by: list[str]
    parameter_delta: dict | None
    explanation: str


class RepScore(BaseModel):
    rep_number: int
    depth_score: float
    trunk_control_score: float
    knee_tracking_score: float
    symmetry_score: float
    composite_score: float


class SetScoreSummary(BaseModel):
    mean_score: float
    best_rep_number: int
    worst_rep_number: int
    trend_slope: float
    per_rep_scores: list[RepScore]


class DiagnosisResult(BaseModel):
    set_id: str
    detected_symptoms: list[DetectedSymptom]
    immediate_causes: list[HypothesizedCause]
    session_causes: list[HypothesizedCause]
    longterm_causes: list[HypothesizedCause]
    contextual_notes: list[HypothesizedCause]
    combined_perturbation: dict
    confidence: float
