"""
Ground Plane Clamping for Ankle Keypoints

Calibrates standing foot placement from the first N frames, then
enforces ground-plane constraints: both ankles at the same Y, stance
width preserved, and ankles never past calibrated leg extension.

Runs AFTER bone length enforcement and BEFORE position smoothing
in the pre-IK filter chain.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import numpy as np

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK

if TYPE_CHECKING:
    from biomechanics.utils.standing_gate import StandingPoseGate

logger = logging.getLogger(__name__)


class GroundClamp:
    """
    Enforces ground-plane constraints on ankle and foot keypoints.

    During calibration (standing), records stance width and ankle Y
    positions. After calibration, enforces flat-floor and anti-slide
    constraints every frame.
    """

    def __init__(
        self,
        calibration_frames: int = 30,
        stance_width_tolerance_m: float = 0.02,
        ankle_y_tolerance_m: float = 0.01,
        standing_gate: Optional["StandingPoseGate"] = None,
    ):
        self._calibration_frames = calibration_frames
        self._stance_width_tol = stance_width_tolerance_m
        self._ankle_y_tol = ankle_y_tolerance_m
        self._standing_gate = standing_gate

        self._calibrated = False
        self._frame_count = 0

        self._stance_widths: list[float] = []
        self._ankle_y_l_obs: list[float] = []
        self._ankle_y_r_obs: list[float] = []

        self._stance_width: float = 0.0
        self._ankle_y_max_l: float = 0.0
        self._ankle_y_max_r: float = 0.0

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def clamp(self, skeleton: Skeleton3D) -> Skeleton3D:
        points = skeleton.to_numpy()
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])
        n_kpts = len(points)

        if confidences[CK.LEFT_ANKLE] < 0.1 or confidences[CK.RIGHT_ANKLE] < 0.1:
            return skeleton

        if not self._calibrated:
            if self._standing_gate is not None and not self._standing_gate.is_ready:
                return skeleton

            self._record_calibration(points)
            self._frame_count += 1
            if self._frame_count >= self._calibration_frames:
                self._finalize_calibration()
            return skeleton

        corrected = points.copy()

        # --- Floor penetration: ankle can't extend past calibrated standing ---
        # Y-down convention: larger Y = further below hip = toward floor.
        corrected[CK.LEFT_ANKLE, 1] = min(
            corrected[CK.LEFT_ANKLE, 1], self._ankle_y_max_l,
        )
        corrected[CK.RIGHT_ANKLE, 1] = min(
            corrected[CK.RIGHT_ANKLE, 1], self._ankle_y_max_r,
        )

        # --- Flat floor: equalize ankle Y when they diverge ---
        y_diff = abs(corrected[CK.LEFT_ANKLE, 1] - corrected[CK.RIGHT_ANKLE, 1])
        if y_diff > self._ankle_y_tol:
            avg_y = (corrected[CK.LEFT_ANKLE, 1] + corrected[CK.RIGHT_ANKLE, 1]) / 2.0
            corrected[CK.LEFT_ANKLE, 1] = avg_y
            corrected[CK.RIGHT_ANKLE, 1] = avg_y

        # --- Stance width: lock ankle-to-ankle XZ distance ---
        l_xz = corrected[CK.LEFT_ANKLE, [0, 2]]
        r_xz = corrected[CK.RIGHT_ANKLE, [0, 2]]
        current_width = float(np.linalg.norm(l_xz - r_xz))

        if current_width > 1e-6:
            width_error = abs(current_width - self._stance_width)
            if width_error > self._stance_width_tol:
                mid_xz = (l_xz + r_xz) / 2.0
                direction = (l_xz - r_xz) / current_width
                half_target = self._stance_width / 2.0
                corrected[CK.LEFT_ANKLE, 0] = mid_xz[0] + direction[0] * half_target
                corrected[CK.LEFT_ANKLE, 2] = mid_xz[1] + direction[1] * half_target
                corrected[CK.RIGHT_ANKLE, 0] = mid_xz[0] - direction[0] * half_target
                corrected[CK.RIGHT_ANKLE, 2] = mid_xz[1] - direction[1] * half_target

        # --- Propagate ankle corrections to foot index keypoints ---
        for ankle_idx, foot_idx in [
            (CK.LEFT_ANKLE, CK.LEFT_FOOT_INDEX),
            (CK.RIGHT_ANKLE, CK.RIGHT_FOOT_INDEX),
        ]:
            if foot_idx < n_kpts and confidences[foot_idx] > 0:
                delta = corrected[ankle_idx] - points[ankle_idx]
                corrected[foot_idx] += delta

        return Skeleton3D.from_numpy(
            corrected,
            confidences=confidences,
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )

    def _record_calibration(self, points: np.ndarray) -> None:
        l_ankle = points[CK.LEFT_ANKLE]
        r_ankle = points[CK.RIGHT_ANKLE]
        width = float(np.linalg.norm(l_ankle[[0, 2]] - r_ankle[[0, 2]]))
        self._stance_widths.append(width)
        self._ankle_y_l_obs.append(float(l_ankle[1]))
        self._ankle_y_r_obs.append(float(r_ankle[1]))

    def _finalize_calibration(self) -> None:
        self._stance_width = float(np.median(self._stance_widths))
        self._ankle_y_max_l = float(np.median(self._ankle_y_l_obs))
        self._ankle_y_max_r = float(np.median(self._ankle_y_r_obs))
        self._calibrated = True

        self._stance_widths.clear()
        self._ankle_y_l_obs.clear()
        self._ankle_y_r_obs.clear()

        logger.info(
            "[GROUND CLAMP] Calibrated: stance_width=%.3fm, "
            "ankle_y_max L=%.3fm R=%.3fm",
            self._stance_width, self._ankle_y_max_l, self._ankle_y_max_r,
        )

    def reset(self) -> None:
        self._calibrated = False
        self._frame_count = 0
        self._stance_widths.clear()
        self._ankle_y_l_obs.clear()
        self._ankle_y_r_obs.clear()
