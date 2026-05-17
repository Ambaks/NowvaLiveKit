"""Tests for the IK solver: Jacobian correctness, single-frame and trajectory recovery."""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.optimizer.ik import (
    fit_frame,
    fit_trajectory,
    _build_descendants,
    _fk_jac,
)

from .synth_fixtures import generate_landmarks_from_q


# DOF indices observable from joint positions (non-leaf joints + root translations)
# pelvis(0-5), L_hip(8-10), R_hip(11-13), L_knee(14), R_knee(15)
_OBSERVABLE = [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15]
_OBSERVABLE_TRANS = [0, 1, 2]
_OBSERVABLE_ROT = [3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15]


def _make_squat_q(skeleton: SkeletonModel, phase: float = 0.5) -> np.ndarray:
    """Half-depth squat pose for testing."""
    q = skeleton.neutral_q()
    hip_flex = np.radians(50.0 * phase)
    for side in ("L", "R"):
        q[skeleton.dof_index(f"{side}_hip", "rx")] = hip_flex
    knee_flex = np.radians(60.0 * phase)
    for side in ("L", "R"):
        q[skeleton.dof_index(f"{side}_knee", "rx")] = knee_flex
    dorsi = np.radians(15.0 * phase)
    for side in ("L", "R"):
        q[skeleton.dof_index(f"{side}_ankle", "rx")] = dorsi
    trunk_flex = np.radians(20.0 * phase)
    q[skeleton.dof_index("trunk", "rx")] = trunk_flex
    q[1] -= 0.15 * phase
    return q


# ── Jacobian correctness ──


class TestJacobian:
    @pytest.fixture
    def skeleton(self):
        return scale_skeleton(1.78, 80.0)

    def test_jacobian_matches_numerical_neutral(self, skeleton):
        q = skeleton.neutral_q()
        self._check_jacobian(skeleton, q)

    def test_jacobian_matches_numerical_squat(self, skeleton):
        q = _make_squat_q(skeleton, phase=0.8)
        self._check_jacobian(skeleton, q)

    def test_jacobian_matches_numerical_asymmetric(self, skeleton):
        q = skeleton.neutral_q()
        q[skeleton.dof_index("L_hip", "rx")] = np.radians(80)
        q[skeleton.dof_index("R_hip", "rx")] = np.radians(30)
        q[skeleton.dof_index("L_knee", "rx")] = np.radians(100)
        q[skeleton.dof_index("pelvis", "ry")] = np.radians(15)
        self._check_jacobian(skeleton, q)

    @staticmethod
    def _check_jacobian(skeleton, q, eps=1e-6):
        desc = _build_descendants(skeleton)
        pos, J = _fk_jac(skeleton, q, desc)
        J_num = np.zeros_like(J)
        for i in range(skeleton.n_dof):
            qp = q.copy()
            qp[i] += eps
            pp, _ = _fk_jac(skeleton, qp, desc)
            qm = q.copy()
            qm[i] -= eps
            pm, _ = _fk_jac(skeleton, qm, desc)
            J_num[:, i] = (pp - pm).ravel() / (2 * eps)
        np.testing.assert_allclose(J, J_num, atol=1e-4)


# ── Single-frame IK ──


class TestFitFrame:
    @pytest.fixture
    def skeleton(self):
        return scale_skeleton(1.78, 80.0)

    def test_recover_squat_exact(self, skeleton):
        """Zero-noise: observable DOFs recovered to high precision."""
        q_true = _make_squat_q(skeleton, phase=0.7)
        lm = generate_landmarks_from_q(skeleton, q_true[np.newaxis], noise_std=0.0)[0]

        q_fit = fit_frame(skeleton, lm, q_init=skeleton.neutral_q())

        for i in _OBSERVABLE_TRANS:
            assert abs(q_fit[i] - q_true[i]) < 1e-3, (
                f"trans DOF {i}: fit={q_fit[i]:.5f} true={q_true[i]:.5f}"
            )
        for i in _OBSERVABLE_ROT:
            assert abs(q_fit[i] - q_true[i]) < 1e-3, (
                f"rot DOF {i}: fit={q_fit[i]:.5f} true={q_true[i]:.5f}"
            )

    def test_recover_squat_noisy(self, skeleton):
        """3 mm noise: observable DOFs within 2 deg / 1 cm."""
        np.random.seed(42)
        q_true = _make_squat_q(skeleton, phase=0.7)
        lm = generate_landmarks_from_q(skeleton, q_true[np.newaxis], noise_std=0.003)[0]

        q_fit = fit_frame(skeleton, lm, q_init=skeleton.neutral_q())

        for i in _OBSERVABLE_TRANS:
            assert abs(q_fit[i] - q_true[i]) < 0.01, (
                f"trans DOF {i}: err={abs(q_fit[i] - q_true[i]):.4f} m"
            )
        for i in _OBSERVABLE_ROT:
            assert abs(q_fit[i] - q_true[i]) < np.radians(2.0), (
                f"rot DOF {i}: err={np.degrees(abs(q_fit[i] - q_true[i])):.2f} deg"
            )

    def test_depth_relative_mode(self, skeleton):
        """IK with z scaled by unknown factor still recovers pose."""
        q_true = _make_squat_q(skeleton, phase=0.6)
        lm = generate_landmarks_from_q(skeleton, q_true[np.newaxis], noise_std=0.0)[0]
        lm[:, 2] *= 2.5  # arbitrary depth scale

        q_fit = fit_frame(
            skeleton, lm, q_init=skeleton.neutral_q(), depth_mode="relative"
        )

        for i in _OBSERVABLE_TRANS:
            assert abs(q_fit[i] - q_true[i]) < 0.02, (
                f"trans DOF {i}: err={abs(q_fit[i] - q_true[i]):.4f} m"
            )
        for i in _OBSERVABLE_ROT:
            assert abs(q_fit[i] - q_true[i]) < np.radians(5.0), (
                f"rot DOF {i}: err={np.degrees(abs(q_fit[i] - q_true[i])):.2f} deg"
            )

    def test_partial_visibility(self, skeleton):
        """IK with some landmarks invisible still converges."""
        q_true = _make_squat_q(skeleton, phase=0.5)
        lm = generate_landmarks_from_q(skeleton, q_true[np.newaxis], noise_std=0.0)[0]
        # Hide trunk and right ankle
        lm[skeleton.joint_index("trunk"), 3] = 0.0
        lm[skeleton.joint_index("R_ankle"), 3] = 0.0

        q_fit = fit_frame(skeleton, lm, q_init=skeleton.neutral_q())

        for i in _OBSERVABLE_TRANS:
            assert abs(q_fit[i] - q_true[i]) < 0.02

    def test_warm_start_improves_accuracy(self, skeleton):
        """Starting closer to the solution gives a better fit."""
        q_true = _make_squat_q(skeleton, phase=0.8)
        lm = generate_landmarks_from_q(skeleton, q_true[np.newaxis], noise_std=0.0)[0]

        q_cold = fit_frame(skeleton, lm, q_init=skeleton.neutral_q(), max_iter=10)
        q_warm = fit_frame(skeleton, lm, q_init=q_true * 0.95, max_iter=10)

        err_cold = np.linalg.norm(q_cold[_OBSERVABLE] - q_true[_OBSERVABLE])
        err_warm = np.linalg.norm(q_warm[_OBSERVABLE] - q_true[_OBSERVABLE])
        assert err_warm <= err_cold

    def test_metric_fit_uses_knee_triangle_when_absolute_positions_conflict(self):
        """A visible deep knee triangle should not collapse to a straight knee."""
        skeleton = scale_skeleton(1.885, 80.0)
        lm = np.array([
            [-0.003928969292991038, -0.6073552130181409, -0.045442498401348196, 1.0],
            [-0.022710349078998465, -1.0040068440164163, 0.00936508671856402, 1.0],
            [-0.04346843644392056, -0.6732857142857144, 0.0, 1.0],
            [0.04346843644392056, -0.6732857142857144, 0.0, 1.0],
            [-0.04346843644392056, -0.7712180307271386, -0.36762788701930343, 1.0],
            [0.04346843644392056, -0.7712180307271386, -0.36762788701930343, 1.0],
            [-0.04346843644392056, -1.1840427607512805, -0.13834036135815522, 1.0],
            [0.04346843644392056, -1.1840427607512805, -0.13834036135815522, 1.0],
        ])
        q_init = skeleton.neutral_q()
        q_init[1] = lm[0, 1]
        for side in ("L", "R"):
            q_init[skeleton.dof_index(f"{side}_hip", "rx")] = np.radians(40.0)
            q_init[skeleton.dof_index(f"{side}_knee", "rx")] = np.radians(55.0)

        q_fit = fit_frame(
            skeleton,
            lm,
            q_init=q_init,
            weights=np.array([0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
            max_iter=100,
        )

        knee_l = np.degrees(q_fit[skeleton.dof_index("L_knee", "rx")])
        knee_r = np.degrees(q_fit[skeleton.dof_index("R_knee", "rx")])
        assert knee_l > 60.0
        assert knee_r > 60.0


# ── Trajectory IK ──


class TestFitTrajectory:
    @pytest.fixture
    def skeleton(self):
        return scale_skeleton(1.78, 80.0)

    def test_recover_trajectory_no_smoothing(self, skeleton):
        """Warm-started trajectory recovery without smoothing.

        Only check mid-squat frames (5-15) where hip ab/adduction has
        sufficient observability — near standing, the thigh aligns with
        the ry rotation axis and the Jacobian is near-degenerate.
        """
        from .synth_fixtures import _make_clean_squat_q

        np.random.seed(123)
        n_frames = 20
        q_true = _make_clean_squat_q(skeleton, n_frames=n_frames)
        lm = generate_landmarks_from_q(skeleton, q_true, noise_std=0.002)

        q_fit = fit_trajectory(skeleton, lm, smooth_sigma=0)

        for t in range(5, 16):
            for i in _OBSERVABLE_TRANS:
                assert abs(q_fit[t, i] - q_true[t, i]) < 0.01, (
                    f"frame {t} trans DOF {i}"
                )
            for i in _OBSERVABLE_ROT:
                assert abs(q_fit[t, i] - q_true[t, i]) < np.radians(2.0), (
                    f"frame {t} rot DOF {i}: "
                    f"err={np.degrees(abs(q_fit[t, i] - q_true[t, i])):.2f} deg"
                )

    def test_smoothing_reduces_jitter(self, skeleton):
        """Gaussian smoothing should lower frame-to-frame velocity."""
        from .synth_fixtures import _make_clean_squat_q

        np.random.seed(456)
        n_frames = 30
        q_true = _make_clean_squat_q(skeleton, n_frames=n_frames)
        lm = generate_landmarks_from_q(skeleton, q_true, noise_std=0.005)

        q_raw = fit_trajectory(skeleton, lm, smooth_sigma=0)
        q_smooth = fit_trajectory(skeleton, lm, smooth_sigma=2.0)

        vel_raw = np.diff(q_raw[:, _OBSERVABLE_ROT], axis=0)
        vel_smooth = np.diff(q_smooth[:, _OBSERVABLE_ROT], axis=0)

        assert np.std(vel_smooth) < np.std(vel_raw)


# ── Performance ──


class TestPerformance:
    def test_fit_frame_speed_warm(self):
        """Warm-started fit_frame should take <30 ms."""
        skeleton = scale_skeleton(1.78, 80.0)
        q = _make_squat_q(skeleton, phase=0.5)
        lm = generate_landmarks_from_q(skeleton, q[np.newaxis], noise_std=0.0)[0]
        q_near = q * 0.98  # close init

        # warm up JIT / caches
        for _ in range(3):
            fit_frame(skeleton, lm, q_init=q_near, max_iter=30)

        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            fit_frame(skeleton, lm, q_init=q_near, max_iter=30)
            times.append(time.perf_counter() - t0)

        median_ms = np.median(times) * 1000
        assert median_ms < 30.0, f"median fit_frame took {median_ms:.1f} ms"
