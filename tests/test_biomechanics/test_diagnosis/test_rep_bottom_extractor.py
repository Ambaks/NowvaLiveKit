"""Tests for extract_bottom_q: synthetic trajectories with known bottom frames."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.diagnosis.rep_bottom_extractor import extract_bottom_q


def _make_skeleton():
    return scale_skeleton(1.78, 80.0)


def _parabolic_trajectory(skeleton, n_frames=30, bottom_frame=15):
    """Create a trajectory where hip Y follows a parabola with minimum at bottom_frame."""
    neutral = skeleton.neutral_q()
    trajectory = np.tile(neutral, (n_frames, 1))

    for fi in range(n_frames):
        phase = 1.0 - ((fi - bottom_frame) / (n_frames / 2.0)) ** 2
        phase = max(0.0, min(1.0, phase))
        trajectory[fi, skeleton.dof_index("L_hip", "rx")] = np.radians(100 * phase)
        trajectory[fi, skeleton.dof_index("R_hip", "rx")] = np.radians(100 * phase)
        trajectory[fi, skeleton.dof_index("L_knee", "rx")] = np.radians(120 * phase)
        trajectory[fi, skeleton.dof_index("R_knee", "rx")] = np.radians(120 * phase)
        trajectory[fi, skeleton.dof_index("L_ankle", "rx")] = np.radians(30 * phase)
        trajectory[fi, skeleton.dof_index("R_ankle", "rx")] = np.radians(30 * phase)
        trajectory[fi, 1] = neutral[1] - 0.35 * phase

    return trajectory


class TestExtractBottomQ:
    def test_finds_correct_bottom_parabolic(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=30, bottom_frame=15)

        bottom_idx, q_bottom = extract_bottom_q(trajectory, skeleton)

        assert abs(bottom_idx - 15) <= 1
        assert q_bottom.shape == (skeleton.n_dof,)
        np.testing.assert_array_equal(q_bottom, trajectory[bottom_idx])

    def test_finds_bottom_at_start(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=20, bottom_frame=2)

        bottom_idx, q_bottom = extract_bottom_q(trajectory, skeleton)

        assert bottom_idx <= 4

    def test_finds_bottom_at_end(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=20, bottom_frame=18)

        bottom_idx, q_bottom = extract_bottom_q(trajectory, skeleton)

        assert bottom_idx >= 15

    def test_short_trajectory_no_smoothing(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=3, bottom_frame=1)

        bottom_idx, q_bottom = extract_bottom_q(trajectory, skeleton)

        assert bottom_idx == 1

    def test_single_frame(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=1, bottom_frame=0)

        bottom_idx, q_bottom = extract_bottom_q(trajectory, skeleton)

        assert bottom_idx == 0

    def test_empty_trajectory_raises(self):
        skeleton = _make_skeleton()
        trajectory = np.zeros((0, skeleton.n_dof))

        with pytest.raises(ValueError, match="empty"):
            extract_bottom_q(trajectory, skeleton)

    def test_noisy_trajectory_still_finds_bottom(self):
        skeleton = _make_skeleton()
        trajectory = _parabolic_trajectory(skeleton, n_frames=40, bottom_frame=20)

        rng = np.random.default_rng(42)
        noise = rng.normal(0, 0.01, trajectory.shape)
        trajectory += noise

        bottom_idx, _ = extract_bottom_q(trajectory, skeleton)

        assert abs(bottom_idx - 20) <= 3
