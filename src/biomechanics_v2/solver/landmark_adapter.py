"""Adapter: pre-processed Skeleton3D (19 COCO keypoints, Y-down) → (17, 4) landmarks (Z-up).

Converts MediaPipe Y-down coordinates to MuJoCo Z-up space (X=lateral, Y=forward, Z=up)
for the V2 IK solver.
"""

from __future__ import annotations

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints

SKELETON_N_JOINTS = 17

# Landmark indices (matches MujocoSkeleton body_names order without head/toe interleaving)
PELVIS = 0
TRUNK = 1
L_HIP = 2
R_HIP = 3
L_KNEE = 4
R_KNEE = 5
L_ANKLE = 6
R_ANKLE = 7
HEAD = 8
L_TOE = 9
R_TOE = 10
L_SHOULDER = 11
R_SHOULDER = 12
L_ELBOW = 13
R_ELBOW = 14
L_WRIST = 15
R_WRIST = 16

_TRUNK_SHOULDER_FRACTION = 0.58


def skeleton3d_to_landmarks(skeleton: Skeleton3D) -> np.ndarray:
    """Convert 19-keypoint Skeleton3D (MediaPipe Y-down) to (17, 4) array (MuJoCo Z-up).

    Coordinate transform: negate X, negate Y, then swap Y↔Z
    (MediaPipe Y-down → V1 Y-up → MuJoCo Z-up).
    Column 3 carries visibility/confidence.
    """
    kpts = skeleton.keypoints
    landmarks = np.zeros((SKELETON_N_JOINTS, 4))

    left_hip = kpts[CocoKeypoints.LEFT_HIP]
    right_hip = kpts[CocoKeypoints.RIGHT_HIP]
    left_shoulder = kpts[CocoKeypoints.LEFT_SHOULDER]
    right_shoulder = kpts[CocoKeypoints.RIGHT_SHOULDER]

    hip_midpoint = _midpoint_lm(left_hip, right_hip)
    shoulder_midpoint = _midpoint_lm(left_shoulder, right_shoulder)

    landmarks[PELVIS] = hip_midpoint
    landmarks[TRUNK] = (
        hip_midpoint * (1.0 - _TRUNK_SHOULDER_FRACTION)
        + shoulder_midpoint * _TRUNK_SHOULDER_FRACTION
    )
    landmarks[L_HIP] = _point3d_to_lm(left_hip)
    landmarks[R_HIP] = _point3d_to_lm(right_hip)
    landmarks[L_KNEE] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_KNEE])
    landmarks[R_KNEE] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_KNEE])
    landmarks[L_ANKLE] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_ANKLE])
    landmarks[R_ANKLE] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_ANKLE])
    landmarks[HEAD] = _point3d_to_lm(kpts[CocoKeypoints.NOSE])

    if len(kpts) > CocoKeypoints.LEFT_FOOT_INDEX:
        landmarks[L_TOE] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_FOOT_INDEX])
    if len(kpts) > CocoKeypoints.RIGHT_FOOT_INDEX:
        landmarks[R_TOE] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_FOOT_INDEX])

    landmarks[L_SHOULDER] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_SHOULDER])
    landmarks[R_SHOULDER] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_SHOULDER])
    landmarks[L_ELBOW] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_ELBOW])
    landmarks[R_ELBOW] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_ELBOW])
    landmarks[L_WRIST] = _point3d_to_lm(kpts[CocoKeypoints.LEFT_WRIST])
    landmarks[R_WRIST] = _point3d_to_lm(kpts[CocoKeypoints.RIGHT_WRIST])

    # MediaPipe: left=+X, down=+Y, forward=+Z
    # MuJoCo:    left=-X, forward=+Y, up=+Z
    landmarks[:, 0] *= -1   # flip X (MediaPipe left → skeleton left)
    landmarks[:, 1] *= -1   # flip Y (down → up, temporarily)

    # V1 Y-up (X=lateral, Y=up, Z=forward) → MuJoCo Z-up (X=lateral, Y=forward, Z=up)
    y_up = landmarks[:, 1].copy()
    landmarks[:, 1] = landmarks[:, 2]  # mj_Y = forward (was V1 Z)
    landmarks[:, 2] = y_up             # mj_Z = up (was V1 Y)

    return landmarks


def _point3d_to_lm(point) -> np.ndarray:
    return np.array([point.x, point.y, point.z, point.confidence])


def _midpoint_lm(point_a, point_b) -> np.ndarray:
    return np.array([
        (point_a.x + point_b.x) * 0.5,
        (point_a.y + point_b.y) * 0.5,
        (point_a.z + point_b.z) * 0.5,
        min(point_a.confidence, point_b.confidence),
    ])
