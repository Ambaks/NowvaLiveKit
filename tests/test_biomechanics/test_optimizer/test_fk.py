"""Tests for skeleton definition, anthropometry, and forward kinematics."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel, JOINT_DEFS_20DOF
from biomechanics.skeleton.anthropometry import (
    scale_skeleton,
    SEGMENT_MASS_FRACTIONS,
)
from biomechanics.skeleton.forward_kin import (
    forward_kinematics,
    joint_world_position,
    body_com_world,
    load_reference_point,
    midfoot_xz,
)


# ── Skeleton definition tests ──


class TestSkeletonModel:
    def test_n_dof_is_20(self):
        skeleton = SkeletonModel()
        assert skeleton.n_dof == 20

    def test_n_joints_is_8(self):
        skeleton = SkeletonModel()
        assert skeleton.n_joints == 8

    def test_dof_index_pelvis_tx(self):
        skeleton = SkeletonModel()
        assert skeleton.dof_index("pelvis", "tx") == 0

    def test_dof_index_r_ankle_ry(self):
        skeleton = SkeletonModel()
        idx = skeleton.dof_index("R_ankle", "ry")
        assert 0 <= idx < 20

    def test_joint_dofs_slice(self):
        skeleton = SkeletonModel()
        s = skeleton.joint_dofs("pelvis")
        assert s.stop - s.start == 6

        s = skeleton.joint_dofs("L_knee")
        assert s.stop - s.start == 1

    def test_bounds_length(self):
        skeleton = SkeletonModel()
        b = skeleton.bounds()
        assert len(b) == 20

    def test_bounds_rotation_in_radians(self):
        skeleton = SkeletonModel()
        b = skeleton.bounds()
        # L_knee rx: [0, 150] degrees -> [0, 2.618] radians
        idx = skeleton.dof_index("L_knee", "rx")
        lo, hi = b[idx]
        assert abs(lo - 0.0) < 1e-6
        assert abs(hi - np.radians(150.0)) < 1e-6

    def test_bounds_translation_unbounded(self):
        skeleton = SkeletonModel()
        b = skeleton.bounds()
        lo, hi = b[0]  # pelvis tx
        assert lo == -np.inf
        assert hi == np.inf

    def test_neutral_q(self):
        skeleton = SkeletonModel()
        q = skeleton.neutral_q()
        assert len(q) == 20
        assert q[1] == pytest.approx(0.95)  # pelvis ty
        # All rotations zero
        assert np.all(q[3:] == 0)


# ── Anthropometry tests ──


class TestAnthropometry:
    def test_mass_fractions_sum_to_one(self):
        total = sum(SEGMENT_MASS_FRACTIONS.values())
        assert abs(total - 1.0) < 0.01

    def test_scale_skeleton_offsets(self):
        skeleton = scale_skeleton(1.75, 75.0)
        # At reference height, offsets should be unchanged
        assert skeleton.offset(0)[1] == pytest.approx(0.95, abs=1e-6)

        tall = scale_skeleton(1.90, 85.0)
        factor = 1.90 / 1.75
        assert tall.offset(0)[1] == pytest.approx(0.95 * factor, abs=1e-4)

    def test_joint_masses_set(self):
        skeleton = scale_skeleton(1.78, 80.0)
        assert skeleton.joint_masses is not None
        assert np.sum(skeleton.joint_masses) > 0

    def test_scale_preserves_dof_count(self):
        skeleton = scale_skeleton(1.60, 55.0)
        assert skeleton.n_dof == 20


# ── Forward kinematics tests ──


class TestForwardKinematics:
    @pytest.fixture
    def skeleton(self):
        return scale_skeleton(1.78, 80.0)

    def test_tpose_pelvis_at_origin_offset(self, skeleton):
        q = skeleton.neutral_q()
        xforms = forward_kinematics(skeleton, q)
        pelvis_pos = xforms["pelvis"][:3, 3]
        assert pelvis_pos[0] == pytest.approx(0.0, abs=1e-6)
        assert pelvis_pos[1] == pytest.approx(q[1], abs=1e-6)
        assert pelvis_pos[2] == pytest.approx(0.0, abs=1e-6)

    def test_tpose_joint_positions_on_y_axis(self, skeleton):
        """In T-pose, trunk should be above pelvis along y."""
        q = skeleton.neutral_q()
        xforms = forward_kinematics(skeleton, q)
        pelvis_y = xforms["pelvis"][1, 3]
        trunk_y = xforms["trunk"][1, 3]
        assert trunk_y > pelvis_y

    def test_tpose_hips_symmetric(self, skeleton):
        q = skeleton.neutral_q()
        l_hip = joint_world_position(skeleton, q, "L_hip")
        r_hip = joint_world_position(skeleton, q, "R_hip")
        assert l_hip[0] == pytest.approx(-r_hip[0], abs=1e-6)
        assert l_hip[1] == pytest.approx(r_hip[1], abs=1e-6)
        assert l_hip[2] == pytest.approx(r_hip[2], abs=1e-6)

    def test_tpose_ankles_below_knees(self, skeleton):
        q = skeleton.neutral_q()
        for side in ("L", "R"):
            knee_pos = joint_world_position(skeleton, q, f"{side}_knee")
            ankle_pos = joint_world_position(skeleton, q, f"{side}_ankle")
            assert ankle_pos[1] < knee_pos[1]

    def test_knee_flexion_moves_ankle(self, skeleton):
        """Setting L_knee rx=90 degrees should move ankle forward and up relative to straight leg."""
        q = skeleton.neutral_q()
        ankle_straight = joint_world_position(skeleton, q, "L_ankle")

        q_bent = q.copy()
        q_bent[skeleton.dof_index("L_knee", "rx")] = np.radians(90.0)
        ankle_bent = joint_world_position(skeleton, q_bent, "L_ankle")

        # Ankle should have moved (not in same position)
        displacement = np.linalg.norm(ankle_bent - ankle_straight)
        assert displacement > 0.1

        # With 90-degree knee flexion, ankle should be more forward (positive x in our convention)
        # and higher (more positive y) than straight leg
        assert ankle_bent[1] > ankle_straight[1]

    def test_tpose_com_near_y_axis(self, skeleton):
        """COM at T-pose should lie close to the y-axis."""
        q = skeleton.neutral_q()
        com = body_com_world(skeleton, q, weight_kg=80.0)
        assert abs(com[0]) < 0.05  # within 5cm of y-axis
        assert abs(com[2]) < 0.05

    def test_com_is_between_feet_and_head(self, skeleton):
        q = skeleton.neutral_q()
        com = body_com_world(skeleton, q, weight_kg=80.0)
        ankle_y = joint_world_position(skeleton, q, "L_ankle")[1]
        trunk_y = joint_world_position(skeleton, q, "trunk")[1]
        assert ankle_y < com[1] < trunk_y + 0.5

    def test_load_reference_above_trunk(self, skeleton):
        """Load reference should be above and close to trunk position."""
        q = skeleton.neutral_q()
        trunk_pos = joint_world_position(skeleton, q, "trunk")
        load_ref = load_reference_point(skeleton, q)
        assert load_ref[1] > trunk_pos[1]
        assert abs(load_ref[0] - trunk_pos[0]) < 0.05

    def test_fk_deterministic(self, skeleton):
        """Same q should produce same result."""
        q = skeleton.neutral_q()
        q[skeleton.dof_index("L_hip", "rx")] = np.radians(45)
        pos1 = joint_world_position(skeleton, q, "L_knee")
        pos2 = joint_world_position(skeleton, q, "L_knee")
        np.testing.assert_array_equal(pos1, pos2)

    def test_pelvis_translation(self, skeleton):
        """Moving pelvis tx should shift all joints."""
        q = skeleton.neutral_q()
        baseline = joint_world_position(skeleton, q, "trunk")

        q_shifted = q.copy()
        q_shifted[0] = 0.5  # move pelvis 0.5m in x
        shifted = joint_world_position(skeleton, q_shifted, "trunk")

        assert shifted[0] == pytest.approx(baseline[0] + 0.5, abs=1e-4)
        assert shifted[1] == pytest.approx(baseline[1], abs=1e-4)

    def test_pelvis_rotation_affects_children(self, skeleton):
        """Pelvis yaw should rotate hip positions."""
        q = skeleton.neutral_q()
        q[skeleton.dof_index("pelvis", "ry")] = np.radians(90)
        l_hip = joint_world_position(skeleton, q, "L_hip")
        # With 90-degree yaw, the x offset should now point in z direction
        assert abs(l_hip[2]) > 0.05

    def test_midfoot_xz_symmetric(self, skeleton):
        q = skeleton.neutral_q()
        mid = midfoot_xz(skeleton, q)
        assert abs(mid[0]) < 0.05  # near x=0
        # xz midpoint should be symmetric


# ── Synthetic fixture tests ──


class TestSyntheticFixtures:
    @pytest.fixture
    def skeleton(self):
        return scale_skeleton(1.78, 80.0)

    def test_clean_squat_fixture_shape(self, skeleton):
        from .synth_fixtures import _make_clean_squat_q
        q_traj = _make_clean_squat_q(skeleton, n_frames=60)
        assert q_traj.shape == (60, 20)

    def test_clean_squat_standing_frames_near_neutral(self, skeleton):
        from .synth_fixtures import _make_clean_squat_q
        q_traj = _make_clean_squat_q(skeleton, n_frames=60)
        q_neutral = skeleton.neutral_q()
        # Frame 0 and frame 59 should be near standing
        for t in [0, 59]:
            rot_diff = np.abs(q_traj[t, 6:] - q_neutral[6:])  # skip pelvis trans+rot
            assert np.max(rot_diff) < np.radians(5.0)

    def test_bad_squat_has_larger_trunk_flex(self, skeleton):
        from .synth_fixtures import (
            _make_clean_squat_q, _make_bad_squat_q
        )
        clean = _make_clean_squat_q(skeleton)
        bad = _make_bad_squat_q(skeleton)
        trunk_idx = skeleton.dof_index("trunk", "rx")
        # At bottom (frame 30), bad squat should have more trunk flexion
        assert bad[30, trunk_idx] > clean[30, trunk_idx]

    def test_landmark_generation_shape(self, skeleton):
        from .synth_fixtures import (
            _make_clean_squat_q, generate_landmarks_from_q
        )
        q_traj = _make_clean_squat_q(skeleton, n_frames=10)
        landmarks = generate_landmarks_from_q(skeleton, q_traj)
        assert landmarks.shape == (10, 8, 4)
        assert np.all(landmarks[:, :, 3] == 1.0)  # all visible


# ── Performance test ──


class TestPerformance:
    def test_fk_speed(self):
        """FK should be fast — <2ms per call (generous for Python)."""
        import time
        skeleton = scale_skeleton(1.78, 80.0)
        q = skeleton.neutral_q()
        q[skeleton.dof_index("L_hip", "rx")] = np.radians(90)
        q[skeleton.dof_index("L_knee", "rx")] = np.radians(90)

        # Warm up
        for _ in range(10):
            forward_kinematics(skeleton, q)

        start = time.perf_counter()
        n_iters = 100
        for _ in range(n_iters):
            forward_kinematics(skeleton, q)
        elapsed = (time.perf_counter() - start) / n_iters * 1000

        assert elapsed < 2.0, f"FK took {elapsed:.2f}ms, should be < 2ms"
