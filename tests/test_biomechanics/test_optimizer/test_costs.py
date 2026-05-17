"""Tests for the 5 soft cost terms: gradient correctness and monotonicity."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.optimizer.costs import (
    cost_pose_deviation,
    cost_torque_proxy,
    cost_load_over_midfoot,
    cost_knee_tracking,
    cost_balance_margin,
    combined_cost_and_grad,
    _support_bounds,
)
from biomechanics.optimizer.ik import _fk_jac, _build_descendants


# ── helpers ──────────────────────────────────────────────────────────────


def _make_skeleton() -> SkeletonModel:
    return scale_skeleton(1.78, 80.0)


def _squat_q(skeleton: SkeletonModel, phase: float = 0.7) -> np.ndarray:
    q = skeleton.neutral_q()
    q[skeleton.dof_index("L_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("R_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("L_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("R_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("L_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("R_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("trunk", "rx")] = np.radians(40 * phase)
    q[1] -= 0.35 * phase
    return q


def _numerical_gradient(fn, q, eps=1e-6):
    _, g_analytic = fn(q)
    g_num = np.zeros_like(g_analytic)
    for i in range(len(q)):
        qp = q.copy(); qp[i] += eps
        qm = q.copy(); qm[i] -= eps
        cp, _ = fn(qp)
        cm, _ = fn(qm)
        g_num[i] = (cp - cm) / (2 * eps)
    return g_analytic, g_num


# ── Pose deviation ───────────────────────────────────────────────────────


class TestPoseDeviation:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_zero_at_reference(self, skeleton):
        q = _squat_q(skeleton)
        c, g = cost_pose_deviation(skeleton, q, q.copy())
        assert c == pytest.approx(0.0)
        np.testing.assert_allclose(g, 0.0, atol=1e-12)

    def test_positive_away_from_reference(self, skeleton):
        q = _squat_q(skeleton)
        q_ref = skeleton.neutral_q()
        c, _ = cost_pose_deviation(skeleton, q, q_ref)
        assert c > 0.0

    def test_gradient_matches_numerical(self, skeleton):
        q = _squat_q(skeleton)
        q_ref = skeleton.neutral_q()
        fn = lambda x: cost_pose_deviation(skeleton, x, q_ref)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-5)

    def test_dof_weights(self, skeleton):
        q = _squat_q(skeleton)
        q_ref = skeleton.neutral_q()
        w = np.zeros(skeleton.n_dof)
        w[0] = 10.0  # only penalise pelvis tx
        c, g = cost_pose_deviation(skeleton, q, q_ref, dof_weights=w)
        # Only DOF 0 should contribute
        assert g[1] == pytest.approx(0.0)


# ── Torque proxy ─────────────────────────────────────────────────────────


class TestTorqueProxy:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_non_negative(self, skeleton):
        c, _ = cost_torque_proxy(skeleton, _squat_q(skeleton))
        assert c >= 0.0

    def test_gradient_matches_numerical(self, skeleton):
        q = _squat_q(skeleton)
        fn = lambda x: cost_torque_proxy(skeleton, x)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-4)

    def test_gradient_neutral(self, skeleton):
        q = skeleton.neutral_q()
        fn = lambda x: cost_torque_proxy(skeleton, x)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-4)


# ── Load over midfoot ────────────────────────────────────────────────────


class TestLoadOverMidfoot:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_small_at_neutral(self, skeleton):
        """In T-pose, trunk is roughly over ankles → low cost."""
        c, _ = cost_load_over_midfoot(skeleton, skeleton.neutral_q())
        assert c < 0.01

    def test_increases_with_pelvis_tilt(self, skeleton):
        """Pelvis forward tilt shifts trunk position away from midfoot."""
        q_base = _squat_q(skeleton, phase=0.5)
        q_tilt = q_base.copy()
        q_tilt[skeleton.dof_index("pelvis", "rx")] += np.radians(15)
        c_base, _ = cost_load_over_midfoot(skeleton, q_base)
        c_tilt, _ = cost_load_over_midfoot(skeleton, q_tilt)
        assert c_tilt != c_base

    def test_gradient_matches_numerical(self, skeleton):
        q = _squat_q(skeleton, phase=0.5)
        fn = lambda x: cost_load_over_midfoot(skeleton, x)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-4)


# ── Knee tracking ────────────────────────────────────────────────────────


class TestKneeTracking:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_small_when_symmetric(self, skeleton):
        """Symmetric squat → knees track roughly over ankles."""
        q = _squat_q(skeleton)
        c, _ = cost_knee_tracking(skeleton, q)
        assert c < 0.01

    def test_increases_with_valgus(self, skeleton):
        """Adding hip internal rotation drives knees inward → higher cost."""
        q_good = _squat_q(skeleton)
        q_bad = q_good.copy()
        q_bad[skeleton.dof_index("L_hip", "rz")] = np.radians(-15)
        q_bad[skeleton.dof_index("R_hip", "rz")] = np.radians(15)
        c_good, _ = cost_knee_tracking(skeleton, q_good)
        c_bad, _ = cost_knee_tracking(skeleton, q_bad)
        assert c_bad > c_good

    def test_gradient_matches_numerical(self, skeleton):
        q = _squat_q(skeleton)
        q[skeleton.dof_index("L_hip", "rz")] = np.radians(-10)
        fn = lambda x: cost_knee_tracking(skeleton, x)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-4)


# ── Balance margin ───────────────────────────────────────────────────────


class TestBalanceMargin:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_zero_when_well_inside(self, skeleton):
        """Neutral pose → COM comfortably inside polygon → zero cost."""
        q = skeleton.neutral_q()
        c, _ = cost_balance_margin(skeleton, q, margin=0.02)
        assert c == pytest.approx(0.0, abs=1e-8)

    def test_positive_when_near_edge(self, skeleton):
        """Use narrow explicit bounds so COM falls near an edge."""
        q = skeleton.neutral_q()
        desc = _build_descendants(skeleton)
        pos, _ = _fk_jac(skeleton, q, desc)
        from biomechanics.optimizer.costs import _com_from_pos
        com = _com_from_pos(skeleton, pos)
        tight = (com[0] - 0.04, com[0] + 0.04, com[2] - 0.04, com[2] + 0.04)
        c, _ = cost_balance_margin(
            skeleton, q, margin=0.05, support_bounds_xz=tight,
        )
        assert c > 0.0

    def test_gradient_matches_numerical(self, skeleton):
        q = skeleton.neutral_q()
        q[2] = 0.15  # push COM toward front edge
        fn = lambda x: cost_balance_margin(skeleton, x, margin=0.10)
        ga, gn = _numerical_gradient(fn, q)
        np.testing.assert_allclose(ga, gn, atol=1e-4)

    def test_fixed_support_bounds(self, skeleton):
        """Passing explicit bounds gives same result as auto-computed."""
        q = skeleton.neutral_q()
        q[2] = 0.15
        c1, g1 = cost_balance_margin(skeleton, q, margin=0.10)
        desc = _build_descendants(skeleton)
        pos, _ = _fk_jac(skeleton, q, desc)
        bnds = _support_bounds(skeleton, pos)
        c2, g2 = cost_balance_margin(
            skeleton, q, margin=0.10, support_bounds_xz=bnds,
        )
        assert c1 == pytest.approx(c2)
        np.testing.assert_allclose(g1, g2, atol=1e-12)


# ── Combined evaluator ──────────────────────────────────────────────────


class TestCombinedCost:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_matches_sum_of_parts(self, skeleton):
        """Combined evaluator should equal the sum of individual costs."""
        q = _squat_q(skeleton, phase=0.6)
        q_ref = skeleton.neutral_q()
        desc = _build_descendants(skeleton)
        pos, _ = _fk_jac(skeleton, q, desc)
        sup = _support_bounds(skeleton, pos)
        weights = {
            "pose_deviation": 1.0,
            "torque_proxy": 0.5,
            "load_over_midfoot": 2.0,
            "knee_tracking": 1.0,
            "balance_margin": 0.5,
        }

        tc, tg = combined_cost_and_grad(
            skeleton, q, q_ref, weights, sup, desc,
        )

        c1, g1 = cost_pose_deviation(skeleton, q, q_ref, 1.0)
        c2, g2 = cost_torque_proxy(skeleton, q, 0.5)
        c3, g3 = cost_load_over_midfoot(skeleton, q, 2.0)
        c4, g4 = cost_knee_tracking(skeleton, q, 1.0)
        c5, g5 = cost_balance_margin(
            skeleton, q, 0.5, support_bounds_xz=sup,
        )

        assert tc == pytest.approx(c1 + c2 + c3 + c4 + c5, rel=1e-10)
        np.testing.assert_allclose(tg, g1 + g2 + g3 + g4 + g5, atol=1e-10)
