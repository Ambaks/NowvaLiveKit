"""
Bone Length Constraint Enforcement

Calibrates segment lengths from the first N frames, then enforces
them as hard constraints. If a distal keypoint violates the calibrated
distance from its proximal joint, it is projected back onto the sphere
of allowed radius.

Operates on Skeleton3D objects, BEFORE the IK solver.

Bone pairs follow the COCO 17 keypoint ordering and are defined
as (proximal_index, distal_index) — the distal point gets corrected.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK


# Ordered from proximal to distal so corrections cascade properly.
# Each tuple is (proximal_keypoint_index, distal_keypoint_index).
BONE_PAIRS: List[Tuple[int, int]] = [
    # Torso
    (CK.LEFT_SHOULDER, CK.LEFT_HIP),
    (CK.RIGHT_SHOULDER, CK.RIGHT_HIP),
    (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER),
    (CK.LEFT_HIP, CK.RIGHT_HIP),
    # Left leg
    (CK.LEFT_HIP, CK.LEFT_KNEE),
    (CK.LEFT_KNEE, CK.LEFT_ANKLE),
    # Right leg
    (CK.RIGHT_HIP, CK.RIGHT_KNEE),
    (CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
    # Left arm
    (CK.LEFT_SHOULDER, CK.LEFT_ELBOW),
    (CK.LEFT_ELBOW, CK.LEFT_WRIST),
    # Right arm
    (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW),
    (CK.RIGHT_ELBOW, CK.RIGHT_WRIST),
]


class BoneLengthConstraints:
    """
    Calibrates and enforces fixed bone lengths on Skeleton3D.

    During calibration (first `calibration_frames` frames), bone lengths
    are measured each frame and the median is stored. After calibration,
    any keypoint that violates its bone length by more than `tolerance`
    percent is projected back to the correct distance.

    Args:
        calibration_frames: Number of frames to observe before locking
            bone lengths. Default 30 (~1 second at 30fps).
        tolerance: Fractional tolerance before correction kicks in.
            0.15 means 15% deviation is allowed. Default 0.15.
    """

    def __init__(
        self,
        calibration_frames: int = 30,
        tolerance: float = 0.15,
    ):
        self.calibration_frames = calibration_frames
        self.tolerance = tolerance

        self._calibrated = False
        self._frame_count = 0

        # During calibration: bone_pair_key -> list of observed lengths
        self._length_observations: Dict[Tuple[int, int], List[float]] = {
            pair: [] for pair in BONE_PAIRS
        }

        # After calibration: bone_pair_key -> median length
        self._calibrated_lengths: Dict[Tuple[int, int], float] = {}

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def enforce(self, skeleton: Skeleton3D) -> Skeleton3D:
        """
        Enforce bone length constraints.

        During calibration: records bone lengths, returns skeleton unchanged.
        After calibration: projects violating keypoints back to allowed radius.

        Args:
            skeleton: Current frame's Skeleton3D

        Returns:
            Skeleton3D with bone lengths enforced (or unchanged during calibration).
        """
        points = skeleton.to_numpy()  # (17, 3)
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])

        if not self._calibrated:
            self._record_calibration(points)
            self._frame_count += 1

            if self._frame_count >= self.calibration_frames:
                self._finalize_calibration()

            return skeleton

        # --- Enforcement pass ---
        corrected = points.copy()

        for proximal_idx, distal_idx in BONE_PAIRS:
            p_prox = corrected[proximal_idx]
            p_dist = corrected[distal_idx]

            current_length = np.linalg.norm(p_dist - p_prox)
            target_length = self._calibrated_lengths.get(
                (proximal_idx, distal_idx)
            )

            if target_length is None or target_length < 1e-6:
                continue

            # Check if violation exceeds tolerance
            deviation = abs(current_length - target_length) / target_length

            if deviation > self.tolerance:
                # Project distal point onto sphere of radius target_length
                # centered at proximal point
                if current_length < 1e-10:
                    # Degenerate: distal is on top of proximal.
                    # Push it in the +Y direction (upward) by target_length.
                    direction = np.array([0.0, 1.0, 0.0])
                else:
                    direction = (p_dist - p_prox) / current_length

                corrected[distal_idx] = p_prox + direction * target_length

        return Skeleton3D.from_numpy(
            corrected,
            confidences=confidences,
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )

    def _record_calibration(self, points: np.ndarray) -> None:
        """Record bone lengths for one frame during calibration."""
        for proximal_idx, distal_idx in BONE_PAIRS:
            length = float(np.linalg.norm(
                points[distal_idx] - points[proximal_idx]
            ))
            if length > 1e-6:  # Skip degenerate frames
                self._length_observations[(proximal_idx, distal_idx)].append(length)

    def _finalize_calibration(self) -> None:
        """Compute median bone lengths and lock calibration."""
        for pair, lengths in self._length_observations.items():
            if lengths:
                self._calibrated_lengths[pair] = float(np.median(lengths))

        self._calibrated = True

        # Free observation memory
        self._length_observations.clear()

    def reset(self):
        """Reset calibration state."""
        self._calibrated = False
        self._frame_count = 0
        self._calibrated_lengths.clear()
        self._length_observations = {pair: [] for pair in BONE_PAIRS}
