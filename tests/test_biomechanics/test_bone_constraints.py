"""Tests for bone length constraint enforcement."""

import numpy as np
import pytest

from biomechanics.utils.bone_constraints import BoneLengthConstraints, BONE_PAIRS
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK


def _make_skeleton(positions: np.ndarray, timestamp: float = 0.0,
                   frame_index: int = 0) -> Skeleton3D:
    """Helper to create a Skeleton3D from a positions array."""
    confidences = np.ones(len(positions))
    return Skeleton3D.from_numpy(
        positions, confidences=confidences,
        timestamp=timestamp, frame_index=frame_index,
    )


def _standing_skeleton() -> np.ndarray:
    """Create a plausible standing skeleton with consistent bone lengths.

    Returns (17, 3) array with anatomically reasonable positions.
    """
    points = np.zeros((17, 3))
    # Head
    points[CK.NOSE] = [0.0, 1.70, 0.0]
    points[CK.LEFT_EYE] = [0.03, 1.72, -0.02]
    points[CK.RIGHT_EYE] = [-0.03, 1.72, -0.02]
    points[CK.LEFT_EAR] = [0.07, 1.70, 0.0]
    points[CK.RIGHT_EAR] = [-0.07, 1.70, 0.0]
    # Torso
    points[CK.LEFT_SHOULDER] = [0.20, 1.50, 0.0]
    points[CK.RIGHT_SHOULDER] = [-0.20, 1.50, 0.0]
    points[CK.LEFT_HIP] = [0.10, 1.00, 0.0]
    points[CK.RIGHT_HIP] = [-0.10, 1.00, 0.0]
    # Left arm
    points[CK.LEFT_ELBOW] = [0.25, 1.25, 0.0]
    points[CK.LEFT_WRIST] = [0.25, 1.00, 0.0]
    # Right arm
    points[CK.RIGHT_ELBOW] = [-0.25, 1.25, 0.0]
    points[CK.RIGHT_WRIST] = [-0.25, 1.00, 0.0]
    # Left leg
    points[CK.LEFT_KNEE] = [0.10, 0.55, 0.0]
    points[CK.LEFT_ANKLE] = [0.10, 0.10, 0.0]
    # Right leg
    points[CK.RIGHT_KNEE] = [-0.10, 0.55, 0.0]
    points[CK.RIGHT_ANKLE] = [-0.10, 0.10, 0.0]
    return points


class TestBoneLengthConstraints:

    def test_calibration_completes(self):
        """After calibration_frames, is_calibrated becomes True."""
        bc = BoneLengthConstraints(calibration_frames=30)
        skeleton_data = _standing_skeleton()

        assert not bc.is_calibrated

        for i in range(30):
            bc.enforce(_make_skeleton(skeleton_data, frame_index=i))

        assert bc.is_calibrated

    def test_not_calibrated_returns_unchanged(self):
        """During calibration, skeleton passes through unmodified."""
        bc = BoneLengthConstraints(calibration_frames=30)
        skeleton_data = _standing_skeleton()
        skeleton = _make_skeleton(skeleton_data)

        result = bc.enforce(skeleton)
        result_positions = result.to_numpy()

        assert np.allclose(result_positions, skeleton_data, atol=1e-10)

    def test_violation_corrected(self):
        """After calibration, a bone length violation is corrected."""
        bc = BoneLengthConstraints(calibration_frames=30, tolerance=0.15)
        skeleton_data = _standing_skeleton()

        # Calibrate with consistent data
        # Left femur: hip(0.10, 1.00, 0.0) → knee(0.10, 0.55, 0.0) = 0.45m
        for i in range(30):
            bc.enforce(_make_skeleton(skeleton_data, frame_index=i))

        assert bc.is_calibrated

        # Now stretch the left femur to 0.75m (knee moved far down)
        violated = skeleton_data.copy()
        violated[CK.LEFT_KNEE] = [0.10, 0.25, 0.0]  # hip-knee distance = 0.75m

        result = bc.enforce(_make_skeleton(violated, frame_index=30))
        result_positions = result.to_numpy()

        # Corrected left knee should be at calibrated distance (0.45m) from hip
        hip = result_positions[CK.LEFT_HIP]
        knee = result_positions[CK.LEFT_KNEE]
        corrected_length = np.linalg.norm(knee - hip)

        assert abs(corrected_length - 0.45) < 1e-6

    def test_within_tolerance_unchanged(self):
        """A bone at 10% deviation (within 15% tolerance) passes through."""
        bc = BoneLengthConstraints(calibration_frames=30, tolerance=0.15)
        skeleton_data = _standing_skeleton()

        # Calibrate
        for i in range(30):
            bc.enforce(_make_skeleton(skeleton_data, frame_index=i))

        # Move left knee slightly: 10% longer femur
        # Original femur = 0.45m, 10% longer = 0.495m
        deviated = skeleton_data.copy()
        deviated[CK.LEFT_KNEE] = [0.10, 0.505, 0.0]  # hip-knee = 0.495m

        result = bc.enforce(_make_skeleton(deviated, frame_index=30))
        result_positions = result.to_numpy()

        # Should be unchanged since 10% < 15% tolerance
        assert np.allclose(result_positions[CK.LEFT_KNEE], deviated[CK.LEFT_KNEE], atol=1e-6)

    def test_direction_preserved_after_correction(self):
        """Corrected distal keypoint lies on line from proximal to original distal."""
        bc = BoneLengthConstraints(calibration_frames=30, tolerance=0.15)
        skeleton_data = _standing_skeleton()

        for i in range(30):
            bc.enforce(_make_skeleton(skeleton_data, frame_index=i))

        # Move left knee diagonally to create a violation
        violated = skeleton_data.copy()
        violated[CK.LEFT_KNEE] = [0.30, 0.20, 0.10]  # far from calibrated position

        result = bc.enforce(_make_skeleton(violated, frame_index=30))
        result_positions = result.to_numpy()

        hip = skeleton_data[CK.LEFT_HIP]  # proximal (unchanged)
        original_knee = violated[CK.LEFT_KNEE]
        corrected_knee = result_positions[CK.LEFT_KNEE]

        # Direction from hip to corrected should match direction from hip to original
        original_dir = original_knee - hip
        original_dir_unit = original_dir / np.linalg.norm(original_dir)

        corrected_dir = corrected_knee - hip
        corrected_dir_unit = corrected_dir / np.linalg.norm(corrected_dir)

        assert np.allclose(original_dir_unit, corrected_dir_unit, atol=1e-6)

    def test_reset_clears_calibration(self):
        """After reset, is_calibrated is False and calibration restarts."""
        bc = BoneLengthConstraints(calibration_frames=30)
        skeleton_data = _standing_skeleton()

        # Calibrate
        for i in range(30):
            bc.enforce(_make_skeleton(skeleton_data, frame_index=i))
        assert bc.is_calibrated

        # Reset
        bc.reset()
        assert not bc.is_calibrated
