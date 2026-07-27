"""Joint Range-of-Motion Clamping for 3D Keypoints

Clamps joint angles implied by keypoint positions to physiological
limits. Operates on Skeleton3D AFTER bone-length enforcement and
BEFORE position smoothing in the pre-IK filter chain.

When a joint exceeds its ROM limit, the distal keypoint is rotated
about the proximal joint to bring the angle within range. Bone
lengths are preserved (only direction changes).
"""

from __future__ import annotations

import math

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK


KNEE_FLEXION_MIN_DEG = 0.0
KNEE_FLEXION_MAX_DEG = 160.0

HIP_FLEXION_MIN_DEG = 0.0
HIP_FLEXION_MAX_DEG = 140.0

ANKLE_DORSI_MAX_DEG = 55.0

ELBOW_FLEXION_MIN_DEG = 0.0
ELBOW_FLEXION_MAX_DEG = 155.0


def _joint_angle_deg(
    proximal: np.ndarray,
    joint: np.ndarray,
    distal: np.ndarray,
) -> float:
    v1 = proximal - joint
    v2 = distal - joint
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 180.0
    cos_a = np.dot(v1, v2) / (n1 * n2)
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def _clamp_joint(
    proximal: np.ndarray,
    joint: np.ndarray,
    distal: np.ndarray,
    min_angle_deg: float,
    max_angle_deg: float,
) -> np.ndarray | None:
    """Rotate distal about joint to clamp the proximal-joint-distal angle.

    Returns corrected distal position, or None if no correction needed.
    The distance from joint to distal is preserved.
    """
    angle = _joint_angle_deg(proximal, joint, distal)

    if min_angle_deg <= angle <= max_angle_deg:
        return None

    target = max(min_angle_deg, min(max_angle_deg, angle))
    delta_rad = math.radians(target - angle)

    v_prox = proximal - joint
    v_dist = distal - joint
    dist_len = np.linalg.norm(v_dist)
    if dist_len < 1e-9:
        return None

    axis = np.cross(v_prox, v_dist)
    axis_len = np.linalg.norm(axis)
    if axis_len < 1e-9:
        return None
    axis = axis / axis_len

    # Rodrigues rotation of v_dist about axis by delta_rad
    cos_d = math.cos(delta_rad)
    sin_d = math.sin(delta_rad)
    rotated = (
        v_dist * cos_d
        + np.cross(axis, v_dist) * sin_d
        + axis * np.dot(axis, v_dist) * (1.0 - cos_d)
    )

    return joint + rotated


def _shin_tilt_from_vertical_deg(knee: np.ndarray, ankle: np.ndarray) -> float:
    shin = ankle - knee
    vert = -shin[1]
    horiz = math.sqrt(shin[0] ** 2 + shin[2] ** 2)
    return math.degrees(math.atan2(horiz, max(vert, 1e-9)))


class ROMClamp:
    """Clamps joint angles to physiological ROM limits on Skeleton3D."""

    def clamp(self, skeleton: Skeleton3D) -> Skeleton3D:
        points = skeleton.to_numpy()
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])
        corrected = points.copy()

        for hip, knee, ankle in [
            (CK.LEFT_HIP, CK.LEFT_KNEE, CK.LEFT_ANKLE),
            (CK.RIGHT_HIP, CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
        ]:
            if confidences[knee] < 0.1:
                continue

            # Knee flexion: angle(hip, knee, ankle) in [0, 160]
            if confidences[hip] >= 0.1 and confidences[ankle] >= 0.1:
                new_ankle = _clamp_joint(
                    corrected[hip], corrected[knee], corrected[ankle],
                    KNEE_FLEXION_MIN_DEG, KNEE_FLEXION_MAX_DEG,
                )
                if new_ankle is not None:
                    corrected[ankle] = new_ankle

        for shoulder, hip, knee in [
            (CK.LEFT_SHOULDER, CK.LEFT_HIP, CK.LEFT_KNEE),
            (CK.RIGHT_SHOULDER, CK.RIGHT_HIP, CK.RIGHT_KNEE),
        ]:
            if confidences[hip] < 0.1:
                continue

            # Hip flexion: angle(shoulder, hip, knee) in [0, 140]
            if confidences[shoulder] >= 0.1 and confidences[knee] >= 0.1:
                new_knee = _clamp_joint(
                    corrected[shoulder], corrected[hip], corrected[knee],
                    HIP_FLEXION_MIN_DEG, HIP_FLEXION_MAX_DEG,
                )
                if new_knee is not None:
                    corrected[knee] = new_knee

        for shoulder, elbow, wrist in [
            (CK.LEFT_SHOULDER, CK.LEFT_ELBOW, CK.LEFT_WRIST),
            (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW, CK.RIGHT_WRIST),
        ]:
            if confidences[elbow] < 0.1:
                continue

            if confidences[shoulder] >= 0.1 and confidences[wrist] >= 0.1:
                new_wrist = _clamp_joint(
                    corrected[shoulder], corrected[elbow], corrected[wrist],
                    ELBOW_FLEXION_MIN_DEG, ELBOW_FLEXION_MAX_DEG,
                )
                if new_wrist is not None:
                    corrected[wrist] = new_wrist

        for knee, ankle in [
            (CK.LEFT_KNEE, CK.LEFT_ANKLE),
            (CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
        ]:
            if confidences[knee] < 0.1 or confidences[ankle] < 0.1:
                continue
            tilt = _shin_tilt_from_vertical_deg(corrected[knee], corrected[ankle])
            if tilt > ANKLE_DORSI_MAX_DEG:
                shin = corrected[ankle] - corrected[knee]
                shin_len = np.linalg.norm(shin)
                if shin_len < 1e-9:
                    continue
                target_rad = math.radians(ANKLE_DORSI_MAX_DEG)
                new_y = -shin_len * math.cos(target_rad)
                horiz = math.sqrt(shin[0] ** 2 + shin[2] ** 2)
                if horiz < 1e-9:
                    continue
                new_horiz = shin_len * math.sin(target_rad)
                scale = new_horiz / horiz
                corrected[ankle] = corrected[knee] + np.array([
                    shin[0] * scale, new_y, shin[2] * scale,
                ])

        return Skeleton3D.from_numpy(
            corrected,
            confidences=confidences,
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )
