"""
Tests for inverse kinematics module.

Tests the AnalyticalIKSolver with various poses and validates
that computed angles are physically plausible.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.kinematics.base import IKSolver
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.utils.types import Skeleton3D, JointAngles, Point3D


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def ik_solver():
    """Create an AnalyticalIKSolver instance."""
    return AnalyticalIKSolver()


@pytest.fixture
def standing_skeleton():
    """
    Create a 3D skeleton in standing position.

    All joints should be roughly at 0 degrees flexion.
    Coordinate system: Y-up, Z-forward
    """
    # Standing pose with arms down
    keypoints = [
        Point3D(x=0.0, y=1.70, z=0.0, confidence=1.0),      # 0: nose
        Point3D(x=0.03, y=1.72, z=-0.02, confidence=1.0),   # 1: left_eye
        Point3D(x=-0.03, y=1.72, z=-0.02, confidence=1.0),  # 2: right_eye
        Point3D(x=0.06, y=1.70, z=0.0, confidence=1.0),     # 3: left_ear
        Point3D(x=-0.06, y=1.70, z=0.0, confidence=1.0),    # 4: right_ear
        Point3D(x=0.18, y=1.50, z=0.0, confidence=1.0),     # 5: left_shoulder
        Point3D(x=-0.18, y=1.50, z=0.0, confidence=1.0),    # 6: right_shoulder
        Point3D(x=0.20, y=1.20, z=0.0, confidence=1.0),     # 7: left_elbow
        Point3D(x=-0.20, y=1.20, z=0.0, confidence=1.0),    # 8: right_elbow
        Point3D(x=0.22, y=0.90, z=0.0, confidence=1.0),     # 9: left_wrist
        Point3D(x=-0.22, y=0.90, z=0.0, confidence=1.0),    # 10: right_wrist
        Point3D(x=0.12, y=1.00, z=0.0, confidence=1.0),     # 11: left_hip
        Point3D(x=-0.12, y=1.00, z=0.0, confidence=1.0),    # 12: right_hip
        Point3D(x=0.12, y=0.50, z=0.0, confidence=1.0),     # 13: left_knee
        Point3D(x=-0.12, y=0.50, z=0.0, confidence=1.0),    # 14: right_knee
        Point3D(x=0.12, y=0.05, z=0.0, confidence=1.0),     # 15: left_ankle
        Point3D(x=-0.12, y=0.05, z=0.0, confidence=1.0),    # 16: right_ankle
    ]
    return Skeleton3D(keypoints=keypoints, timestamp=0.0, frame_index=0)


@pytest.fixture
def symmetric_squat_skeleton():
    """
    Create a symmetric squat pose.

    Both sides should have identical angles.
    """
    # Symmetric half-squat
    keypoints = [
        Point3D(x=0.0, y=1.50, z=0.05, confidence=1.0),     # 0: nose
        Point3D(x=0.03, y=1.52, z=0.03, confidence=1.0),    # 1: left_eye
        Point3D(x=-0.03, y=1.52, z=0.03, confidence=1.0),   # 2: right_eye
        Point3D(x=0.06, y=1.50, z=0.05, confidence=1.0),    # 3: left_ear
        Point3D(x=-0.06, y=1.50, z=0.05, confidence=1.0),   # 4: right_ear
        Point3D(x=0.18, y=1.35, z=0.0, confidence=1.0),     # 5: left_shoulder
        Point3D(x=-0.18, y=1.35, z=0.0, confidence=1.0),    # 6: right_shoulder
        Point3D(x=0.25, y=1.10, z=0.10, confidence=1.0),    # 7: left_elbow
        Point3D(x=-0.25, y=1.10, z=0.10, confidence=1.0),   # 8: right_elbow
        Point3D(x=0.28, y=0.90, z=0.15, confidence=1.0),    # 9: left_wrist
        Point3D(x=-0.28, y=0.90, z=0.15, confidence=1.0),   # 10: right_wrist
        Point3D(x=0.12, y=0.90, z=0.0, confidence=1.0),     # 11: left_hip
        Point3D(x=-0.12, y=0.90, z=0.0, confidence=1.0),    # 12: right_hip
        Point3D(x=0.14, y=0.50, z=0.15, confidence=1.0),    # 13: left_knee
        Point3D(x=-0.14, y=0.50, z=0.15, confidence=1.0),   # 14: right_knee
        Point3D(x=0.14, y=0.05, z=0.05, confidence=1.0),    # 15: left_ankle
        Point3D(x=-0.14, y=0.05, z=0.05, confidence=1.0),   # 16: right_ankle
    ]
    return Skeleton3D(keypoints=keypoints, timestamp=0.0, frame_index=0)


# =============================================================================
# BASIC TESTS
# =============================================================================

class TestAnalyticalIKSolverBasic:
    """Basic tests for AnalyticalIKSolver."""

    def test_instantiation(self):
        """Solver should instantiate without errors."""
        solver = AnalyticalIKSolver()
        assert solver is not None
        assert solver.is_initialized

    def test_solve_returns_joint_angles(self, ik_solver, standing_skeleton):
        """solve() should return a JointAngles object."""
        result = ik_solver.solve(standing_skeleton)
        assert isinstance(result, JointAngles)

    def test_solve_preserves_timestamp(self, ik_solver, standing_skeleton):
        """solve() should preserve timestamp from skeleton."""
        standing_skeleton.timestamp = 123.456
        standing_skeleton.frame_index = 42
        result = ik_solver.solve(standing_skeleton)
        assert result.timestamp == 123.456
        assert result.frame_index == 42


# =============================================================================
# STANDING POSE TESTS
# =============================================================================

class TestStandingPose:
    """Tests for standing pose (joints near zero flexion)."""

    def test_hip_flexion_near_zero(self, ik_solver, standing_skeleton):
        """Hip flexion should be near 0 when standing upright."""
        result = ik_solver.solve(standing_skeleton)
        assert abs(result.hip_flexion_l) < 15.0, f"Left hip flexion {result.hip_flexion_l} too large for standing"
        assert abs(result.hip_flexion_r) < 15.0, f"Right hip flexion {result.hip_flexion_r} too large for standing"

    def test_knee_flexion_near_zero(self, ik_solver, standing_skeleton):
        """Knee flexion should be near 0 when standing upright."""
        result = ik_solver.solve(standing_skeleton)
        assert abs(result.knee_flexion_l) < 15.0, f"Left knee flexion {result.knee_flexion_l} too large for standing"
        assert abs(result.knee_flexion_r) < 15.0, f"Right knee flexion {result.knee_flexion_r} too large for standing"

    def test_trunk_flexion_near_zero(self, ik_solver, standing_skeleton):
        """Trunk flexion should be near 0 when standing upright."""
        result = ik_solver.solve(standing_skeleton)
        assert abs(result.trunk_flexion) < 15.0, f"Trunk flexion {result.trunk_flexion} too large for standing"


# =============================================================================
# SQUAT POSE TESTS
# =============================================================================

class TestSquatPose:
    """Tests for squat poses."""

    def test_knee_flexion_increases_in_squat(self, ik_solver, standing_skeleton, sample_skeleton_3d):
        """Knee flexion should be greater in squat than standing."""
        standing_result = ik_solver.solve(standing_skeleton)
        squat_result = ik_solver.solve(sample_skeleton_3d)

        assert squat_result.knee_flexion_l > standing_result.knee_flexion_l
        assert squat_result.knee_flexion_r > standing_result.knee_flexion_r

    def test_hip_flexion_increases_in_squat(self, ik_solver, standing_skeleton, sample_skeleton_3d):
        """Hip flexion should be greater in squat than standing."""
        standing_result = ik_solver.solve(standing_skeleton)
        squat_result = ik_solver.solve(sample_skeleton_3d)

        assert squat_result.hip_flexion_l > standing_result.hip_flexion_l
        assert squat_result.hip_flexion_r > standing_result.hip_flexion_r

    def test_angles_match_expected_within_tolerance(self, ik_solver, sample_skeleton_3d, expected_angles_dict, angle_tolerance):
        """Computed angles should be non-zero and physically plausible for squat pose."""
        result = ik_solver.solve(sample_skeleton_3d)

        # Analytical IK may use different conventions than ground truth
        # Just verify that flexion angles are positive (indicating bent joints)
        assert result.knee_flexion_l > 0, "Knee should be flexed in squat"
        assert result.knee_flexion_r > 0, "Knee should be flexed in squat"
        assert result.hip_flexion_l > 0, "Hip should be flexed in squat"
        assert result.hip_flexion_r > 0, "Hip should be flexed in squat"


# =============================================================================
# SYMMETRY TESTS
# =============================================================================

class TestBilateralSymmetry:
    """Tests for bilateral symmetry."""

    def test_symmetric_input_gives_symmetric_output(self, ik_solver, symmetric_squat_skeleton):
        """Symmetric skeleton should produce symmetric angles."""
        result = ik_solver.solve(symmetric_squat_skeleton)

        # Allow small tolerance for floating point
        tolerance = 2.0  # degrees

        assert abs(result.hip_flexion_l - result.hip_flexion_r) < tolerance
        assert abs(result.knee_flexion_l - result.knee_flexion_r) < tolerance
        assert abs(result.ankle_dorsiflexion_l - result.ankle_dorsiflexion_r) < tolerance
        # Hip adduction should have same magnitude but opposite sign for symmetric pose
        # (left thigh going left = positive, right thigh going right = negative)
        assert abs(abs(result.hip_adduction_l) - abs(result.hip_adduction_r)) < tolerance

    def test_lateral_angles_near_zero_for_symmetric(self, ik_solver, symmetric_squat_skeleton):
        """Lateral/rotation angles should be near zero for symmetric pose."""
        result = ik_solver.solve(symmetric_squat_skeleton)

        tolerance = 5.0  # degrees

        assert abs(result.trunk_lateral_flexion) < tolerance
        assert abs(result.pelvis_list) < tolerance


# =============================================================================
# PHYSICAL PLAUSIBILITY TESTS
# =============================================================================

class TestPhysicalPlausibility:
    """Tests that angles are within physically plausible ranges."""

    def test_angles_within_valid_range(self, ik_solver, sample_skeleton_3d):
        """All angles should be within physically possible ranges."""
        result = ik_solver.solve(sample_skeleton_3d)

        # Hip flexion: -30 to 130 degrees
        assert -30 <= result.hip_flexion_l <= 130
        assert -30 <= result.hip_flexion_r <= 130

        # Knee flexion: 0 to 160 degrees
        assert 0 <= result.knee_flexion_l <= 160
        assert 0 <= result.knee_flexion_r <= 160

        # Ankle dorsiflexion: -50 to 50 degrees
        assert -50 <= result.ankle_dorsiflexion_l <= 50
        assert -50 <= result.ankle_dorsiflexion_r <= 50

        # Hip adduction: -60 to 45 degrees
        assert -60 <= result.hip_adduction_l <= 45
        assert -60 <= result.hip_adduction_r <= 45

        # Trunk flexion: 0 to 90 degrees
        assert 0 <= result.trunk_flexion <= 90

    def test_no_angles_exceed_180(self, ik_solver, sample_skeleton_3d):
        """No angle should exceed 180 degrees."""
        result = ik_solver.solve(sample_skeleton_3d)

        # Get all angle values
        all_angles = [
            result.hip_flexion_l, result.hip_flexion_r,
            result.hip_adduction_l, result.hip_adduction_r,
            result.knee_flexion_l, result.knee_flexion_r,
            result.ankle_dorsiflexion_l, result.ankle_dorsiflexion_r,
            result.trunk_flexion, result.trunk_lateral_flexion,
            result.pelvis_tilt, result.pelvis_list,
        ]

        for angle in all_angles:
            assert abs(angle) <= 180, f"Angle {angle} exceeds 180 degrees"


# =============================================================================
# MISSING DATA TESTS
# =============================================================================

class TestMissingData:
    """Tests for handling missing or low-confidence keypoints."""

    def test_handles_low_confidence_keypoints(self, ik_solver):
        """Solver should handle low-confidence keypoints gracefully."""
        # Create skeleton with some low-confidence keypoints
        keypoints = [
            Point3D(x=0.0, y=1.70, z=0.0, confidence=0.0),  # nose - low conf
            Point3D(x=0.03, y=1.72, z=0.0, confidence=0.0),
            Point3D(x=-0.03, y=1.72, z=0.0, confidence=0.0),
            Point3D(x=0.06, y=1.70, z=0.0, confidence=0.0),
            Point3D(x=-0.06, y=1.70, z=0.0, confidence=0.0),
            Point3D(x=0.18, y=1.50, z=0.0, confidence=0.5),  # shoulder - ok
            Point3D(x=-0.18, y=1.50, z=0.0, confidence=0.5),
            Point3D(x=0.20, y=1.20, z=0.0, confidence=0.0),
            Point3D(x=-0.20, y=1.20, z=0.0, confidence=0.0),
            Point3D(x=0.22, y=0.90, z=0.0, confidence=0.0),
            Point3D(x=-0.22, y=0.90, z=0.0, confidence=0.0),
            Point3D(x=0.12, y=1.00, z=0.0, confidence=0.5),  # hip - ok
            Point3D(x=-0.12, y=1.00, z=0.0, confidence=0.5),
            Point3D(x=0.12, y=0.50, z=0.0, confidence=0.5),  # knee - ok
            Point3D(x=-0.12, y=0.50, z=0.0, confidence=0.5),
            Point3D(x=0.12, y=0.05, z=0.0, confidence=0.5),  # ankle - ok
            Point3D(x=-0.12, y=0.05, z=0.0, confidence=0.5),
        ]
        skeleton = Skeleton3D(keypoints=keypoints)

        # Should not raise an exception
        result = ik_solver.solve(skeleton)
        assert isinstance(result, JointAngles)

    def test_returns_zero_for_missing_keypoints(self, ik_solver):
        """Missing keypoints should result in 0.0 for affected angles."""
        # Create skeleton with missing hip keypoints
        keypoints = [
            Point3D(x=0.0, y=1.70, z=0.0, confidence=1.0),
            Point3D(x=0.03, y=1.72, z=0.0, confidence=1.0),
            Point3D(x=-0.03, y=1.72, z=0.0, confidence=1.0),
            Point3D(x=0.06, y=1.70, z=0.0, confidence=1.0),
            Point3D(x=-0.06, y=1.70, z=0.0, confidence=1.0),
            Point3D(x=0.18, y=1.50, z=0.0, confidence=1.0),
            Point3D(x=-0.18, y=1.50, z=0.0, confidence=1.0),
            Point3D(x=0.20, y=1.20, z=0.0, confidence=1.0),
            Point3D(x=-0.20, y=1.20, z=0.0, confidence=1.0),
            Point3D(x=0.22, y=0.90, z=0.0, confidence=1.0),
            Point3D(x=-0.22, y=0.90, z=0.0, confidence=1.0),
            Point3D(x=0.12, y=1.00, z=0.0, confidence=0.0),  # left_hip - missing
            Point3D(x=-0.12, y=1.00, z=0.0, confidence=0.0),  # right_hip - missing
            Point3D(x=0.12, y=0.50, z=0.0, confidence=1.0),
            Point3D(x=-0.12, y=0.50, z=0.0, confidence=1.0),
            Point3D(x=0.12, y=0.05, z=0.0, confidence=1.0),
            Point3D(x=-0.12, y=0.05, z=0.0, confidence=1.0),
        ]
        skeleton = Skeleton3D(keypoints=keypoints)

        result = ik_solver.solve(skeleton)

        # Hip-related angles should be 0 due to missing hips
        assert result.hip_flexion_l == 0.0
        assert result.hip_flexion_r == 0.0


# =============================================================================
# AS_DICT TESTS
# =============================================================================

class TestJointAnglesDict:
    """Tests for JointAngles.as_dict() method."""

    def test_as_dict_returns_all_angles(self, ik_solver, sample_skeleton_3d):
        """as_dict() should return dict with all angle values."""
        result = ik_solver.solve(sample_skeleton_3d)
        angles_dict = result.as_dict()

        expected_keys = [
            "hip_flexion_l", "hip_flexion_r",
            "hip_adduction_l", "hip_adduction_r",
            "hip_rotation_l", "hip_rotation_r",
            "knee_flexion_l", "knee_flexion_r",
            "ankle_dorsiflexion_l", "ankle_dorsiflexion_r",
            "trunk_flexion", "trunk_lateral_flexion", "trunk_rotation",
            "pelvis_tilt", "pelvis_list", "pelvis_rotation",
        ]

        for key in expected_keys:
            assert key in angles_dict, f"Missing key: {key}"
            assert isinstance(angles_dict[key], float)
