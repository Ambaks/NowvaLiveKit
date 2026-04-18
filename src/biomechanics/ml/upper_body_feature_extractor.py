"""
Upper Body Feature Extractor

14-feature vector for upper-body exercises (press, row, curl, tricep extensions).
Mirrors the LandmarkFeatureExtractor's structure but uses upper-body keypoints.
"""

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK
from biomechanics.utils.geometry import joint_angle_3_points, distance_3d, midpoint


# Normalization pairs (upper body: shoulder-to-hip, then upper arm)
_NORM_PAIRS = [
    (CK.LEFT_SHOULDER, CK.LEFT_HIP),
    (CK.RIGHT_SHOULDER, CK.RIGHT_HIP),
    (CK.LEFT_SHOULDER, CK.LEFT_ELBOW),
    (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW),
]

_NORM_FALLBACK = 0.5

# Bone-length pairs for upper body
_BONE_PAIRS = [
    (CK.LEFT_SHOULDER, CK.LEFT_ELBOW),    # upper arm L
    (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW),  # upper arm R
    (CK.LEFT_ELBOW, CK.LEFT_WRIST),       # forearm L
    (CK.RIGHT_ELBOW, CK.RIGHT_WRIST),     # forearm R
    (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER), # shoulder width
    (CK.LEFT_SHOULDER, CK.LEFT_HIP),      # torso L
]


class UpperBodyFeatureExtractor:
    """
    Extracts a 14-feature vector from upper-body keypoints.

    Feature vector layout (14 floats):
        [0:4]   - Joint angles: L/R elbow flexion, L/R shoulder flexion (degrees)
        [4:10]  - Normalized bone lengths (6 pairs: upper arm L/R, forearm L/R,
                  shoulder width, torso)
        [10:14] - Normalized y-displacements relative to shoulder_mid:
                  elbow_mid, wrist_mid, hip_mid, ankle_mid
    """

    FEATURE_DIM = 14

    def extract(self, skeleton: Skeleton3D) -> np.ndarray:
        kpts = skeleton.to_numpy()  # (17, 3)

        norm = self._compute_normalization_factor(kpts)
        angles = self._compute_angles(kpts)
        distances = self._compute_normalized_distances(kpts, norm)
        y_diffs = self._compute_normalized_y_diffs(kpts, norm)

        return np.concatenate([angles, distances, y_diffs])

    def _compute_normalization_factor(self, kpts: np.ndarray) -> float:
        for i, j in _NORM_PAIRS:
            d = distance_3d(kpts[i], kpts[j])
            if d > 1e-6:
                return d
        return _NORM_FALLBACK

    def _compute_angles(self, kpts: np.ndarray) -> np.ndarray:
        """Compute 4 joint angles: L/R elbow flexion, L/R shoulder flexion."""
        left_elbow = joint_angle_3_points(
            kpts[CK.LEFT_SHOULDER], kpts[CK.LEFT_ELBOW], kpts[CK.LEFT_WRIST]
        )
        right_elbow = joint_angle_3_points(
            kpts[CK.RIGHT_SHOULDER], kpts[CK.RIGHT_ELBOW], kpts[CK.RIGHT_WRIST]
        )
        # Shoulder flexion: angle at shoulder between hip→shoulder and shoulder→elbow
        left_shoulder = joint_angle_3_points(
            kpts[CK.LEFT_HIP], kpts[CK.LEFT_SHOULDER], kpts[CK.LEFT_ELBOW]
        )
        right_shoulder = joint_angle_3_points(
            kpts[CK.RIGHT_HIP], kpts[CK.RIGHT_SHOULDER], kpts[CK.RIGHT_ELBOW]
        )
        return np.array([left_elbow, right_elbow, left_shoulder, right_shoulder])

    def _compute_normalized_distances(self, kpts: np.ndarray, norm: float) -> np.ndarray:
        return np.array([
            distance_3d(kpts[i], kpts[j]) / norm for i, j in _BONE_PAIRS
        ])

    def _compute_normalized_y_diffs(self, kpts: np.ndarray, norm: float) -> np.ndarray:
        """Normalized vertical displacements relative to shoulder midpoint."""
        shoulder_mid = midpoint(kpts[CK.LEFT_SHOULDER], kpts[CK.RIGHT_SHOULDER])
        elbow_mid = midpoint(kpts[CK.LEFT_ELBOW], kpts[CK.RIGHT_ELBOW])
        wrist_mid = midpoint(kpts[CK.LEFT_WRIST], kpts[CK.RIGHT_WRIST])
        hip_mid = midpoint(kpts[CK.LEFT_HIP], kpts[CK.RIGHT_HIP])
        ankle_mid = midpoint(kpts[CK.LEFT_ANKLE], kpts[CK.RIGHT_ANKLE])

        ref_y = shoulder_mid[1]
        return np.array([
            (elbow_mid[1] - ref_y) / norm,
            (wrist_mid[1] - ref_y) / norm,
            (hip_mid[1] - ref_y) / norm,
            (ankle_mid[1] - ref_y) / norm,
        ])
