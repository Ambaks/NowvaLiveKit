"""Parameter-delta functions for tier-1 (cue-correctable) causes.

Each delta function returns a dict. The KeypointCorrector uses the cause_id
to decide what geometric correction to apply; these deltas serve as
structured metadata about what the engine thinks should change.

Each delta function is paired with a magnitude function that renders its
delta as a short spoken phrase, so the key names stay defined and consumed
in one file. Magnitude functions return None when no phrase is derivable.

Shared anthropometry-driven target functions also live here so the geometric
corrections and the spoken explanation templates derive from the same
computation and cannot disagree.
"""

from __future__ import annotations

import math

from ..types import RepKinematicSummary


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def expected_trunk_lean_geometric(anthro: dict) -> float:
    femur_torso_ratio = anthro.get("femur_torso_ratio", 1.0)
    return 30.0 + (femur_torso_ratio - 1.0) * 120.0


def dorsi_driven_targets(
    dorsiflexion_capacity: float, anthro: dict
) -> tuple[float, float]:
    """Compute target stance ratio and toe-out from dorsiflexion + femur proportions.

    Returns (target_stance_ratio_x_shoulder_width, target_toe_out_degrees).
    """
    femur_torso_ratio = anthro.get("femur_torso_ratio", 1.0)
    dorsi_clamped = max(10.0, min(45.0, dorsiflexion_capacity))

    dorsi_factor = _clamp((45.0 - dorsi_clamped) / 25.0)
    femur_factor = _clamp((femur_torso_ratio - 0.70) / 0.30)

    target_stance = (
        1.1
        + femur_factor * 0.5
        + dorsi_factor * 0.5
        + femur_factor * dorsi_factor * 0.3
    )
    target_stance = min(target_stance, 2.0)

    target_toe_out = (
        15.0
        + femur_factor * 10.0
        + dorsi_factor * 8.0
        + femur_factor * dorsi_factor * 5.0
    )

    return (max(1.1, target_stance), max(15.0, min(40.0, target_toe_out)))


def stance_target_ratio(current_ratio: float, anthro: dict, rom: dict) -> float:
    """Single source of truth for the stance-width target — used by both the
    geometric correction and the spoken explanation."""
    dorsi_capacity = rom.get("dorsiflexion_drop", 35.0)
    dorsi_target_ratio, _ = dorsi_driven_targets(dorsi_capacity, anthro)
    target_ratio = max(dorsi_target_ratio, current_ratio + 0.15, 1.0)
    return min(target_ratio, 2.5)


def foot_angle_target_deg(anthro: dict, rom: dict) -> float:
    """Single source of truth for the toe-out target — used by both the
    geometric correction and the spoken explanation."""
    dorsi_capacity = rom.get("dorsiflexion_drop", 35.0)
    _, dorsi_target_angle = dorsi_driven_targets(dorsi_capacity, anthro)
    return max(30.0, dorsi_target_angle)


def delta_widen_stance(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    current_ratio = features.stance_width_ratio
    shoulder_width = anthro.get("shoulder_width", 0.40)

    target_ratio = stance_target_ratio(current_ratio, anthro, rom)
    width_increase_per_side = max(
        0.0, (target_ratio - current_ratio) * shoulder_width / 2.0
    )

    return {
        "__foot_target_delta": [
            0.0, 0.0, -width_increase_per_side,
            0.0, 0.0, width_increase_per_side,
        ],
        "__target_stance_ratio": target_ratio,
    }


def magnitude_widen_stance(parameter_delta: dict) -> str | None:
    ratio = parameter_delta.get("__target_stance_ratio")
    if ratio is None or float(ratio) <= 0:
        return None
    return f"about {float(ratio):.1f} times shoulder width"


def delta_widen_foot_angle(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    avg_current = (
        features.foot_direction_angle_l + features.foot_direction_angle_r
    ) / 2.0

    target_angle = foot_angle_target_deg(anthro, rom)
    delta_degrees = max(0.0, min(target_angle - avg_current, 50.0))
    delta_radians = math.radians(delta_degrees)

    return {
        "L_ankle.ry": delta_radians,
        "R_ankle.ry": -delta_radians,
    }


def magnitude_widen_foot_angle(parameter_delta: dict) -> str | None:
    radians = parameter_delta.get("L_ankle.ry")
    if radians is None:
        return None
    degrees = round(math.degrees(abs(float(radians))))
    if degrees <= 0:
        return None
    return f"toes turned out about {degrees} more degrees"


def delta_brace_trunk(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    expected_lean = expected_trunk_lean_geometric(anthro)
    excess_lean = features.trunk_pitch_at_bottom - expected_lean
    correction_degrees = min(excess_lean * 0.4, 8.0)
    correction_degrees = max(correction_degrees, 3.0)

    return {
        "trunk.rx": -math.radians(correction_degrees),
    }


def delta_knees_out(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    max_valgus = max(features.knee_valgus_l, features.knee_valgus_r)
    correction_degrees = min(max_valgus * 0.5, 8.0)
    correction_degrees = max(correction_degrees, 4.0)
    correction_radians = math.radians(correction_degrees)

    return {
        "L_hip.ry": -correction_radians,
        "R_hip.ry": correction_radians,
    }


def magnitude_knees_out(parameter_delta: dict) -> str | None:
    radians = parameter_delta.get("R_hip.ry")
    if radians is None:
        return None
    degrees = round(math.degrees(abs(float(radians))))
    if degrees <= 0:
        return None
    return f"knees pushed out about {degrees} degrees more"


def delta_center_weight(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict[str, float]:
    hip_diff = features.hip_y_l_at_bottom - features.hip_y_r_at_bottom
    shift_meters = -hip_diff / 100.0 * 0.5
    shift_meters = max(-0.04, min(0.04, shift_meters))

    return {
        "pelvis.tx": shift_meters,
    }


def magnitude_center_weight(parameter_delta: dict) -> str | None:
    shift_m = parameter_delta.get("pelvis.tx")
    if shift_m is None:
        return None
    shift_cm = round(abs(float(shift_m)) * 100.0)
    if shift_cm <= 0:
        return None
    return f"weight centered by about {shift_cm} centimeters"


def delta_increase_depth(
    features: RepKinematicSummary, anthro: dict, rom: dict
) -> dict:
    return {
        "depth_target": "parallel",
    }
