"""Tests for the joint ROM clamp.

The clamp is not wired into the pre-IK chain (see preik_chain.py). These
tests pin the conventions it got wrong when it was: limits are flexion
angles, not interior angles, and the frame is Y-down.
"""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.utils.rom_clamp import (
    ROMClamp,
    ANKLE_DORSI_MAX_DEG,
    KNEE_FLEXION_MAX_DEG,
    _clamp_joint,
    _joint_angle_deg,
    _shin_tilt_from_vertical_deg,
)
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK

ANGLE_TOL_DEG = 0.5
LENGTH_TOL_M = 1e-6
POSITION_TOL_M = 1e-6


def _standing_points() -> np.ndarray:
    """Perfect standing pose in the production Y-down frame."""
    points = np.zeros((19, 3))
    points[CK.LEFT_SHOULDER] = [0.20, -0.50, 0.0]
    points[CK.RIGHT_SHOULDER] = [-0.20, -0.50, 0.0]
    points[CK.LEFT_ELBOW] = [0.22, -0.25, 0.0]
    points[CK.RIGHT_ELBOW] = [-0.22, -0.25, 0.0]
    points[CK.LEFT_WRIST] = [0.24, 0.0, 0.0]
    points[CK.RIGHT_WRIST] = [-0.24, 0.0, 0.0]
    points[CK.LEFT_HIP] = [0.12, 0.0, 0.0]
    points[CK.RIGHT_HIP] = [-0.12, 0.0, 0.0]
    points[CK.LEFT_KNEE] = [0.12, 0.45, 0.0]
    points[CK.RIGHT_KNEE] = [-0.12, 0.45, 0.0]
    points[CK.LEFT_ANKLE] = [0.12, 0.90, 0.0]
    points[CK.RIGHT_ANKLE] = [-0.12, 0.90, 0.0]
    return points


def _make_skeleton(points: np.ndarray) -> Skeleton3D:
    return Skeleton3D.from_numpy(
        points, confidences=np.ones(len(points)), timestamp=0.0, frame_index=0,
    )


class TestShinTilt:

    def test_vertical_shin_reads_zero(self):
        knee = np.array([0.12, 0.45, 0.0])
        ankle = np.array([0.12, 0.90, 0.0])
        assert _shin_tilt_from_vertical_deg(knee, ankle) == pytest.approx(
            0.0, abs=ANGLE_TOL_DEG,
        )

    def test_forward_shin_reads_its_tilt(self):
        """Shin tilted 45° forward: equal vertical and forward components."""
        knee = np.array([0.12, 0.45, 0.0])
        ankle = np.array([0.12, 0.45 + 0.3, 0.3])
        assert _shin_tilt_from_vertical_deg(knee, ankle) == pytest.approx(
            45.0, abs=ANGLE_TOL_DEG,
        )


class TestStandingPoseIsUntouched:

    def test_straight_leg_is_not_clamped(self):
        """The bug that folded every frame: a straight leg read as a violation."""
        points = _standing_points()
        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()
        np.testing.assert_allclose(result, points, atol=POSITION_TOL_M)

    def test_straight_leg_knee_flexion_is_zero(self):
        points = _standing_points()
        interior = _joint_angle_deg(
            points[CK.LEFT_HIP], points[CK.LEFT_KNEE], points[CK.LEFT_ANKLE],
        )
        assert 180.0 - interior == pytest.approx(0.0, abs=ANGLE_TOL_DEG)


class TestClampFires:

    def test_hyperflexed_knee_is_clamped_to_the_limit(self):
        hip = np.array([0.12, 0.0, 0.0])
        knee = np.array([0.12, 0.45, 0.0])
        # Heel to backside: shin folded to 170° flexion, past the 160° limit.
        ankle = np.array([0.12, 0.007, -0.078])

        clamped = _clamp_joint(
            hip, knee, ankle, 0.0, KNEE_FLEXION_MAX_DEG,
        )
        interior = _joint_angle_deg(hip, knee, clamped)
        assert 180.0 - interior == pytest.approx(
            KNEE_FLEXION_MAX_DEG, abs=ANGLE_TOL_DEG,
        )

    def test_in_range_knee_is_not_clamped(self):
        hip = np.array([0.12, 0.0, 0.0])
        knee = np.array([0.12, 0.45, 0.0])
        ankle = np.array([0.12, 0.90, 0.0])
        assert _clamp_joint(hip, knee, ankle, 0.0, KNEE_FLEXION_MAX_DEG) is None

    def test_clamping_preserves_bone_length(self):
        points = _standing_points()
        points[CK.LEFT_ANKLE] = [0.12, 0.30, -0.42]
        original_tibia = float(np.linalg.norm(
            points[CK.LEFT_ANKLE] - points[CK.LEFT_KNEE],
        ))

        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()
        clamped_tibia = float(np.linalg.norm(
            result[CK.LEFT_ANKLE] - result[CK.LEFT_KNEE],
        ))
        assert clamped_tibia == pytest.approx(original_tibia, abs=LENGTH_TOL_M)

    def test_dorsiflexion_clamp_runs_last_on_the_ankle(self):
        """Knee-flexion and dorsiflexion limits both write the ankle; the
        dorsiflexion pass runs last and wins. Documented, not endorsed —
        resolve the priority before this module goes back in the chain."""
        points = _standing_points()
        points[CK.LEFT_ANKLE] = [0.12, 0.30, -0.42]
        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()

        tilt = _shin_tilt_from_vertical_deg(
            result[CK.LEFT_KNEE], result[CK.LEFT_ANKLE],
        )
        assert tilt == pytest.approx(ANKLE_DORSI_MAX_DEG, abs=ANGLE_TOL_DEG)

    def test_excess_dorsiflexion_is_clamped_to_the_limit(self):
        points = _standing_points()
        # Shin tilted ~70° forward, past the 55° dorsiflexion limit.
        points[CK.LEFT_ANKLE] = [0.12, 0.45 + 0.154, 0.423]
        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()

        tilt = _shin_tilt_from_vertical_deg(
            result[CK.LEFT_KNEE], result[CK.LEFT_ANKLE],
        )
        assert tilt == pytest.approx(ANKLE_DORSI_MAX_DEG, abs=ANGLE_TOL_DEG)

    def test_dorsiflexion_clamp_keeps_ankle_below_knee(self):
        points = _standing_points()
        points[CK.LEFT_ANKLE] = [0.12, 0.45 + 0.154, 0.423]
        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()
        # Y-down: below means larger y.
        assert result[CK.LEFT_ANKLE][1] > result[CK.LEFT_KNEE][1]

    def test_normal_squat_depth_is_not_clamped(self):
        """A parallel squat is well inside every limit and must pass through."""
        points = _standing_points()
        points[CK.LEFT_HIP] = [0.12, 0.45, -0.10]
        points[CK.RIGHT_HIP] = [-0.12, 0.45, -0.10]
        points[CK.LEFT_KNEE] = [0.12, 0.52, 0.30]
        points[CK.RIGHT_KNEE] = [-0.12, 0.52, 0.30]
        points[CK.LEFT_ANKLE] = [0.12, 0.90, 0.06]
        points[CK.RIGHT_ANKLE] = [-0.12, 0.90, 0.06]

        result = ROMClamp().clamp(_make_skeleton(points)).to_numpy()
        np.testing.assert_allclose(result, points, atol=POSITION_TOL_M)
