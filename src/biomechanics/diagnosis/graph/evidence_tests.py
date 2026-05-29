"""Pure evidence-test functions for the diagnosis hypothesis engine.

Each test function takes (features, anthro, rom) and returns a float in [0, 1]
representing how strongly the evidence supports that cause being active.

Expected-value functions compute the personalized baseline for a symptom given
the athlete's anthropometry, so severity is measured relative to what's
biomechanically expected for THEIR body.
"""

from __future__ import annotations

import math

from ..types import RepKinematicSummary


def expected_trunk_lean_geometric(anthro: dict) -> float:
    femur_torso_ratio = anthro.get("femur_torso_ratio", 1.0)
    return 30.0 + (femur_torso_ratio - 1.0) * 120.0


def expected_knee_valgus_baseline(anthro: dict) -> float:
    hip_width = anthro.get("hip_width", 0.30)
    return min(3.0, (hip_width - 0.25) * 30.0)


def expected_hip_symmetry(anthro: dict) -> float:
    return 0.0


def expected_depth_zero(anthro: dict) -> float:
    return 0.0


def test_femur_torso_ratio(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    ratio = anthro.get("femur_torso_ratio", 1.0)
    if ratio <= 1.0:
        return 0.0
    return _clamp((ratio - 1.0) / 0.2)


def test_narrow_stance(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    hip_width = anthro.get("hip_width", 0.30)
    shoulder_width = anthro.get("shoulder_width", 0.40)
    ideal_ratio = 0.9 + (hip_width / max(shoulder_width, 0.01) - 0.7) * 0.5
    ideal_ratio = max(0.8, min(1.3, ideal_ratio))

    current_ratio = features.stance_width_ratio
    if current_ratio >= ideal_ratio:
        return 0.0
    return _clamp((ideal_ratio - current_ratio) / 0.3)


def test_narrow_foot_angle(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    ideal_minimum = 15.0
    if avg_foot_angle >= ideal_minimum:
        return 0.0
    return _clamp((ideal_minimum - avg_foot_angle) / 15.0)


def test_bracing_failure(
    features: RepKinematicSummary, anthro: dict, rom: dict
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
    return _clamp(excess_lean / 15.0)


def test_knee_track_cue(
    features: RepKinematicSummary, anthro: dict, rom: dict
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
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 1.5:
        return 0.0

    if asymmetry_cm > 6.0:
        return 0.2
    return _clamp((asymmetry_cm - 1.5) / 3.5)


def test_depth_unfamiliarity(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    if features.depth_class_int >= 3:
        return 0.0

    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)
    ankle_ok = ankle_df_max < (dorsiflexion_capacity * 0.85)

    hip_rom = rom.get("avg_depth", 120.0)
    hip_ok = hip_rom > 100.0

    if ankle_ok and hip_ok:
        return 0.8
    if ankle_ok or hip_ok:
        return 0.4
    return 0.1


def test_progressive_degradation(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    expected_lean = expected_trunk_lean_geometric(anthro)
    excess = features.trunk_pitch_at_bottom - expected_lean

    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)

    fatigue_signal = (excess / 15.0) + (max_valgus / 12.0)
    return _clamp(fatigue_signal * 0.5)


def test_limited_ankle_df(
    features: RepKinematicSummary, anthro: dict, rom: dict
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
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    hip_rom_peak = rom.get("avg_depth", 120.0)

    if hip_rom_peak > 110.0:
        return 0.0
    if hip_rom_peak < 80.0:
        return 0.9

    return _clamp((110.0 - hip_rom_peak) / 30.0)


def test_weak_hip_abductors(
    features: RepKinematicSummary, anthro: dict, rom: dict
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
    features: RepKinematicSummary, anthro: dict, rom: dict
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
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 2.0:
        return 0.0
    return _clamp((asymmetry_cm - 2.0) / 4.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
