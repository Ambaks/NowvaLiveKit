"""Tests for confidence-weighted keypoint blending."""

import numpy as np
import pytest

from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.types import Skeleton3D


def _make_skeleton(positions: np.ndarray, confidences: np.ndarray,
                   timestamp: float = 0.0, frame_index: int = 0) -> Skeleton3D:
    """Helper to create a Skeleton3D from positions and confidences arrays."""
    return Skeleton3D.from_numpy(
        positions, confidences=confidences,
        timestamp=timestamp, frame_index=frame_index,
    )


# Fixed test data: 17 keypoints
FRAME_A = np.zeros((17, 3))  # All zeros
FRAME_B = np.ones((17, 3))   # All ones


class TestConfidenceBlender:

    def test_first_frame_passthrough(self):
        """First call stores positions and returns skeleton unchanged."""
        blender = ConfidenceBlender()
        confidences = np.full(17, 0.5)
        skeleton = _make_skeleton(FRAME_B, confidences)

        result = blender.blend(skeleton)
        result_positions = result.to_numpy()

        assert np.allclose(result_positions, FRAME_B, atol=1e-6)

    def test_high_confidence_passthrough(self):
        """High confidence (0.95) should fully trust detection."""
        blender = ConfidenceBlender()
        high_conf = np.full(17, 0.95)

        # First frame: establish previous positions
        blender.blend(_make_skeleton(FRAME_A, high_conf, timestamp=0.0, frame_index=0))

        # Second frame: high confidence should pass through current positions
        skeleton_b = _make_skeleton(FRAME_B, high_conf, timestamp=0.033, frame_index=1)
        result = blender.blend(skeleton_b)
        result_positions = result.to_numpy()

        # weight = (0.95 - 0.1) / (0.9 - 0.1) = 1.0625 → clipped to 1.0
        # blended = 1.0 * FRAME_B + 0.0 * FRAME_A = FRAME_B
        assert np.allclose(result_positions, FRAME_B, atol=1e-6)

    def test_low_confidence_uses_previous(self):
        """Low confidence (0.05) should fully use previous position."""
        blender = ConfidenceBlender()
        high_conf = np.full(17, 0.95)
        low_conf = np.full(17, 0.05)

        # First frame with high confidence
        blender.blend(_make_skeleton(FRAME_A, high_conf, timestamp=0.0, frame_index=0))

        # Second frame with low confidence — should stay at previous (FRAME_A)
        skeleton_b = _make_skeleton(FRAME_B, low_conf, timestamp=0.033, frame_index=1)
        result = blender.blend(skeleton_b)
        result_positions = result.to_numpy()

        # weight = (0.05 - 0.1) / (0.9 - 0.1) = -0.0625 → clipped to 0.0
        # blended = 0.0 * FRAME_B + 1.0 * FRAME_A = FRAME_A
        assert np.allclose(result_positions, FRAME_A, atol=1e-6)

    def test_mid_confidence_interpolation(self):
        """Confidence 0.5 should produce midpoint between current and previous."""
        blender = ConfidenceBlender()  # min=0.1, max=0.9
        high_conf = np.full(17, 0.95)
        mid_conf = np.full(17, 0.5)

        # First frame
        blender.blend(_make_skeleton(FRAME_A, high_conf, timestamp=0.0, frame_index=0))

        # Second frame with mid confidence
        skeleton_b = _make_skeleton(FRAME_B, mid_conf, timestamp=0.033, frame_index=1)
        result = blender.blend(skeleton_b)
        result_positions = result.to_numpy()

        # weight = (0.5 - 0.1) / (0.9 - 0.1) = 0.5
        # blended = 0.5 * FRAME_B + 0.5 * FRAME_A = 0.5
        expected = 0.5 * FRAME_B + 0.5 * FRAME_A
        assert np.allclose(result_positions, expected, atol=1e-6)

    def test_reset_clears_state(self):
        """After reset, next call acts as first frame (passthrough)."""
        blender = ConfidenceBlender()
        high_conf = np.full(17, 0.95)

        # Blend two frames
        blender.blend(_make_skeleton(FRAME_A, high_conf))
        blender.blend(_make_skeleton(FRAME_B, high_conf))

        # Reset
        blender.reset()

        # Next call should act as first frame — return unchanged
        new_positions = np.full((17, 3), 5.0)
        skeleton = _make_skeleton(new_positions, high_conf, timestamp=1.0, frame_index=10)
        result = blender.blend(skeleton)
        result_positions = result.to_numpy()

        assert np.allclose(result_positions, new_positions, atol=1e-6)
