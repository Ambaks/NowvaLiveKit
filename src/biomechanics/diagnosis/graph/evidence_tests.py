"""Pure evidence-test functions for the diagnosis hypothesis engine.

Each test function takes (features, anthro, rom, set_summary) and returns a
float in [0, 1] representing how strongly the evidence supports that cause
being active. set_summary carries set-level score trends and is None for
single-rep sets.

Expected-value functions compute the personalized baseline for a symptom given
the athlete's anthropometry, so severity is measured relative to what's
biomechanically expected for THEIR body.
"""

from __future__ import annotations

import math

from ..types import RepKinematicSummary, SetScoreSummary
from .parameter_deltas import dorsi_driven_targets, expected_trunk_lean_geometric


def expected_knee_valgus_baseline(anthro: dict) -> float:
    hip_width = anthro.get("hip_width", 0.30)
    return min(3.0, (hip_width - 0.25) * 30.0)


def expected_hip_symmetry(anthro: dict) -> float:
    return 0.0


def expected_depth_zero(anthro: dict) -> float:
    return 0.0


def test_femur_torso_ratio(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    ratio = anthro.get("femur_torso_ratio", 1.0)
    if ratio <= 1.0:
        return 0.0
    return _clamp((ratio - 1.0) / 0.2)


def test_narrow_stance(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    depth_signal = 0.0
    if features.depth_class_int < 3:
        depth_signal = (3 - features.depth_class_int) / 3.0

    lean_signal = 0.0
    if features.trunk_pitch_at_bottom > 40.0:
        lean_signal = _clamp((features.trunk_pitch_at_bottom - 40.0) / 20.0)

    symptom_severity = max(depth_signal, lean_signal)
    if symptom_severity <= 0.0:
        return 0.0

    dorsi_capacity = rom.get("dorsiflexion_drop", 35.0)
    ideal_ratio, _ = dorsi_driven_targets(dorsi_capacity, anthro)

    current_ratio = features.stance_width_ratio
    if current_ratio >= ideal_ratio:
        return 0.0

    gap_factor = _clamp((ideal_ratio - current_ratio) / 0.5)
    return symptom_severity * gap_factor


def test_narrow_foot_angle(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)
    _, target_toe_out = dorsi_driven_targets(dorsiflexion_capacity, anthro)
    ideal_minimum = max(15.0, target_toe_out)
    if avg_foot_angle >= ideal_minimum:
        return 0.0
    return _clamp((ideal_minimum - avg_foot_angle) / ideal_minimum)


def test_bracing_failure(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    expected_lean = expected_trunk_lean_geometric(anthro)
    actual_lean = features.trunk_pitch_at_bottom

    excess_lean = actual_lean - expected_lean
    if excess_lean <= 5.0:
        return 0.0

    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)
    ankle_is_limited = ankle_df_max >= (dorsiflexion_capacity * 0.9)

    if ankle_is_limited:
        return _clamp(excess_lean / 20.0) * 0.3

    stance_narrow = test_narrow_stance(features, anthro, rom, set_summary)
    lean_discount = stance_narrow * 0.6
    return _clamp(excess_lean / 15.0) * (1.0 - lean_discount)


def test_knee_track_cue(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 4.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    foot_angle_adequate = avg_foot_angle >= 15.0

    base_evidence = _clamp((max_valgus - 4.0) / 10.0)
    return base_evidence * (0.8 if foot_angle_adequate else 0.4)


def test_weight_shift(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 1.5:
        return 0.0
    return _clamp((asymmetry_cm - 1.5) / 3.5)


def test_depth_unfamiliarity(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    if features.depth_class_int >= 3:
        return 0.0

    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)
    ankle_ok = ankle_df_max < (dorsiflexion_capacity * 0.85)

    hip_rom = rom.get("avg_depth", 120.0)
    hip_ok = hip_rom > 100.0

    if ankle_ok and hip_ok:
        base = 0.8
    elif ankle_ok or hip_ok:
        base = 0.4
    else:
        base = 0.1

    stance_narrow = test_narrow_stance(features, anthro, rom, set_summary)
    foot_narrow = test_narrow_foot_angle(features, anthro, rom, set_summary)
    mechanical_explanation = max(stance_narrow, foot_narrow)
    return base * (1.0 - mechanical_explanation * 0.8)


def test_progressive_degradation(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    if set_summary is None or len(set_summary.per_rep_scores) < 3:
        return 0.0

    decline_per_rep = -set_summary.trend_slope
    if decline_per_rep <= 0.01:
        return 0.0
    return _clamp((decline_per_rep - 0.01) / 0.04)


def test_limited_ankle_df(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)

    if dorsiflexion_capacity <= 0:
        return 0.5

    utilization = ankle_df_max / dorsiflexion_capacity
    if utilization < 0.85:
        return 0.0
    return _clamp((utilization - 0.85) / 0.15)


def test_limited_hip_flexion(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    hip_rom_peak = rom.get("avg_depth", 120.0)

    if hip_rom_peak > 110.0:
        return 0.0
    if hip_rom_peak < 80.0:
        return 0.9

    return _clamp((110.0 - hip_rom_peak) / 30.0)


def test_weak_hip_abductors(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 5.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    stance_adequate = features.stance_width_ratio >= 0.8
    foot_angle_adequate = avg_foot_angle >= 15.0

    if stance_adequate and foot_angle_adequate:
        return _clamp((max_valgus - 5.0) / 8.0)
    return _clamp((max_valgus - 5.0) / 12.0) * 0.5


def test_foot_arch_collapse(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 5.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0

    if avg_foot_angle >= 20.0:
        return _clamp((max_valgus - 5.0) / 8.0) * 0.7
    return 0.1


def test_unilateral_hip(
    features: RepKinematicSummary,
    anthro: dict,
    rom: dict,
    set_summary: SetScoreSummary | None,
) -> float:
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 2.0:
        return 0.0
    return _clamp((asymmetry_cm - 2.0) / 4.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
