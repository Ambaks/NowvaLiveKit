"""Tests for MJCF model creation, loading, and basic properties."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from biomechanics_v2.model import MujocoSkeleton
from biomechanics.skeleton.definition import SkeletonModel


class TestModelLoads:
    def test_model_compiles_without_error(self):
        skeleton = MujocoSkeleton()
        assert skeleton.model is not None
        assert skeleton.data is not None

    def test_n_dof_is_20(self):
        skeleton = MujocoSkeleton()
        assert skeleton.n_dof() == 20
        assert skeleton.model.nq == 20
        assert skeleton.model.nv == 20

    def test_scaled_model_compiles(self):
        skeleton = MujocoSkeleton(height_m=1.885, weight_kg=85.0)
        assert skeleton.n_dof() == 20


class TestJointNames:
    def test_all_expected_bodies_exist(self):
        skeleton = MujocoSkeleton()
        expected_bodies = [
            "pelvis", "trunk", "head",
            "L_hip", "R_hip", "L_knee", "R_knee",
            "L_ankle", "R_ankle", "L_toe", "R_toe",
        ]
        positions = skeleton.get_body_positions()
        for name in expected_bodies:
            assert name in positions, f"Missing body: {name}"

    def test_joint_index_mapping(self):
        skeleton = MujocoSkeleton()
        assert skeleton.get_joint_index("pelvis", "tx") == 0
        assert skeleton.get_joint_index("pelvis", "ty") == 1
        assert skeleton.get_joint_index("pelvis", "tz") == 2
        assert skeleton.get_joint_index("pelvis", "rx") == 3
        assert skeleton.get_joint_index("trunk", "rx") == 6
        assert skeleton.get_joint_index("L_hip", "rx") == 8
        assert skeleton.get_joint_index("R_hip", "rx") == 11
        assert skeleton.get_joint_index("L_knee", "rx") == 14
        assert skeleton.get_joint_index("R_knee", "rx") == 15
        assert skeleton.get_joint_index("L_ankle", "rx") == 16
        assert skeleton.get_joint_index("R_ankle", "rx") == 18

    def test_invalid_joint_raises(self):
        skeleton = MujocoSkeleton()
        with pytest.raises(KeyError):
            skeleton.get_joint_index("nonexistent", "rx")


class TestBounds:
    def test_bounds_match_v1(self):
        v1_skeleton = SkeletonModel()
        v2_skeleton = MujocoSkeleton()

        v1_bounds = v1_skeleton.bounds()
        v2_bounds = v2_skeleton.get_bounds()

        assert len(v1_bounds) == len(v2_bounds) == 20

        for i, ((v1_lo, v1_hi), (v2_lo, v2_hi)) in enumerate(zip(v1_bounds, v2_bounds)):
            if np.isinf(v1_lo):
                assert np.isinf(v2_lo), f"DOF {i}: expected -inf, got {v2_lo}"
            else:
                assert abs(v1_lo - v2_lo) < 0.001, f"DOF {i} lower: V1={v1_lo}, V2={v2_lo}"

            if np.isinf(v1_hi):
                assert np.isinf(v2_hi), f"DOF {i}: expected inf, got {v2_hi}"
            else:
                assert abs(v1_hi - v2_hi) < 0.001, f"DOF {i} upper: V1={v1_hi}, V2={v2_hi}"


class TestNeutralPose:
    def test_pelvis_at_correct_height(self):
        skeleton = MujocoSkeleton()
        q = skeleton.neutral_q()
        skeleton.set_qpos(q)
        skeleton.forward()
        positions = skeleton.get_body_positions()
        assert abs(positions["pelvis"][1] - 0.95) < 0.001

    def test_ankles_near_floor(self):
        skeleton = MujocoSkeleton()
        q = skeleton.neutral_q()
        skeleton.set_qpos(q)
        skeleton.forward()
        positions = skeleton.get_body_positions()
        # At neutral, ankle Y ≈ pelvis_height (0.95) because legs extend in Z, not Y
        # Toes are 0.20m below ankles
        assert positions["L_toe"][1] < positions["L_ankle"][1]
        assert positions["R_toe"][1] < positions["R_ankle"][1]

    def test_scaled_pelvis_height(self):
        height = 1.885
        skeleton = MujocoSkeleton(height_m=height)
        q = skeleton.neutral_q()
        skeleton.set_qpos(q)
        skeleton.forward()
        positions = skeleton.get_body_positions()
        expected_pelvis_y = 0.95 * (height / 1.75)
        assert abs(positions["pelvis"][1] - expected_pelvis_y) < 0.001


class TestQposRoundTrip:
    def test_set_get_roundtrip(self):
        skeleton = MujocoSkeleton()
        rng = np.random.default_rng(123)
        bounds = skeleton.get_bounds()

        q = np.zeros(20)
        q[1] = 0.95
        for i in range(3, 20):
            lo, hi = bounds[i]
            if np.isinf(lo) or np.isinf(hi):
                continue
            q[i] = rng.uniform(lo, hi)

        skeleton.set_qpos(q)
        q_back = skeleton.get_qpos()
        np.testing.assert_allclose(q, q_back, atol=1e-10)


class TestXmlExport:
    def test_to_xml_returns_valid_xml(self):
        skeleton = MujocoSkeleton()
        xml = skeleton.to_xml()
        assert "<mujoco" in xml
        assert "pelvis" in xml
        assert "L_knee_rx" in xml
