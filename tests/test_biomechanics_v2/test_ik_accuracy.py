"""Tests for MuJoCo IK solver accuracy, convergence, and performance."""

from __future__ import annotations

import math
import time

import mujoco
import numpy as np
import pytest

from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.mujoco_ik import MujocoIKSolver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def skeleton():
    return MujocoSkeleton(height_m=1.75, weight_kg=75.0)


@pytest.fixture
def tall_skeleton():
    """User's height (188.5 cm)."""
    return MujocoSkeleton(height_m=1.885, weight_kg=85.0)


@pytest.fixture
def solver(skeleton):
    return MujocoIKSolver(skeleton)


@pytest.fixture
def tall_solver(tall_skeleton):
    return MujocoIKSolver(tall_skeleton)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TARGET_BODY_NAMES = [
    "pelvis", "trunk", "L_hip", "R_hip",
    "L_knee", "R_knee", "L_ankle", "R_ankle",
    "head", "L_toe", "R_toe",
]


def _fk_to_landmarks(skeleton: MujocoSkeleton, q_vector: np.ndarray) -> np.ndarray:
    """Run MuJoCo FK on a q-vector and return (11, 4) landmarks with visibility=1."""
    skeleton.set_qpos(q_vector)
    skeleton.forward()
    positions = skeleton.get_body_positions()
    landmarks = np.zeros((11, 4))
    for i, name in enumerate(TARGET_BODY_NAMES):
        landmarks[i, :3] = positions[name]
        landmarks[i, 3] = 1.0
    return landmarks


def _random_q_within_bounds(skeleton: MujocoSkeleton, scale: float = 0.7) -> np.ndarray:
    """Generate a random q-vector within scaled joint limits."""
    bounds = skeleton.get_bounds()
    q_vector = np.zeros(20)
    for i, (low, high) in enumerate(bounds):
        if np.isfinite(low) and np.isfinite(high):
            q_vector[i] = np.random.uniform(low * scale, high * scale)
        elif i == 1:
            q_vector[i] = np.random.uniform(0.5, 1.0)
        else:
            q_vector[i] = np.random.uniform(-0.3, 0.3)
    return q_vector


def _make_deep_squat_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Produce a realistic deep squat q-vector."""
    q_vector = skeleton.neutral_q()
    q_vector[1] = 0.55 * (skeleton.height_m / 1.75)

    hip_flexion = math.radians(100.0)
    knee_flexion = math.radians(140.0)
    ankle_dorsiflexion = math.radians(30.0)
    trunk_flexion = math.radians(25.0)

    q_vector[skeleton.get_joint_index("L_hip", "rx")] = hip_flexion
    q_vector[skeleton.get_joint_index("R_hip", "rx")] = hip_flexion
    q_vector[skeleton.get_joint_index("L_knee", "rx")] = knee_flexion
    q_vector[skeleton.get_joint_index("R_knee", "rx")] = knee_flexion
    q_vector[skeleton.get_joint_index("L_ankle", "rx")] = ankle_dorsiflexion
    q_vector[skeleton.get_joint_index("R_ankle", "rx")] = ankle_dorsiflexion
    q_vector[skeleton.get_joint_index("trunk", "rx")] = trunk_flexion

    return q_vector


def _per_joint_fk_error_mm(
    skeleton: MujocoSkeleton,
    q_solved: np.ndarray,
    target_landmarks: np.ndarray,
) -> dict[str, float]:
    """Compute per-joint FK reconstruction error in mm."""
    skeleton.set_qpos(q_solved)
    skeleton.forward()
    positions = skeleton.get_body_positions()
    errors = {}
    for i, name in enumerate(TARGET_BODY_NAMES):
        errors[name] = float(np.linalg.norm(positions[name] - target_landmarks[i, :3])) * 1000.0
    return errors


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Generate landmarks from known q via FK, run IK, verify q recovery."""

    def test_neutral_pose_round_trip(self, skeleton, solver):
        q_true = skeleton.neutral_q()
        landmarks = _fk_to_landmarks(skeleton, q_true)
        q_solved = solver.fit_frame(landmarks, q_init=None)

        errors = _per_joint_fk_error_mm(skeleton, q_solved, landmarks)
        for name, err_mm in errors.items():
            assert err_mm < 10.0, f"{name}: {err_mm:.1f}mm > 10mm"

    @pytest.mark.parametrize("seed", range(10))
    def test_random_pose_round_trip(self, skeleton, solver, seed):
        np.random.seed(seed)
        q_true = _random_q_within_bounds(skeleton, scale=0.6)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        q_solved = solver.fit_frame(landmarks, q_init=None)

        errors = _per_joint_fk_error_mm(skeleton, q_solved, landmarks)
        for name, err_mm in errors.items():
            assert err_mm < 10.0, f"seed={seed} {name}: {err_mm:.1f}mm > 10mm"

    @pytest.mark.parametrize("seed", range(10))
    def test_random_warm_started_round_trip(self, skeleton, solver, seed):
        """Warm-start from a nearby pose — should converge within 10mm."""
        np.random.seed(seed)
        q_true = _random_q_within_bounds(skeleton, scale=0.6)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        q_nearby = q_true + np.random.normal(0, 0.05, size=20)
        q_solved = solver.fit_frame(landmarks, q_init=q_nearby)

        errors = _per_joint_fk_error_mm(skeleton, q_solved, landmarks)
        for name, err_mm in errors.items():
            assert err_mm < 10.0, f"seed={seed} {name}: {err_mm:.1f}mm > 10mm"

    @pytest.mark.parametrize("seed", range(10))
    def test_angle_recovery(self, skeleton, solver, seed):
        """Verify solved q-vector is close to ground truth (within 0.05 rad ≈ 3°)."""
        np.random.seed(seed)
        q_true = _random_q_within_bounds(skeleton, scale=0.5)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        q_nearby = q_true + np.random.normal(0, 0.02, size=20)
        q_solved = solver.fit_frame(landmarks, q_init=q_nearby)

        # Skip pelvis translation (indices 0-2) since there can be
        # translational degeneracy when rotations compensate
        for dof_idx in range(3, 20):
            diff = abs(q_solved[dof_idx] - q_true[dof_idx])
            assert diff < 0.05, (
                f"seed={seed} DOF[{dof_idx}]: "
                f"solved={q_solved[dof_idx]:.3f} vs true={q_true[dof_idx]:.3f} "
                f"(diff={diff:.3f} > 0.05 rad)"
            )


# ---------------------------------------------------------------------------
# Deep squat test — the V1 bug scenario
# ---------------------------------------------------------------------------

class TestDeepSquat:
    """Verify the IK solves a deep squat correctly (the V1 ankle/trunk bug)."""

    def test_deep_squat_angles_nonzero(self, skeleton, solver):
        q_true = _make_deep_squat_q(skeleton)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        q_solved = solver.fit_frame(landmarks, q_init=None)

        ankle_df_idx = skeleton.get_joint_index("L_ankle", "rx")
        trunk_rx_idx = skeleton.get_joint_index("trunk", "rx")
        hip_rz_idx = skeleton.get_joint_index("L_hip", "rz")

        ankle_df_deg = math.degrees(q_solved[ankle_df_idx])
        trunk_rx_deg = math.degrees(q_solved[trunk_rx_idx])
        hip_rz_deg = math.degrees(q_solved[hip_rz_idx])

        assert ankle_df_deg > 5.0, f"Ankle DF={ankle_df_deg:.1f}° — stuck at zero (V1 bug!)"
        assert trunk_rx_deg > 5.0, f"Trunk flexion={trunk_rx_deg:.1f}° — stuck at zero (V1 bug!)"

        hip_rz_bounds = skeleton.get_bounds()[hip_rz_idx]
        assert hip_rz_bounds[0] < q_solved[hip_rz_idx] < hip_rz_bounds[1], (
            f"L_hip rz={hip_rz_deg:.1f}° is at bounds — over-constrained"
        )

    def test_deep_squat_fk_error(self, skeleton, solver):
        q_true = _make_deep_squat_q(skeleton)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        q_solved = solver.fit_frame(landmarks, q_init=None)

        lower_body = ["pelvis", "L_hip", "R_hip", "L_knee", "R_knee", "L_ankle", "R_ankle"]
        errors = _per_joint_fk_error_mm(skeleton, q_solved, landmarks)
        for name in lower_body:
            assert errors[name] < 20.0, f"{name}: {errors[name]:.1f}mm > 20mm"

    def test_deep_squat_tall_skeleton(self, tall_skeleton, tall_solver):
        """Same test at user's height (188.5 cm)."""
        q_true = _make_deep_squat_q(tall_skeleton)
        landmarks = _fk_to_landmarks(tall_skeleton, q_true)

        q_solved = tall_solver.fit_frame(landmarks, q_init=None)

        errors = _per_joint_fk_error_mm(tall_skeleton, q_solved, landmarks)
        for name, err_mm in errors.items():
            assert err_mm < 20.0, f"{name}: {err_mm:.1f}mm > 20mm"


# ---------------------------------------------------------------------------
# Trajectory test
# ---------------------------------------------------------------------------

class TestTrajectory:
    """30-frame synthetic trajectory: standing → deep squat → standing."""

    @pytest.fixture
    def trajectory_data(self, skeleton):
        """Generate a smooth 30-frame trajectory and its FK landmarks."""
        num_frames = 30
        q_neutral = skeleton.neutral_q()
        q_deep = _make_deep_squat_q(skeleton)

        q_true_trajectory = np.zeros((num_frames, 20))
        landmark_trajectory = np.zeros((num_frames, 11, 4))

        for frame_idx in range(num_frames):
            # Parabolic blend: 0→1→0 peaking at frame 15
            blend = 1.0 - ((frame_idx - 15.0) / 15.0) ** 2
            blend = max(0.0, blend)
            q_frame = q_neutral * (1.0 - blend) + q_deep * blend
            q_true_trajectory[frame_idx] = q_frame
            landmark_trajectory[frame_idx] = _fk_to_landmarks(skeleton, q_frame)

        return q_true_trajectory, landmark_trajectory

    def test_trajectory_fk_error(self, skeleton, solver, trajectory_data):
        q_true_trajectory, landmark_trajectory = trajectory_data
        q_solved_trajectory = solver.fit_trajectory(
            landmark_trajectory, smooth_sigma=0.0,
        )

        for frame_idx in range(len(q_true_trajectory)):
            errors = _per_joint_fk_error_mm(
                skeleton, q_solved_trajectory[frame_idx],
                landmark_trajectory[frame_idx],
            )
            for name, err_mm in errors.items():
                assert err_mm < 20.0, (
                    f"frame={frame_idx} {name}: {err_mm:.1f}mm > 20mm"
                )

    def test_trajectory_smoothness(self, skeleton, solver, trajectory_data):
        """Verify IK doesn't introduce jitter beyond what the ground truth contains."""
        q_true_trajectory, landmark_trajectory = trajectory_data
        q_solved_trajectory = solver.fit_trajectory(
            landmark_trajectory, smooth_sigma=0.0,
        )

        # The solved trajectory's per-frame rotational deltas should not exceed
        # the ground truth deltas by more than a small margin (0.02 rad).
        for frame_idx in range(2, len(q_solved_trajectory)):
            solved_delta = np.abs(q_solved_trajectory[frame_idx] - q_solved_trajectory[frame_idx - 1])
            true_delta = np.abs(q_true_trajectory[frame_idx] - q_true_trajectory[frame_idx - 1])
            excess = np.max(solved_delta[3:] - true_delta[3:])
            assert excess < 0.03, (
                f"frame {frame_idx}: IK introduces {excess:.3f} rad "
                f"extra jitter beyond ground truth"
            )

    def test_trajectory_smoothing_reduces_jitter(self, skeleton, solver, trajectory_data):
        _, landmark_trajectory = trajectory_data
        q_raw = solver.fit_trajectory(landmark_trajectory, smooth_sigma=0.0)
        q_smoothed = solver.fit_trajectory(landmark_trajectory, smooth_sigma=1.5)

        # Smoothed trajectory should have equal or smaller total variation
        raw_tv = np.sum(np.abs(np.diff(q_raw[:, 3:], axis=0)))
        smoothed_tv = np.sum(np.abs(np.diff(q_smoothed[:, 3:], axis=0)))
        assert smoothed_tv <= raw_tv * 1.05  # allow 5% tolerance


# ---------------------------------------------------------------------------
# Visibility / weighting tests
# ---------------------------------------------------------------------------

class TestVisibility:
    """Verify that low-visibility landmarks are ignored."""

    def test_low_vis_landmarks_ignored(self, skeleton, solver):
        q_true = _make_deep_squat_q(skeleton)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        # Zero out visibility for head and toes
        landmarks[8, 3] = 0.0   # head
        landmarks[9, 3] = 0.0   # L_toe
        landmarks[10, 3] = 0.0  # R_toe

        # Corrupt those positions — should not affect IK result
        landmarks[8, :3] = [99.0, 99.0, 99.0]
        landmarks[9, :3] = [-50.0, -50.0, -50.0]
        landmarks[10, :3] = [-50.0, -50.0, -50.0]

        q_solved = solver.fit_frame(landmarks, q_init=None)

        # Lower body joints should still be accurate
        lower_body = ["pelvis", "L_hip", "R_hip", "L_knee", "R_knee", "L_ankle", "R_ankle"]
        good_landmarks = _fk_to_landmarks(skeleton, q_true)
        errors = _per_joint_fk_error_mm(skeleton, q_solved, good_landmarks)
        for name in lower_body:
            assert errors[name] < 25.0, f"{name}: {errors[name]:.1f}mm > 25mm"


# ---------------------------------------------------------------------------
# Performance tests
# ---------------------------------------------------------------------------

class TestPerformance:
    """Verify IK meets latency budget: fit_frame < 5ms, trajectory < 150ms."""

    def test_fit_frame_latency(self, skeleton, solver):
        q_true = _make_deep_squat_q(skeleton)
        landmarks = _fk_to_landmarks(skeleton, q_true)

        # Warm up
        solver.fit_frame(landmarks)

        elapsed_times = []
        for _ in range(20):
            start = time.perf_counter()
            solver.fit_frame(landmarks, q_init=q_true)
            elapsed_times.append((time.perf_counter() - start) * 1000)

        median_ms = float(np.median(elapsed_times))
        assert median_ms < 5.0, f"fit_frame median={median_ms:.2f}ms > 5ms"

    def test_fit_trajectory_latency(self, skeleton, solver):
        num_frames = 30
        q_neutral = skeleton.neutral_q()
        q_deep = _make_deep_squat_q(skeleton)

        landmark_trajectory = np.zeros((num_frames, 11, 4))
        for frame_idx in range(num_frames):
            blend = 1.0 - ((frame_idx - 15.0) / 15.0) ** 2
            blend = max(0.0, blend)
            q_frame = q_neutral * (1.0 - blend) + q_deep * blend
            landmark_trajectory[frame_idx] = _fk_to_landmarks(skeleton, q_frame)

        # Warm up
        solver.fit_trajectory(landmark_trajectory)

        start = time.perf_counter()
        solver.fit_trajectory(landmark_trajectory)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 150.0, f"fit_trajectory(30 frames)={elapsed_ms:.1f}ms > 150ms"
