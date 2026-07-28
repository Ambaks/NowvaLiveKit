"""Tests for the anatomical gate on synthesized poses.

Poses here are in the choreographer's grounded Y-UP frame (feet at y = 0),
which is the mirror of the pipeline's Y-down frame.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from biomechanics.diagnosis.pose_validation import (
    ANKLE_DORSIFLEXION_MAX_DEG,
    HIP_FLEXION_MAX_DEG,
    KNEE_FLEXION_MAX_DEG,
    validate_pose,
)

HIP_L, HIP_R = 11, 12
KNEE_L, KNEE_R = 13, 14
ANKLE_L, ANKLE_R = 15, 16
FOOT_L, FOOT_R = 17, 18


def _valid_squat_pose() -> np.ndarray:
    """A parallel squat: legal at every joint."""
    points = np.zeros((19, 3))
    points[0] = [0.0, 1.30, 0.02]
    points[1] = [-0.03, 1.33, 0.0]
    points[2] = [0.03, 1.33, 0.0]
    points[3] = [-0.07, 1.31, 0.0]
    points[4] = [0.07, 1.31, 0.0]
    points[5] = [-0.20, 1.08, 0.10]
    points[6] = [0.20, 1.08, 0.10]
    points[7] = [-0.24, 0.84, 0.14]
    points[8] = [0.24, 0.84, 0.14]
    points[9] = [-0.26, 0.62, 0.18]
    points[10] = [0.26, 0.62, 0.18]
    points[HIP_L] = [-0.12, 0.60, -0.08]
    points[HIP_R] = [0.12, 0.60, -0.08]
    points[KNEE_L] = [-0.16, 0.44, 0.20]
    points[KNEE_R] = [0.16, 0.44, 0.20]
    points[ANKLE_L] = [-0.16, 0.06, 0.0]
    points[ANKLE_R] = [0.16, 0.06, 0.0]
    points[FOOT_L] = [-0.16, 0.0, 0.22]
    points[FOOT_R] = [0.16, 0.0, 0.22]
    return points


def _standing_pose() -> np.ndarray:
    points = _valid_squat_pose()
    points[HIP_L] = [-0.12, 0.95, 0.0]
    points[HIP_R] = [0.12, 0.95, 0.0]
    points[KNEE_L] = [-0.16, 0.50, 0.0]
    points[KNEE_R] = [0.16, 0.50, 0.0]
    return points


class TestValidPoses:

    def test_parallel_squat_is_valid(self):
        result = validate_pose(_valid_squat_pose())
        assert result.is_valid, result.violations

    def test_standing_is_valid(self):
        result = validate_pose(_standing_pose())
        assert result.is_valid, result.violations

    def test_result_is_truthy_when_valid(self):
        assert validate_pose(_valid_squat_pose())

    def test_accepts_a_nested_list(self):
        assert validate_pose(_valid_squat_pose().tolist()).is_valid


class TestJointLimits:

    def test_hyperflexed_knee_is_rejected(self):
        points = _valid_squat_pose()
        # Heel to backside: shin folded up against the thigh.
        points[KNEE_L] = [-0.16, 0.44, 0.30]
        points[ANKLE_L] = [-0.16, 0.62, -0.04]
        result = validate_pose(points)
        assert not result.is_valid
        assert any("knee flexion" in v for v in result.violations)

    def test_hyperextended_knee_is_rejected(self):
        points = _standing_pose()
        # Knee pushed backwards past straight.
        points[KNEE_L] = [-0.16, 0.50, -0.25]
        result = validate_pose(points)
        assert not result.is_valid
        assert any("hyperextended" in v for v in result.violations)

    def test_excessive_shank_tilt_is_rejected(self):
        points = _valid_squat_pose()
        points[KNEE_L] = [-0.16, 0.30, 0.45]
        result = validate_pose(points)
        assert not result.is_valid
        assert any("shank tilt" in v for v in result.violations)

    def test_excessive_knee_deviation_is_rejected(self):
        points = _standing_pose()
        points[KNEE_L] = [1.30, 0.50, 0.0]
        result = validate_pose(points)
        assert not result.is_valid
        assert any("deviates" in v for v in result.violations)

    def test_ankle_above_knee_is_rejected(self):
        """The folded-leg signature."""
        points = _standing_pose()
        points[ANKLE_L] = [-0.16, 0.92, 0.0]
        result = validate_pose(points)
        assert not result.is_valid


class TestStructuralChecks:

    def test_nan_is_rejected(self):
        points = _valid_squat_pose()
        points[KNEE_L][1] = float("nan")
        result = validate_pose(points)
        assert not result.is_valid
        assert any("NaN" in v for v in result.violations)

    def test_infinity_is_rejected(self):
        points = _valid_squat_pose()
        points[HIP_R][0] = float("inf")
        assert not validate_pose(points).is_valid

    def test_wrong_shape_is_rejected(self):
        result = validate_pose(np.zeros((17, 3)))
        assert not result.is_valid
        assert any("19, 3" in v for v in result.violations)

    def test_degenerate_leg_is_rejected(self):
        points = _valid_squat_pose()
        points[KNEE_L] = points[HIP_L].copy()
        result = validate_pose(points)
        assert not result.is_valid
        assert any("degenerate" in v for v in result.violations)

    def test_feet_below_the_floor_are_rejected(self):
        points = _valid_squat_pose()
        points[ANKLE_L][1] = -0.10
        points[FOOT_L][1] = -0.16
        result = validate_pose(points)
        assert not result.is_valid
        assert any("floor" in v for v in result.violations)

    def test_unset_facial_keypoints_do_not_trip_the_floor_check(self):
        """Upstream leaves eyes and ears at the origin; a depth correction
        carries them below y=0 without the feet ever leaving the floor."""
        points = _valid_squat_pose()
        points[1] = points[2] = points[3] = points[4] = np.array([0.0, -0.26, 0.0])
        assert validate_pose(points).is_valid


class TestViolationReporting:

    def test_all_violations_are_reported_not_just_the_first(self):
        points = _standing_pose()
        points[KNEE_L] = [0.90, 0.50, -0.35]
        result = validate_pose(points)
        assert len(result.violations) >= 2

    def test_valid_pose_reports_no_violations(self):
        assert validate_pose(_valid_squat_pose()).violations == []
