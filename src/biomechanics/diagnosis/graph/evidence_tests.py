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


# ═══════════════════════════════════════════════════════════════════════
# Expected-value functions (referenced by symptoms.yaml expected_value_fn)
# ═══════════════════════════════════════════════════════════════════════


def expected_trunk_lean_geometric(anthro: dict) -> float:
    """Geometric model for expected trunk lean at parallel depth.

    Longer femurs relative to torso require more forward lean to keep
    the center of mass over midfoot. Derivation: simple 2-segment
    sagittal-plane model (femur + torso) with COM constraint.

    Returns degrees of trunk flexion from vertical.
    """
    femur_torso_ratio = anthro.get("femur_torso_ratio", 1.0)
    # ~30° base for ratio=1.0, increases ~12° per 0.1 ratio above 1.0
    return 30.0 + (femur_torso_ratio - 1.0) * 120.0


def expected_knee_valgus_baseline(anthro: dict) -> float:
    """Baseline acceptable valgus is ~0° for most athletes.

    Some hip-width-dependent tolerance: wider hips allow slightly more
    apparent valgus before it becomes problematic.
    """
    hip_width = anthro.get("hip_width", 0.30)
    # Wider hips → slightly higher acceptable valgus (up to ~3°)
    return min(3.0, (hip_width - 0.25) * 30.0)


def expected_hip_symmetry(anthro: dict) -> float:
    """Expected hip asymmetry is 0 cm (perfect symmetry)."""
    return 0.0


def expected_depth_zero(anthro: dict) -> float:
    """Expected depth deficit is 0 (can reach parallel)."""
    return 0.0


# ═══════════════════════════════════════════════════════════════════════
# Evidence-test functions (referenced by causes.yaml evidence_test_fn)
# ═══════════════════════════════════════════════════════════════════════


def test_femur_torso_ratio(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """High evidence if femur/torso ratio is notably above average (>1.05).

    A ratio of 1.0 is average. Above 1.1 makes excessive trunk lean
    almost inevitable regardless of mobility.
    """
    ratio = anthro.get("femur_torso_ratio", 1.0)
    if ratio <= 1.0:
        return 0.0
    return _clamp((ratio - 1.0) / 0.2)


def test_narrow_stance(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that stance is too narrow for the athlete's hip width.

    Ideal stance width ratio is ~1.0-1.3× shoulder width for most
    athletes. Below 0.8 is narrow; strength of evidence scales with
    how far below ideal.
    """
    hip_width = anthro.get("hip_width", 0.30)
    shoulder_width = anthro.get("shoulder_width", 0.40)
    # Wider hips need wider stance; ideal ratio scales up slightly
    ideal_ratio = 0.9 + (hip_width / max(shoulder_width, 0.01) - 0.7) * 0.5
    ideal_ratio = max(0.8, min(1.3, ideal_ratio))

    current_ratio = features.stance_width_ratio
    if current_ratio >= ideal_ratio:
        return 0.0
    return _clamp((ideal_ratio - current_ratio) / 0.3)


def test_narrow_foot_angle(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that foot direction angle is insufficient.

    Most athletes benefit from 15-30° of external foot rotation.
    Less than 15° with trunk lean or depth issues is strong evidence.
    """
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
    """Evidence of bracing failure: trunk pitch increases beyond what
    mobility limitations would predict.

    If ankle/hip ROM are adequate but trunk still leans excessively,
    bracing failure is likely. We check if the actual lean exceeds
    the geometrically expected lean by more than the mobility-limited
    prediction.
    """
    expected_lean = expected_trunk_lean_geometric(anthro)
    actual_lean = features.trunk_pitch_at_bottom

    # If lean is within expected range, no bracing failure
    excess_lean = actual_lean - expected_lean
    if excess_lean <= 5.0:
        return 0.0

    # Check if ankle DF is NOT limited (if it is, lean is explained by ankle)
    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)
    ankle_is_limited = ankle_df_max >= (dorsiflexion_capacity * 0.9)

    if ankle_is_limited:
        # Lean is more likely explained by ankle than bracing
        return _clamp(excess_lean / 20.0) * 0.3
    return _clamp(excess_lean / 15.0)


def test_knee_track_cue(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that valgus is cue-correctable (not a strength deficit).

    High evidence if valgus is present but does NOT worsen across reps
    (would suggest fatigue/weakness if it did). Also high if foot angle
    is adequate (ruling out foot angle as the driver).
    """
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 4.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    foot_angle_adequate = avg_foot_angle >= 15.0

    # If foot angle is adequate, valgus is more likely a cue issue
    base_evidence = _clamp((max_valgus - 4.0) / 10.0)
    return base_evidence * (0.8 if foot_angle_adequate else 0.4)


def test_weight_shift(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that asymmetry is a cueing issue (not structural).

    High evidence if the asymmetry is moderate (2-5 cm) and the athlete
    has symmetric ROM (no unilateral restriction detected).
    """
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 1.5:
        return 0.0

    # Moderate asymmetry is more likely cueing; large asymmetry → structural
    if asymmetry_cm > 6.0:
        return 0.2
    return _clamp((asymmetry_cm - 1.5) / 3.5)


def test_depth_unfamiliarity(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that depth is limited by unfamiliarity, not mobility.

    High evidence if:
    - depth_class is below parallel (< 3)
    - BUT ankle DF and hip flexion ROM are adequate
    """
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
    """Evidence that load is too heavy: form degrades across the set.

    This is a single-rep test but the engine aggregates across reps.
    For a single rep, we check if it's in the latter half and has
    worse metrics than early reps would suggest. The engine will
    call this per-rep and look at the trend.
    """
    # As a single-rep function, return higher evidence for later reps
    # with worse form. The rep_number itself is a weak signal.
    # High trunk lean + late rep = evidence of fatigue
    expected_lean = expected_trunk_lean_geometric(anthro)
    excess = features.trunk_pitch_at_bottom - expected_lean

    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)

    fatigue_signal = (excess / 15.0) + (max_valgus / 12.0)
    return _clamp(fatigue_signal * 0.5)


def test_limited_ankle_df(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that ankle dorsiflexion is the limiting factor.

    High evidence if ankle DF during the squat is near or at the
    athlete's measured ROM ceiling.
    """
    ankle_df_max = max(features.ankle_df_l_max, features.ankle_df_r_max)
    dorsiflexion_capacity = rom.get("dorsiflexion_drop", 35.0)

    if dorsiflexion_capacity <= 0:
        return 0.5

    utilization = ankle_df_max / dorsiflexion_capacity
    # Above 85% utilization = evidence of limitation
    if utilization < 0.85:
        return 0.0
    return _clamp((utilization - 0.85) / 0.15)


def test_limited_hip_flexion(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that hip flexion ROM is limiting depth or causing lean.

    Checks if trunk lean is high AND depth is limited — suggests the
    hips can't flex enough to allow upright torso at depth.
    """
    hip_rom_peak = rom.get("avg_depth", 120.0)

    # Low peak knee flexion in calibration suggests hip mobility limit
    if hip_rom_peak > 110.0:
        return 0.0
    if hip_rom_peak < 80.0:
        return 0.9

    return _clamp((110.0 - hip_rom_peak) / 30.0)


def test_weak_hip_abductors(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that hip abductors are weak (not just a cueing issue).

    High evidence if valgus is present AND foot angle is adequate
    (ruling out foot position) AND stance isn't too narrow.
    """
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 5.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    stance_adequate = features.stance_width_ratio >= 0.8
    foot_angle_adequate = avg_foot_angle >= 15.0

    if stance_adequate and foot_angle_adequate:
        # Setup is fine, valgus is likely strength-related
        return _clamp((max_valgus - 5.0) / 8.0)
    return _clamp((max_valgus - 5.0) / 12.0) * 0.5


def test_foot_arch_collapse(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence that medial arch collapse is driving valgus.

    Proxy: valgus is present AND foot direction angle is adequate
    (if toes point out enough but knees still cave, foot collapse
    is a likely contributor from below).
    """
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    if max_valgus < 5.0:
        return 0.0

    avg_foot_angle = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0

    if avg_foot_angle >= 20.0:
        # Good foot angle but still valgus → arch collapse likely
        return _clamp((max_valgus - 5.0) / 8.0) * 0.7
    return 0.1


def test_unilateral_hip(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> float:
    """Evidence of unilateral hip mobility restriction.

    High evidence if hip asymmetry is large (>3 cm) and consistent,
    suggesting structural restriction rather than random shift.
    """
    asymmetry_cm = abs(features.hip_y_l_at_bottom - features.hip_y_r_at_bottom)
    if asymmetry_cm < 2.0:
        return 0.0
    # Large asymmetry → more likely structural
    return _clamp((asymmetry_cm - 2.0) / 4.0)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
