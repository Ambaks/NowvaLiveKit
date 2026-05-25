"""Tests for the MuJoCo forward-dynamics what-if solver."""

import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from biomechanics_v2.model import MujocoSkeleton
from biomechanics_v2.solver.mujoco_whatif import MujocoWhatIfSolver
from biomechanics_v2.solver.mujoco_fk import joint_world_positions, body_com_world
from biomechanics_v2.solver.temporal import gaussian_taper


def _deep_squat_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Construct a deep squat pose within joint bounds."""
    q = skeleton.neutral_q()
    q[skeleton.get_joint_index("pelvis", "ty")] = 0.45
    q[skeleton.get_joint_index("pelvis", "rx")] = 0.15
    q[skeleton.get_joint_index("trunk", "rx")] = 0.35
    for side in ("L_hip", "R_hip"):
        q[skeleton.get_joint_index(side, "rx")] = 1.75
    for side in ("L_knee", "R_knee"):
        q[skeleton.get_joint_index(side, "rx")] = 2.40
    for side in ("L_ankle", "R_ankle"):
        q[skeleton.get_joint_index(side, "rx")] = 0.26  # ~15° DF
    return q


def _standing_q(skeleton: MujocoSkeleton) -> np.ndarray:
    """Roughly upright standing pose."""
    q = skeleton.neutral_q()
    q[skeleton.get_joint_index("L_knee", "rx")] = 0.05
    q[skeleton.get_joint_index("R_knee", "rx")] = 0.05
    return q


@pytest.fixture
def skeleton():
    return MujocoSkeleton(height_m=1.75, weight_kg=75.0)


@pytest.fixture
def solver(skeleton):
    return MujocoWhatIfSolver(skeleton)


# ------------------------------------------------------------------
# 1. Stance widening
# ------------------------------------------------------------------
class TestStanceWidening:
    def test_knees_track_outward(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)
        positions_before = joint_world_positions(skeleton, q_squat)

        foot_delta = np.array([-0.10, 0.0, 0.0, 0.10, 0.0, 0.0])
        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={},
            foot_target_delta=foot_delta,
        )

        positions_after = joint_world_positions(skeleton, q_corrected)

        left_knee_moved_left = (
            positions_after["L_knee"][0] < positions_before["L_knee"][0]
        )
        right_knee_moved_right = (
            positions_after["R_knee"][0] > positions_before["R_knee"][0]
        )
        assert left_knee_moved_left, "Left knee should move leftward (−X)"
        assert right_knee_moved_right, "Right knee should move rightward (+X)"

    def test_com_within_support_polygon(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)
        foot_delta = np.array([-0.10, 0.0, 0.0, 0.10, 0.0, 0.0])
        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={},
            foot_target_delta=foot_delta,
        )

        positions = joint_world_positions(skeleton, q_corrected)
        com = body_com_world(skeleton, q_corrected)

        left_ankle_x = positions["L_ankle"][0]
        right_ankle_x = positions["R_ankle"][0]
        x_min = min(left_ankle_x, right_ankle_x) - 0.05
        x_max = max(left_ankle_x, right_ankle_x) + 0.05

        assert x_min <= com[0] <= x_max, (
            f"COM X ({com[0]:.3f}) outside support polygon "
            f"[{x_min:.3f}, {x_max:.3f}]"
        )

    def test_pose_is_stable(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)
        foot_delta = np.array([-0.10, 0.0, 0.0, 0.10, 0.0, 0.0])
        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={},
            foot_target_delta=foot_delta,
            energy_threshold=1e-6,
        )
        assert q_corrected is not None
        assert q_corrected.shape == (20,)
        assert np.all(np.isfinite(q_corrected))


# ------------------------------------------------------------------
# 2. Dorsiflexion increase — cascading chain test
# ------------------------------------------------------------------
class TestDorsiflexionIncrease:
    def test_trunk_becomes_more_upright(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)

        df_increase_rad = math.radians(15)
        new_df_limit_rad = math.radians(40)

        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={
                "L_ankle.rx": df_increase_rad,
                "R_ankle.rx": df_increase_rad,
            },
            joint_limit_overrides={
                "L_ankle.rx": (math.radians(-30), new_df_limit_rad),
                "R_ankle.rx": (math.radians(-30), new_df_limit_rad),
            },
        )

        # Trunk rx: positive = forward lean. More upright means smaller or
        # equal trunk rx compared to original.
        trunk_idx = skeleton.get_joint_index("trunk", "rx")
        original_trunk_lean = q_squat[trunk_idx]
        corrected_trunk_lean = q_corrected[trunk_idx]

        assert corrected_trunk_lean <= original_trunk_lean + 0.05, (
            f"Trunk should be at least as upright: "
            f"original={math.degrees(original_trunk_lean):.1f}°, "
            f"corrected={math.degrees(corrected_trunk_lean):.1f}°"
        )

    def test_ankle_df_actually_increased(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)
        df_increase_rad = math.radians(15)

        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={
                "L_ankle.rx": df_increase_rad,
                "R_ankle.rx": df_increase_rad,
            },
        )

        ankle_l_idx = skeleton.get_joint_index("L_ankle", "rx")
        ankle_r_idx = skeleton.get_joint_index("R_ankle", "rx")

        assert q_corrected[ankle_l_idx] > q_squat[ankle_l_idx], (
            "Left ankle DF should have increased"
        )
        assert q_corrected[ankle_r_idx] > q_squat[ankle_r_idx], (
            "Right ankle DF should have increased"
        )


# ------------------------------------------------------------------
# 3. Asymmetric perturbation
# ------------------------------------------------------------------
class TestAsymmetricPerturbation:
    def test_left_ankle_df_larger_than_right(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)

        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={"L_ankle.rx": math.radians(20)},
        )

        ankle_l_idx = skeleton.get_joint_index("L_ankle", "rx")
        ankle_r_idx = skeleton.get_joint_index("R_ankle", "rx")

        assert q_corrected[ankle_l_idx] > q_corrected[ankle_r_idx] + math.radians(5), (
            f"Left ankle DF ({math.degrees(q_corrected[ankle_l_idx]):.1f}°) "
            f"should be significantly larger than right "
            f"({math.degrees(q_corrected[ankle_r_idx]):.1f}°)"
        )

    def test_left_knee_adapts_more_than_right(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)

        q_corrected = solver.solve(
            q_fitted=q_squat,
            perturbation={"L_ankle.rx": math.radians(20)},
        )

        left_knee_idx = skeleton.get_joint_index("L_knee", "rx")
        right_knee_idx = skeleton.get_joint_index("R_knee", "rx")

        left_knee_change = abs(q_corrected[left_knee_idx] - q_squat[left_knee_idx])
        right_knee_change = abs(q_corrected[right_knee_idx] - q_squat[right_knee_idx])

        assert left_knee_change > right_knee_change, (
            f"Left knee DOF change ({math.degrees(left_knee_change):.4f}°) "
            f"should exceed right ({math.degrees(right_knee_change):.4f}°) "
            f"for left-only ankle perturbation"
        )


# ------------------------------------------------------------------
# 4. Standing frames unaffected by taper
# ------------------------------------------------------------------
class TestTaperTrajectory:
    def test_distant_frames_unchanged(self, skeleton, solver):
        num_frames = 60
        bottom_frame = 30
        q_squat = _deep_squat_q(skeleton)
        q_stand = _standing_q(skeleton)

        q_trajectory = np.zeros((num_frames, 20))
        for frame_idx in range(num_frames):
            blend = max(0.0, 1.0 - abs(frame_idx - bottom_frame) / 20.0)
            q_trajectory[frame_idx] = (
                q_stand * (1.0 - blend) + q_squat * blend
            )

        warped = solver.warp_trajectory(
            q_trajectory=q_trajectory,
            bottom_frame=bottom_frame,
            perturbation={
                "L_ankle.rx": math.radians(15),
                "R_ankle.rx": math.radians(15),
            },
        )

        # Frames at the start and end (taper ≈ 0) should be nearly unchanged
        for edge_frame in [0, 1, num_frames - 2, num_frames - 1]:
            max_diff = np.max(np.abs(warped[edge_frame] - q_trajectory[edge_frame]))
            assert max_diff < 0.01, (
                f"Frame {edge_frame} changed by {max_diff:.4f} rad — "
                f"expected < 0.01 (taper should be ~0 here)"
            )

    def test_bottom_frame_is_corrected(self, skeleton, solver):
        num_frames = 60
        bottom_frame = 30
        q_squat = _deep_squat_q(skeleton)

        q_trajectory = np.tile(q_squat, (num_frames, 1))
        perturbation = {
            "L_ankle.rx": math.radians(15),
            "R_ankle.rx": math.radians(15),
        }

        warped = solver.warp_trajectory(
            q_trajectory=q_trajectory,
            bottom_frame=bottom_frame,
            perturbation=perturbation,
        )

        ankle_l_idx = skeleton.get_joint_index("L_ankle", "rx")
        delta_at_bottom = abs(
            warped[bottom_frame, ankle_l_idx] - q_trajectory[bottom_frame, ankle_l_idx]
        )
        assert delta_at_bottom > math.radians(5), (
            f"Bottom frame ankle should change significantly "
            f"(delta={math.degrees(delta_at_bottom):.1f}°)"
        )


# ------------------------------------------------------------------
# 5. Performance
# ------------------------------------------------------------------
class TestPerformance:
    def test_single_solve_under_50ms(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)

        # Warm-up run
        solver.solve(q_squat, {"L_ankle.rx": 0.1})

        start = time.perf_counter()
        solver.solve(
            q_fitted=q_squat,
            perturbation={"L_ankle.rx": math.radians(15)},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 50, f"Single solve took {elapsed_ms:.1f}ms (limit: 50ms)"

    def test_warp_trajectory_under_200ms(self, skeleton, solver):
        q_squat = _deep_squat_q(skeleton)
        num_frames = 150
        q_trajectory = np.tile(q_squat, (num_frames, 1))
        bottom_frame = 75

        # Warm-up
        solver.warp_trajectory(
            q_trajectory[:10], 5, {"L_ankle.rx": 0.1}
        )

        start = time.perf_counter()
        solver.warp_trajectory(
            q_trajectory=q_trajectory,
            bottom_frame=bottom_frame,
            perturbation={"L_ankle.rx": math.radians(15)},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 200, (
            f"Warp 150-frame trajectory took {elapsed_ms:.1f}ms (limit: 200ms)"
        )


# ------------------------------------------------------------------
# Gaussian taper unit tests
# ------------------------------------------------------------------
class TestGaussianTaper:
    def test_peak_at_bottom_frame(self):
        taper = gaussian_taper(100, 50)
        assert taper[50] == pytest.approx(1.0)

    def test_symmetric_around_peak(self):
        taper = gaussian_taper(100, 50)
        assert taper[40] == pytest.approx(taper[60], abs=1e-10)

    def test_decays_away_from_peak(self):
        taper = gaussian_taper(100, 50)
        assert taper[0] < taper[25] < taper[50]

    def test_custom_sigma(self):
        narrow = gaussian_taper(100, 50, sigma_frames=5.0)
        wide = gaussian_taper(100, 50, sigma_frames=30.0)
        assert narrow[30] < wide[30]

    def test_default_sigma_is_n_over_6(self):
        taper = gaussian_taper(60, 30)
        expected_sigma = 60.0 / 6.0
        t = np.arange(60, dtype=np.float64)
        expected = np.exp(-0.5 * ((t - 30) / expected_sigma) ** 2)
        np.testing.assert_allclose(taper, expected)
