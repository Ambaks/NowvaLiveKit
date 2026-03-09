"""
Standing Pose Gate

Validates that the user is standing properly before allowing calibration
to begin. Checks keypoint visibility, knee extension, torso uprightness,
and distance plausibility.

Requires several consecutive passing frames to filter single-frame flukes.
Once satisfied, the gate latches and stays open.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK
from biomechanics.utils.geometry import angle_between_vectors, joint_angle_3_points

logger = logging.getLogger(__name__)

# Keypoints that MUST be visible for a valid standing pose.
REQUIRED_KEYPOINTS = [
    CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER,
    CK.LEFT_HIP, CK.RIGHT_HIP,
    CK.LEFT_KNEE, CK.RIGHT_KNEE,
    CK.LEFT_ANKLE, CK.RIGHT_ANKLE,
]


class StandingPoseGate:
    """
    Validates that the skeleton represents a standing person before
    allowing downstream calibration to begin.

    Checks per frame:
      1. All 8 major keypoints visible with confidence >= min_confidence
      2. Knees nearly extended (flexion < max_knee_flexion_deg)
      3. Torso roughly upright (trunk angle from vertical < max_trunk_flexion_deg)
      4. Person at reasonable distance (torso length in plausible range)

    Requires ``required_consecutive_frames`` consecutive passing frames
    before latching ``is_ready = True``.
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        max_knee_flexion_deg: float = 20.0,
        max_trunk_flexion_deg: float = 25.0,
        min_torso_length_m: float = 0.25,
        max_torso_length_m: float = 0.80,
        required_consecutive_frames: int = 5,
    ):
        self.min_confidence = min_confidence
        self.max_knee_flexion_deg = max_knee_flexion_deg
        self.max_trunk_flexion_deg = max_trunk_flexion_deg
        self.min_torso_length_m = min_torso_length_m
        self.max_torso_length_m = max_torso_length_m
        self.required_consecutive_frames = required_consecutive_frames

        self._consecutive_passes: int = 0
        self._passed: bool = False

    @property
    def is_ready(self) -> bool:
        """Whether the standing pose gate has been satisfied."""
        return self._passed

    def check(self, skeleton: Skeleton3D) -> bool:
        """
        Check if the current skeleton passes the standing pose gate.

        Returns True once the gate is satisfied (and stays True forever).
        """
        if self._passed:
            return True

        if self._check_single_frame(skeleton):
            self._consecutive_passes += 1
        else:
            self._consecutive_passes = 0

        if self._consecutive_passes >= self.required_consecutive_frames:
            self._passed = True
            logger.info("[STANDING GATE] Passed — calibration may begin")

        return self._passed

    def _check_single_frame(self, skeleton: Skeleton3D) -> bool:
        """Run all standing-pose checks on a single frame."""
        points = skeleton.to_numpy()  # (17, 3)
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])

        if not self._check_keypoint_visibility(confidences):
            return False
        if not self._check_knee_extension(points):
            return False
        if not self._check_torso_upright(points):
            return False
        if not self._check_distance(points):
            return False

        return True

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_keypoint_visibility(self, confidences: np.ndarray) -> bool:
        for idx in REQUIRED_KEYPOINTS:
            if confidences[idx] < self.min_confidence:
                return False
        return True

    def _check_knee_extension(self, points: np.ndarray) -> bool:
        left_angle = joint_angle_3_points(
            points[CK.LEFT_HIP], points[CK.LEFT_KNEE], points[CK.LEFT_ANKLE],
        )
        left_flexion = 180.0 - left_angle

        right_angle = joint_angle_3_points(
            points[CK.RIGHT_HIP], points[CK.RIGHT_KNEE], points[CK.RIGHT_ANKLE],
        )
        right_flexion = 180.0 - right_angle

        return (
            left_flexion < self.max_knee_flexion_deg
            and right_flexion < self.max_knee_flexion_deg
        )

    def _check_torso_upright(self, points: np.ndarray) -> bool:
        shoulder_mid = (points[CK.LEFT_SHOULDER] + points[CK.RIGHT_SHOULDER]) / 2.0
        hip_mid = (points[CK.LEFT_HIP] + points[CK.RIGHT_HIP]) / 2.0
        trunk_vec = shoulder_mid - hip_mid
        vertical = np.array([0.0, 1.0, 0.0])
        trunk_flexion = angle_between_vectors(trunk_vec, vertical)
        return trunk_flexion < self.max_trunk_flexion_deg

    def _check_distance(self, points: np.ndarray) -> bool:
        shoulder_mid = (points[CK.LEFT_SHOULDER] + points[CK.RIGHT_SHOULDER]) / 2.0
        hip_mid = (points[CK.LEFT_HIP] + points[CK.RIGHT_HIP]) / 2.0
        torso_length = float(np.linalg.norm(shoulder_mid - hip_mid))
        return self.min_torso_length_m <= torso_length <= self.max_torso_length_m

    def reset(self) -> None:
        """Reset the gate state."""
        self._consecutive_passes = 0
        self._passed = False
