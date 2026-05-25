"""Tests that MuJoCo FK matches V1 FK for the same q-vectors."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.forward_kin import forward_kinematics
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics_v2.model import MujocoSkeleton

JOINT_NAMES = [
    "pelvis", "trunk", "head",
    "L_hip", "R_hip", "L_knee", "R_knee",
    "L_ankle", "R_ankle", "L_toe", "R_toe",
]

FK_TOLERANCE_MM = 5.0


def _compare_fk(v1_skeleton, v2_skeleton, q_vector):
    """Run FK on both models, return max error in mm."""
    v1_transforms = forward_kinematics(v1_skeleton, q_vector)
    v2_skeleton.set_qpos(q_vector)
    v2_skeleton.forward()
    v2_positions = v2_skeleton.get_body_positions()

    max_error_mm = 0.0
    for name in JOINT_NAMES:
        v1_pos = v1_transforms[name][:3, 3]
        v2_pos = v2_positions[name]
        error_mm = np.linalg.norm(v1_pos - v2_pos) * 1000
        max_error_mm = max(max_error_mm, error_mm)

    return max_error_mm


class TestFKMatchRandomPoses:
    def test_10_random_q_vectors(self):
        v1_skeleton = SkeletonModel()
        v2_skeleton = MujocoSkeleton()
        bounds = v1_skeleton.bounds()
        rng = np.random.default_rng(42)

        for trial in range(10):
            q = np.zeros(20)
            q[1] = 0.95
            for i in range(3, 20):
                lo, hi = bounds[i]
                if np.isinf(lo) or np.isinf(hi):
                    continue
                q[i] = rng.uniform(lo, hi)

            max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
            assert max_error < FK_TOLERANCE_MM, (
                f"Trial {trial}: FK error {max_error:.3f} mm exceeds {FK_TOLERANCE_MM} mm"
            )


class TestFKMatchDeepSquat:
    def test_deep_squat_pose(self):
        v1_skeleton = SkeletonModel()
        v2_skeleton = MujocoSkeleton()

        q = np.zeros(20)
        q[1] = 0.95
        q[6] = np.radians(20)      # trunk forward lean
        q[8] = np.radians(100)     # L_hip flexion
        q[11] = np.radians(100)    # R_hip flexion
        q[14] = np.radians(140)    # L_knee flexion
        q[15] = np.radians(140)    # R_knee flexion
        q[16] = np.radians(30)     # L_ankle dorsiflexion
        q[18] = np.radians(30)     # R_ankle dorsiflexion

        max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
        assert max_error < FK_TOLERANCE_MM

    def test_asymmetric_squat(self):
        v1_skeleton = SkeletonModel()
        v2_skeleton = MujocoSkeleton()

        q = np.zeros(20)
        q[1] = 0.95
        q[6] = np.radians(15)
        q[8] = np.radians(90)      # L_hip flexion
        q[9] = np.radians(10)      # L_hip adduction
        q[11] = np.radians(80)     # R_hip flexion
        q[12] = np.radians(-5)     # R_hip abduction
        q[14] = np.radians(120)    # L_knee
        q[15] = np.radians(100)    # R_knee
        q[16] = np.radians(25)     # L_ankle DF
        q[17] = np.radians(10)     # L_ankle eversion
        q[18] = np.radians(15)     # R_ankle DF

        max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
        assert max_error < FK_TOLERANCE_MM


class TestFKMatchScaled:
    def test_scaled_to_user_height(self):
        height = 1.885
        weight = 80.0
        v1_skeleton = scale_skeleton(height, weight)
        v2_skeleton = MujocoSkeleton(height_m=height, weight_kg=weight)

        scale_factor = height / 1.75
        q = np.zeros(20)
        q[1] = 0.95 * scale_factor
        q[6] = np.radians(20)
        q[8] = np.radians(100)
        q[11] = np.radians(100)
        q[14] = np.radians(130)
        q[15] = np.radians(130)
        q[16] = np.radians(25)
        q[18] = np.radians(25)

        max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
        assert max_error < FK_TOLERANCE_MM

    def test_scaled_random_poses(self):
        height = 1.885
        weight = 80.0
        v1_skeleton = scale_skeleton(height, weight)
        v2_skeleton = MujocoSkeleton(height_m=height, weight_kg=weight)
        bounds = v1_skeleton.bounds()
        rng = np.random.default_rng(99)

        scale_factor = height / 1.75
        for trial in range(5):
            q = np.zeros(20)
            q[1] = 0.95 * scale_factor
            for i in range(3, 20):
                lo, hi = bounds[i]
                if np.isinf(lo) or np.isinf(hi):
                    continue
                q[i] = rng.uniform(lo, hi)

            max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
            assert max_error < FK_TOLERANCE_MM, (
                f"Scaled trial {trial}: FK error {max_error:.3f} mm"
            )


class TestFKMatchWithPelvisRotation:
    def test_pelvis_rotation_affects_children(self):
        v1_skeleton = SkeletonModel()
        v2_skeleton = MujocoSkeleton()

        q = np.zeros(20)
        q[1] = 0.95
        q[3] = np.radians(10)     # pelvis rx
        q[4] = np.radians(-5)     # pelvis ry
        q[5] = np.radians(8)      # pelvis rz
        q[8] = np.radians(60)     # L_hip rx
        q[14] = np.radians(80)    # L_knee rx

        max_error = _compare_fk(v1_skeleton, v2_skeleton, q)
        assert max_error < FK_TOLERANCE_MM
