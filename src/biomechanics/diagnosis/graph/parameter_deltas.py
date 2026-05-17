"""Parameter-delta functions for tier-1 (cue-correctable) causes.

Each function returns a dict compatible with whatif_solve's perturbation
parameter: {"joint.axis": delta_radians, ...}

Special key "__foot_target_delta" is extracted by the engine and passed
as the foot_target_delta array to whatif_solve (not mixed into the
perturbation dict).

All angular values are in RADIANS (whatif_solve operates in radians).
"""

from __future__ import annotations

import math

from ..types import RepKinematicSummary


def delta_widen_stance(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Widen stance by moving feet laterally outward.

    Returns foot_target_delta: [dLx, dLy, dLz, dRx, dRy, dRz]
    where dLx is negative (left foot moves left) and dRx is positive
    (right foot moves right) in the skeleton's coordinate frame.
    """
    current_ratio = features.stance_width_ratio
    shoulder_width = anthro.get("shoulder_width", 0.40)
    target_ratio = max(1.0, current_ratio + 0.15)
    width_increase_per_side = (target_ratio - current_ratio) * shoulder_width / 2.0
    width_increase_per_side = min(width_increase_per_side, 0.05)

    return {
        "__foot_target_delta": [
            -width_increase_per_side, 0.0, 0.0,
            width_increase_per_side, 0.0, 0.0,
        ]
    }


def delta_widen_foot_angle(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Increase foot external rotation (turn toes out more).

    Target: bring foot direction to ~20-25° if currently below that.
    Uses ankle ry axis (external rotation of the foot).
    """
    avg_current = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0
    target_angle = 22.0
    delta_degrees = max(0.0, min(target_angle - avg_current, 12.0))
    delta_radians = math.radians(delta_degrees)

    return {
        "L_ankle.ry": delta_radians,
        "R_ankle.ry": -delta_radians,
    }


def delta_brace_trunk(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Reduce trunk flexion to simulate better bracing.

    A well-braced trunk resists forward collapse. We perturb trunk
    extension by a small amount (~3-5°) to show the corrected posture.
    """
    expected_lean = 30.0 + (anthro.get("femur_torso_ratio", 1.0) - 1.0) * 120.0
    excess_lean = features.trunk_pitch_at_bottom - expected_lean
    correction_degrees = min(excess_lean * 0.4, 8.0)
    correction_degrees = max(correction_degrees, 3.0)

    return {
        "trunk.rx": -math.radians(correction_degrees),
    }


def delta_knees_out(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Push knees out via hip external rotation.

    Corrects valgus by increasing hip abduction/external rotation,
    which tracks the knee outward over the toes.
    """
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    correction_degrees = min(max_valgus * 0.5, 8.0)
    correction_degrees = max(correction_degrees, 4.0)
    correction_radians = math.radians(correction_degrees)

    return {
        "L_hip.ry": -correction_radians,
        "R_hip.ry": correction_radians,
    }


def delta_center_weight(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Shift pelvis laterally to center weight over midfoot.

    Moves the pelvis translation toward the underloaded (higher) side.
    """
    hip_diff = features.hip_y_l_at_bottom - features.hip_y_r_at_bottom
    # Positive diff = left hip higher = weight shifted right → move pelvis left
    # In skeleton frame: pelvis.tx negative = move left
    shift_meters = -hip_diff / 100.0 * 0.5
    shift_meters = max(-0.04, min(0.04, shift_meters))

    return {
        "pelvis.tx": shift_meters,
    }


def delta_increase_depth(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    """Increase squat depth by flexing hips and knees further.

    For athletes with adequate mobility who just need to go deeper.
    Adds ~10° of hip and knee flexion bilaterally.
    """
    depth_deficit = features.depth_class_int
    # More deficit → bigger correction, capped at 15°
    extra_degrees = min((3 - depth_deficit) * 5.0 + 5.0, 15.0)
    extra_degrees = max(extra_degrees, 8.0)
    extra_radians = math.radians(extra_degrees)

    return {
        "L_hip.rx": extra_radians,
        "R_hip.rx": extra_radians,
        "L_knee.rx": extra_radians,
        "R_knee.rx": extra_radians,
    }
