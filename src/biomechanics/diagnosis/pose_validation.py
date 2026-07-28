"""Anatomical validation for synthesized poses.

Corrected poses are shown to the athlete as a movement target, so nothing
downstream should ever render one the body cannot achieve. Nothing validated
the choreographer's output before this: no knee-flexion ceiling, no
hyperextension check, no varus/valgus limit, no hip ROM check.

Poses here are in the choreographer's grounded frame — Y-UP, feet at y = 0 —
which is the mirror of the pipeline's Y-down frame (see geometry.WORLD_UP).
The conversion happens when the observation is grounded for the viewer.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel

HIP_L, HIP_R = 11, 12
KNEE_L, KNEE_R = 13, 14
ANKLE_L, ANKLE_R = 15, 16
FOOT_L, FOOT_R = 17, 18
SHOULDER_L, SHOULDER_R = 5, 6

# Joint limits for a loaded barbell squat, deliberately generous — this is a
# guard against impossible output, not a form judgement.
KNEE_FLEXION_MAX_DEG = 155.0
KNEE_HYPEREXTENSION_MAX_DEG = 5.0
HIP_FLEXION_MAX_DEG = 145.0
ANKLE_DORSIFLEXION_MAX_DEG = 50.0
# The knee legitimately sits well lateral of the hip-ankle line in a wide,
# deep squat — a measured 33 deg on a normal parallel rep — so this only
# catches a leg bent sideways, not valgus or varus a coach would flag.
KNEE_FRONTAL_DEVIATION_MAX_DEG = 50.0

# A foot pressed this far below the floor is a solver failure, not rounding.
GROUND_PENETRATION_MAX_M = 0.02
MIN_SEGMENT_LENGTH_M = 0.05


class PoseValidation(BaseModel):
    is_valid: bool
    violations: list[str]

    def __bool__(self) -> bool:
        return self.is_valid


def _interior_angle_deg(
    proximal: np.ndarray, joint: np.ndarray, distal: np.ndarray,
) -> float:
    first = proximal - joint
    second = distal - joint
    first_length = float(np.linalg.norm(first))
    second_length = float(np.linalg.norm(second))
    if first_length < 1e-9 or second_length < 1e-9:
        return 180.0
    cosine = float(np.dot(first, second) / (first_length * second_length))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _horizontal_unit(vector: np.ndarray) -> np.ndarray | None:
    flat = np.array([vector[0], 0.0, vector[2]])
    length = float(np.linalg.norm(flat))
    if length < 1e-9:
        return None
    return flat / length


def body_axes(points: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Derive (lateral, forward) horizontal unit vectors from the pose itself.

    The skeleton carries whatever yaw the athlete had, so the anatomical axes
    are not the world axes — bottom_up_build derives them the same way.
    Lateral runs left hip to right hip; forward runs ankle to toes.
    """
    lateral = _horizontal_unit(points[HIP_R] - points[HIP_L])
    if lateral is None:
        return None

    toes = (points[FOOT_L] - points[ANKLE_L]) + (points[FOOT_R] - points[ANKLE_R])
    forward = _horizontal_unit(toes)
    if forward is None:
        # No usable foot vector: fall back to the perpendicular of lateral.
        forward = np.array([-lateral[2], 0.0, lateral[0]])
    else:
        # Remove any lateral component so the two axes stay orthogonal.
        forward = forward - lateral * float(np.dot(forward, lateral))
        forward = _horizontal_unit(forward)
        if forward is None:
            return None

    return (lateral, forward)


def _knee_offset_from_hip_ankle_line(
    hip: np.ndarray, knee: np.ndarray, ankle: np.ndarray, axis: np.ndarray,
) -> tuple[float, float]:
    """Signed knee offset from the hip-ankle line along axis, and line length."""
    span = ankle[1] - hip[1]
    if abs(span) < 1e-6:
        return (0.0, 0.0)
    ratio = float(np.clip((knee[1] - hip[1]) / span, 0.0, 1.0))
    expected = hip + ratio * (ankle - hip)
    return (
        float(np.dot(knee - expected, axis)),
        float(np.linalg.norm(ankle - hip)),
    )


def _shank_tilt_deg(knee: np.ndarray, ankle: np.ndarray) -> float:
    """Shank tilt from vertical. Y-up frame: the knee sits above the ankle."""
    shank = knee - ankle
    vertical = shank[1]
    horizontal = math.hypot(shank[0], shank[2])
    if abs(vertical) < 1e-9 and horizontal < 1e-9:
        return 0.0
    return math.degrees(math.atan2(horizontal, vertical))


def validate_pose(keypoints: np.ndarray | list[list[float]]) -> PoseValidation:
    """Check a synthesized pose against anatomical limits.

    Returns the full list of violations rather than the first, so a failure
    can be logged with everything that is wrong with the pose.
    """
    points = np.asarray(keypoints, dtype=np.float64)
    violations: list[str] = []

    # 19 keypoints for poses captured before heels were tracked, 21 with them.
    if points.ndim != 2 or points.shape[0] not in (19, 21) or points.shape[1] != 3:
        return PoseValidation(
            is_valid=False, violations=[f"expected (19, 3) or (21, 3), got {points.shape}"],
        )
    if not np.all(np.isfinite(points)):
        return PoseValidation(
            is_valid=False, violations=["pose contains NaN or infinite values"],
        )

    axes = body_axes(points)
    if axes is None:
        return PoseValidation(
            is_valid=False, violations=["cannot derive body axes from the pose"],
        )
    lateral_axis, forward_axis = axes

    for side, hip, knee, ankle, shoulder in (
        ("left", HIP_L, KNEE_L, ANKLE_L, SHOULDER_L),
        ("right", HIP_R, KNEE_R, ANKLE_R, SHOULDER_R),
    ):
        femur = float(np.linalg.norm(points[knee] - points[hip]))
        tibia = float(np.linalg.norm(points[ankle] - points[knee]))
        if femur < MIN_SEGMENT_LENGTH_M or tibia < MIN_SEGMENT_LENGTH_M:
            violations.append(
                f"{side} leg is degenerate "
                f"(femur {femur * 100:.1f} cm, tibia {tibia * 100:.1f} cm)"
            )
            continue

        knee_flexion = 180.0 - _interior_angle_deg(
            points[hip], points[knee], points[ankle],
        )
        if knee_flexion > KNEE_FLEXION_MAX_DEG:
            violations.append(
                f"{side} knee flexion {knee_flexion:.1f}° exceeds "
                f"{KNEE_FLEXION_MAX_DEG:.0f}°"
            )

        sagittal_offset, line_length = _knee_offset_from_hip_ankle_line(
            points[hip], points[knee], points[ankle], forward_axis,
        )
        if line_length > MIN_SEGMENT_LENGTH_M:
            # Negative = knee behind the hip-ankle line, i.e. bending backwards.
            hyperextension = math.degrees(math.atan2(-sagittal_offset, line_length))
            if hyperextension > KNEE_HYPEREXTENSION_MAX_DEG:
                violations.append(
                    f"{side} knee hyperextended by {hyperextension:.1f}°"
                )

        hip_flexion = 180.0 - _interior_angle_deg(
            points[shoulder], points[hip], points[knee],
        )
        if hip_flexion > HIP_FLEXION_MAX_DEG:
            violations.append(
                f"{side} hip flexion {hip_flexion:.1f}° exceeds "
                f"{HIP_FLEXION_MAX_DEG:.0f}°"
            )

        frontal_offset, line_length = _knee_offset_from_hip_ankle_line(
            points[hip], points[knee], points[ankle], lateral_axis,
        )
        if line_length > MIN_SEGMENT_LENGTH_M:
            frontal_deviation = math.degrees(
                math.atan2(abs(frontal_offset), line_length)
            )
            if frontal_deviation > KNEE_FRONTAL_DEVIATION_MAX_DEG:
                violations.append(
                    f"{side} knee deviates {frontal_deviation:.1f}° from the "
                    f"hip-ankle line, over {KNEE_FRONTAL_DEVIATION_MAX_DEG:.0f}°"
                )

        shank_tilt = _shank_tilt_deg(points[knee], points[ankle])
        if shank_tilt > ANKLE_DORSIFLEXION_MAX_DEG:
            violations.append(
                f"{side} shank tilt {shank_tilt:.1f}° exceeds "
                f"{ANKLE_DORSIFLEXION_MAX_DEG:.0f}°"
            )

        if points[ankle][1] < points[knee][1] - tibia - 1e-6:
            violations.append(f"{side} ankle is above the knee")

    # Only the feet are checked against the floor. Facial keypoints are often
    # left unset at the origin upstream, and a zeroed keypoint riding down
    # with a depth correction is not a floor collision.
    lowest_foot = float(np.min(points[[ANKLE_L, ANKLE_R, FOOT_L, FOOT_R], 1]))
    if lowest_foot < -GROUND_PENETRATION_MAX_M:
        violations.append(
            f"feet penetrate the floor by {-lowest_foot * 100:.1f} cm"
        )

    return PoseValidation(is_valid=not violations, violations=violations)
