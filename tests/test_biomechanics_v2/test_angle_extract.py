"""Tests for Session 3: FK helpers and angle extraction.

Verifies:
1. Standing pose produces expected angles (trunk ~180°, knees ~0°, hips ~0°)
2. Deep squat produces correct ranges
3. Asymmetric poses produce differing L/R angles
4. Comparison against V1 angle_extract for shared q-vectors
5. FK helper functions produce valid results
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.mujoco_fk import (
    body_com_world,
    inverse_dynamics,
    joint_jacobian,
    joint_world_positions,
    midfoot_xz,
)
from biomechanics_v2.solver.angle_extract import q_to_joint_angles


@pytest.fixture
def skeleton():
    return MujocoSkeleton(height_m=1.75, weight_kg=75.0)


@pytest.fixture
def tall_skeleton():
    return MujocoSkeleton(height_m=1.885, weight_kg=85.0)


def _standing_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Neutral standing pose — pelvis at default height, all rotations zero."""
    return skeleton.neutral_q()


def _deep_squat_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Deep squat: high hip/knee flexion, moderate ankle DF."""
    q = skeleton.neutral_q()
    q[skeleton.get_joint_index("pelvis", "ty")] = 0.55
    q[skeleton.get_joint_index("L_hip", "rx")] = math.radians(105)
    q[skeleton.get_joint_index("R_hip", "rx")] = math.radians(105)
    q[skeleton.get_joint_index("L_knee", "rx")] = math.radians(130)
    q[skeleton.get_joint_index("R_knee", "rx")] = math.radians(130)
    q[skeleton.get_joint_index("L_ankle", "rx")] = math.radians(25)
    q[skeleton.get_joint_index("R_ankle", "rx")] = math.radians(25)
    q[skeleton.get_joint_index("trunk", "rx")] = math.radians(30)
    return q


def _asymmetric_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Asymmetric pose: left ankle more dorsiflexed, different hip rotations."""
    q = _deep_squat_q(skeleton)
    q[skeleton.get_joint_index("L_ankle", "rx")] = math.radians(35)
    q[skeleton.get_joint_index("R_ankle", "rx")] = math.radians(15)
    q[skeleton.get_joint_index("L_hip", "rz")] = math.radians(10)
    q[skeleton.get_joint_index("R_hip", "rz")] = math.radians(-5)
    q[skeleton.get_joint_index("L_ankle", "ry")] = math.radians(12)
    q[skeleton.get_joint_index("R_ankle", "ry")] = math.radians(-8)
    return q


# =====================================================================
# FK helper tests
# =====================================================================

class TestJointWorldPositions:
    def test_standing_pelvis_height(self, skeleton):
        q = _standing_q(skeleton)
        positions = joint_world_positions(skeleton, q)
        assert abs(positions["pelvis"][1] - 0.95) < 0.02

    def test_standing_ankles_at_pelvis_height(self, skeleton):
        """At neutral pose (q=0), legs extend horizontally (thigh -Z, shin +Z).

        Ankles end up near pelvis Y because the vertical offsets cancel.
        This is expected — the 'standing' q is geometric neutral, not a
        physically standing pose.
        """
        q = _standing_q(skeleton)
        positions = joint_world_positions(skeleton, q)
        pelvis_y = positions["pelvis"][1]
        for side in ("L", "R"):
            ankle_y = positions[f"{side}_ankle"][1]
            assert abs(ankle_y - pelvis_y) < 0.05, (
                f"{side} ankle Y={ankle_y:.3f} should be near pelvis Y={pelvis_y:.3f}"
            )

    def test_returns_all_bodies(self, skeleton):
        q = _standing_q(skeleton)
        positions = joint_world_positions(skeleton, q)
        expected_bodies = [
            "pelvis", "trunk", "head",
            "L_hip", "R_hip", "L_knee", "R_knee",
            "L_ankle", "R_ankle", "L_toe", "R_toe",
        ]
        for body in expected_bodies:
            assert body in positions
            assert positions[body].shape == (3,)


class TestBodyComWorld:
    def test_com_within_body_extent(self, skeleton):
        q = _standing_q(skeleton)
        com = body_com_world(skeleton, q)
        assert com.shape == (3,)
        assert 0.3 < com[1] < 1.2, f"COM Y outside reasonable range: {com[1]}"

    def test_com_above_floor(self, skeleton):
        q = _deep_squat_q(skeleton)
        com = body_com_world(skeleton, q)
        assert com[1] > 0.0


class TestMidfootXZ:
    def test_standing_midfoot(self, skeleton):
        q = _standing_q(skeleton)
        mid = midfoot_xz(skeleton, q)
        assert mid.shape == (2,)
        assert abs(mid[0]) < 0.1, "Midfoot X should be near center"


class TestInverseDynamics:
    def test_static_pose_gravity_torques(self, skeleton):
        q = _standing_q(skeleton)
        qvel = np.zeros(20)
        qacc = np.zeros(20)
        torques = inverse_dynamics(skeleton, q, qvel, qacc)
        assert torques.shape == (20,)
        # Gravity produces non-zero torques on some joints
        assert np.any(np.abs(torques) > 0.01)


class TestJointJacobian:
    def test_jacobian_shape(self, skeleton):
        q = _standing_q(skeleton)
        jac = joint_jacobian(skeleton, q, "L_ankle")
        assert jac.shape[0] == 3
        assert jac.shape[1] == skeleton.model.nv

    def test_jacobian_nonzero(self, skeleton):
        q = _standing_q(skeleton)
        jac = joint_jacobian(skeleton, q, "L_ankle")
        assert np.any(np.abs(jac) > 1e-6)


# =====================================================================
# Angle extraction tests
# =====================================================================

class TestStandingPose:
    def test_trunk_flexion_upright(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.trunk_flexion - 180.0) < 5.0, (
            f"Standing trunk_flexion should be ~180°, got {angles.trunk_flexion}"
        )

    def test_knee_flexion_zero(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.knee_flexion_l) < 2.0
        assert abs(angles.knee_flexion_r) < 2.0

    def test_hip_flexion_zero(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.hip_flexion_l) < 2.0
        assert abs(angles.hip_flexion_r) < 2.0

    def test_ankle_df_zero(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.ankle_dorsiflexion_l) < 2.0
        assert abs(angles.ankle_dorsiflexion_r) < 2.0

    def test_stance_width_positive(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.stance_width_ratio > 0.5

    def test_timestamp_frame_index(self, skeleton):
        q = _standing_q(skeleton)
        angles = q_to_joint_angles(skeleton, q, timestamp=1.5, frame_index=42)
        assert angles.timestamp == 1.5
        assert angles.frame_index == 42


class TestDeepSquat:
    def test_knee_flexion_high(self, skeleton):
        q = _deep_squat_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.knee_flexion_l > 100.0
        assert angles.knee_flexion_r > 100.0

    def test_hip_flexion_high(self, skeleton):
        q = _deep_squat_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.hip_flexion_l > 80.0
        assert angles.hip_flexion_r > 80.0

    def test_ankle_dorsiflexion_nonzero(self, skeleton):
        q = _deep_squat_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.ankle_dorsiflexion_l > 15.0
        assert angles.ankle_dorsiflexion_r > 15.0

    def test_trunk_flexion_below_180(self, skeleton):
        q = _deep_squat_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.trunk_flexion < 175.0, (
            f"Trunk should lean forward in deep squat, got {angles.trunk_flexion}"
        )

    def test_foot_confidence_set(self, skeleton):
        q = _deep_squat_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.foot_confidence_l == 1.0
        assert angles.foot_confidence_r == 1.0


class TestAsymmetricPose:
    def test_ankle_df_differs(self, skeleton):
        q = _asymmetric_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.ankle_dorsiflexion_l - angles.ankle_dorsiflexion_r) > 10.0

    def test_hip_rotation_differs(self, skeleton):
        q = _asymmetric_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.hip_rotation_l - angles.hip_rotation_r) > 5.0

    def test_toe_out_differs(self, skeleton):
        q = _asymmetric_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.toe_out_angle_l - angles.toe_out_angle_r) > 10.0

    def test_toe_out_values(self, skeleton):
        q = _asymmetric_q(skeleton)
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.toe_out_angle_l - 12.0) < 1.0
        assert abs(angles.toe_out_angle_r - (-8.0)) < 1.0


class TestV1Comparison:
    """Compare V2 angle extraction against V1 for matching q-vectors.

    Uses V1's SkeletonModel + q_to_joint_angles as ground truth.
    Angles that are DOF-derived should match exactly. FK-derived angles
    (hip_adduction, knee_valgus, trunk_flexion) may differ slightly
    due to FK implementation differences.
    """

    @pytest.fixture
    def v1_skeleton(self):
        try:
            from biomechanics.skeleton.definition import SkeletonModel
            return SkeletonModel()
        except Exception:
            pytest.skip("V1 SkeletonModel not available")

    def _make_test_poses(self, skeleton: MujocoSkeleton) -> list[np.ndarray]:
        """5 test q-vectors covering standing through deep squat."""
        poses = []
        poses.append(_standing_q(skeleton))
        poses.append(_deep_squat_q(skeleton))
        poses.append(_asymmetric_q(skeleton))

        # Moderate squat
        q = skeleton.neutral_q()
        q[skeleton.get_joint_index("pelvis", "ty")] = 0.75
        q[skeleton.get_joint_index("L_hip", "rx")] = math.radians(60)
        q[skeleton.get_joint_index("R_hip", "rx")] = math.radians(60)
        q[skeleton.get_joint_index("L_knee", "rx")] = math.radians(70)
        q[skeleton.get_joint_index("R_knee", "rx")] = math.radians(70)
        q[skeleton.get_joint_index("L_ankle", "rx")] = math.radians(15)
        q[skeleton.get_joint_index("R_ankle", "rx")] = math.radians(15)
        poses.append(q)

        # Slight forward lean
        q = skeleton.neutral_q()
        q[skeleton.get_joint_index("trunk", "rx")] = math.radians(20)
        q[skeleton.get_joint_index("pelvis", "rx")] = math.radians(10)
        poses.append(q)

        return poses

    def test_dof_derived_angles_match_v1(self, skeleton, v1_skeleton):
        from biomechanics.optimizer.angle_extract import (
            q_to_joint_angles as v1_q_to_joint_angles,
        )

        tolerance_deg = 2.0
        poses = self._make_test_poses(skeleton)

        for pose_idx, q in enumerate(poses):
            v2_angles = q_to_joint_angles(skeleton, q)
            v1_angles = v1_q_to_joint_angles(v1_skeleton, q)

            dof_fields = [
                "hip_flexion_l", "hip_flexion_r",
                "knee_flexion_l", "knee_flexion_r",
                "ankle_dorsiflexion_l", "ankle_dorsiflexion_r",
                "pelvis_tilt", "pelvis_rotation",
                "trunk_lateral_flexion",
            ]
            for field in dof_fields:
                v2_val = getattr(v2_angles, field)
                v1_val = getattr(v1_angles, field)
                assert abs(v2_val - v1_val) < tolerance_deg, (
                    f"Pose {pose_idx}, {field}: V2={v2_val:.2f}° vs V1={v1_val:.2f}°"
                )

    def test_trunk_flexion_close_to_v1(self, skeleton, v1_skeleton):
        from biomechanics.optimizer.angle_extract import (
            q_to_joint_angles as v1_q_to_joint_angles,
        )

        tolerance_deg = 5.0
        poses = self._make_test_poses(skeleton)

        for pose_idx, q in enumerate(poses):
            v2_angles = q_to_joint_angles(skeleton, q)
            v1_angles = v1_q_to_joint_angles(v1_skeleton, q)
            assert abs(v2_angles.trunk_flexion - v1_angles.trunk_flexion) < tolerance_deg, (
                f"Pose {pose_idx}: V2 trunk_flexion={v2_angles.trunk_flexion:.2f}° "
                f"vs V1={v1_angles.trunk_flexion:.2f}°"
            )


class TestScaledSkeleton:
    def test_tall_skeleton_standing(self, tall_skeleton):
        q = tall_skeleton.neutral_q()
        angles = q_to_joint_angles(tall_skeleton, q)
        assert abs(angles.trunk_flexion - 180.0) < 5.0
        assert abs(angles.knee_flexion_l) < 2.0

    def test_tall_skeleton_deep_squat(self, tall_skeleton):
        q = _deep_squat_q(tall_skeleton)
        angles = q_to_joint_angles(tall_skeleton, q)
        assert angles.knee_flexion_l > 100.0
        assert angles.hip_flexion_l > 80.0
