"""Tests for velocity clamping of 3D skeleton keypoints."""

import numpy as np
import pytest

from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.types import Skeleton3D


def _make_skeleton(positions: np.ndarray, confidences: np.ndarray = None,
                   timestamp: float = 0.0, frame_index: int = 0) -> Skeleton3D:
    """Helper to create a Skeleton3D from a positions array."""
    if confidences is None:
        confidences = np.ones(len(positions))
    return Skeleton3D.from_numpy(
        positions, confidences=confidences,
        timestamp=timestamp, frame_index=frame_index,
    )


DEFAULT_MAX_VEL = 2.5  # m/s
DEFAULT_DT = 0.033     # seconds between test frames


class TestVelocityClamp:

    def test_first_frame_passthrough(self):
        """First call stores positions and returns skeleton unchanged."""
        clamp = VelocityClamp()
        positions = np.random.rand(17, 3)
        skeleton = _make_skeleton(positions)

        result = clamp.clamp(skeleton)
        assert np.allclose(result.to_numpy(), positions, atol=1e-10)

    def test_within_threshold_unchanged(self):
        """Keypoints moving less than max_displacement pass through unchanged."""
        clamp = VelocityClamp()

        frame_a = np.zeros((17, 3))
        frame_b = np.full((17, 3), 0.01)  # 0.01m displacement ≈ 0.017m 3D distance, well within 0.083m

        clamp.clamp(_make_skeleton(frame_a))
        result = clamp.clamp(_make_skeleton(frame_b, timestamp=0.033, frame_index=1))

        assert np.allclose(result.to_numpy(), frame_b, atol=1e-10)

    def test_teleport_clamped(self):
        """A keypoint that teleports 0.5m should be clamped to max_displacement."""
        clamp = VelocityClamp()

        frame_a = np.zeros((17, 3))
        frame_b = np.zeros((17, 3))
        # Teleport keypoint 5 (left shoulder) by 0.5m in the X direction
        frame_b[5] = [0.5, 0.0, 0.0]

        clamp.clamp(_make_skeleton(frame_a))
        result = clamp.clamp(_make_skeleton(frame_b, timestamp=0.033, frame_index=1))

        result_positions = result.to_numpy()

        # Keypoint 5 should be clamped to max_velocity * dt
        expected_disp = DEFAULT_MAX_VEL * DEFAULT_DT
        clamped_distance = np.linalg.norm(result_positions[5] - frame_a[5])
        assert abs(clamped_distance - expected_disp) < 1e-6

        # Other keypoints should be unchanged (they didn't move)
        for i in range(17):
            if i != 5:
                assert np.allclose(result_positions[i], frame_b[i], atol=1e-10)

    def test_direction_preserved(self):
        """After clamping, the direction from prev to clamped matches prev to detected."""
        clamp = VelocityClamp()

        frame_a = np.zeros((17, 3))
        frame_b = np.zeros((17, 3))
        # Teleport keypoint 13 (left knee) diagonally
        frame_b[13] = [0.3, 0.4, 0.0]  # distance = 0.5m, well over threshold

        clamp.clamp(_make_skeleton(frame_a))
        result = clamp.clamp(_make_skeleton(frame_b, timestamp=0.033, frame_index=1))

        result_positions = result.to_numpy()

        # Compute direction vectors
        detected_dir = frame_b[13] - frame_a[13]
        detected_dir_unit = detected_dir / np.linalg.norm(detected_dir)

        clamped_dir = result_positions[13] - frame_a[13]
        clamped_dir_unit = clamped_dir / np.linalg.norm(clamped_dir)

        assert np.allclose(detected_dir_unit, clamped_dir_unit, atol=1e-6)

    def test_reset_clears_state(self):
        """After reset, next call acts as first frame (passthrough)."""
        clamp = VelocityClamp()

        frame_a = np.zeros((17, 3))
        frame_b = np.ones((17, 3))

        clamp.clamp(_make_skeleton(frame_a))
        clamp.clamp(_make_skeleton(frame_b))

        clamp.reset()

        # After reset, next frame should pass through unchanged
        frame_c = np.full((17, 3), 99.0)
        result = clamp.clamp(_make_skeleton(frame_c, timestamp=1.0, frame_index=10))
        assert np.allclose(result.to_numpy(), frame_c, atol=1e-10)

    def test_multiple_frames_accumulate(self):
        """A teleporting joint gradually approaches target over multiple frames."""
        clamp = VelocityClamp()

        origin = np.zeros((17, 3))
        # Target: keypoint 9 (left wrist) at 0.5m in X direction
        target = np.zeros((17, 3))
        target[9] = [0.5, 0.0, 0.0]

        clamp.clamp(_make_skeleton(origin))

        # Feed the same target position for 3 frames
        prev_pos = origin[9].copy()
        for frame_idx in range(1, 4):
            result = clamp.clamp(_make_skeleton(target, timestamp=frame_idx * 0.033, frame_index=frame_idx))
            result_pos = result.to_numpy()[9]

            distance_from_prev = np.linalg.norm(result_pos - prev_pos)

            # Each frame should advance by at most max_velocity * dt
            expected_disp = DEFAULT_MAX_VEL * DEFAULT_DT
            assert distance_from_prev <= expected_disp + 1e-6

            # Each frame should be closer to the target than the previous
            distance_to_target = np.linalg.norm(result_pos - target[9])
            prev_distance_to_target = np.linalg.norm(prev_pos - target[9])
            assert distance_to_target < prev_distance_to_target

            prev_pos = result_pos.copy()
