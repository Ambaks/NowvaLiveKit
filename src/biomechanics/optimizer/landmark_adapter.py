"""Adapter: pre-processed Skeleton3D (19 COCO keypoints, Y-down) → (11, 4) landmarks (Y-up)."""

from __future__ import annotations

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints


# Skeleton joint order matches SkeletonModel:
#   0: pelvis, 1: trunk, 2: L_hip, 3: R_hip,
#   4: L_knee, 5: R_knee, 6: L_ankle, 7: R_ankle,
#   8: head, 9: L_toe, 10: R_toe

_SKELETON_N_JOINTS = 11


def skeleton3d_to_landmarks(skeleton: Skeleton3D) -> np.ndarray:
    """Convert a pre-processed Skeleton3D into the (11, 4) landmark array that fit_frame() expects.

    Mapping (COCO → skeleton):
        hip midpoint   → pelvis
        shoulder midpt → trunk
        left_hip       → L_hip
        right_hip      → R_hip
        left_knee      → L_knee
        right_knee     → R_knee
        left_ankle     → L_ankle
        right_ankle    → R_ankle
        nose           → head
        left_foot      → L_toe
        right_foot     → R_toe

    Coordinate flip: MediaPipe Y-down → skeleton Y-up (negate X, negate Y).
    Confidence is propagated as the visibility channel.
    """
    kpts = skeleton.keypoints
    landmarks = np.zeros((_SKELETON_N_JOINTS, 4))

    l_hip = kpts[CocoKeypoints.LEFT_HIP]
    r_hip = kpts[CocoKeypoints.RIGHT_HIP]
    l_sh = kpts[CocoKeypoints.LEFT_SHOULDER]
    r_sh = kpts[CocoKeypoints.RIGHT_SHOULDER]

    hip_mid = _midpoint_lm(l_hip, r_hip)
    sh_mid = _midpoint_lm(l_sh, r_sh)
    _TRUNK_FRAC = 0.58
    landmarks[0] = hip_mid
    landmarks[1] = hip_mid * (1 - _TRUNK_FRAC) + sh_mid * _TRUNK_FRAC
    landmarks[2] = _pt_to_lm(l_hip)
    landmarks[3] = _pt_to_lm(r_hip)
    landmarks[4] = _pt_to_lm(kpts[CocoKeypoints.LEFT_KNEE])
    landmarks[5] = _pt_to_lm(kpts[CocoKeypoints.RIGHT_KNEE])
    landmarks[6] = _pt_to_lm(kpts[CocoKeypoints.LEFT_ANKLE])
    landmarks[7] = _pt_to_lm(kpts[CocoKeypoints.RIGHT_ANKLE])

    landmarks[8] = _pt_to_lm(kpts[CocoKeypoints.NOSE])
    if len(kpts) > CocoKeypoints.LEFT_FOOT_INDEX:
        landmarks[9] = _pt_to_lm(kpts[CocoKeypoints.LEFT_FOOT_INDEX])
    if len(kpts) > CocoKeypoints.RIGHT_FOOT_INDEX:
        landmarks[10] = _pt_to_lm(kpts[CocoKeypoints.RIGHT_FOOT_INDEX])

    # MediaPipe: left=+X, down=+Y → Skeleton model: left=-X, up=+Y
    landmarks[:, 0] *= -1
    landmarks[:, 1] *= -1

    return landmarks


def _pt_to_lm(pt) -> np.ndarray:
    return np.array([pt.x, pt.y, pt.z, pt.confidence])


def _midpoint_lm(a, b) -> np.ndarray:
    return np.array([
        (a.x + b.x) * 0.5,
        (a.y + b.y) * 0.5,
        (a.z + b.z) * 0.5,
        min(a.confidence, b.confidence),
    ])
