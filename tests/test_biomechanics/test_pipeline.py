"""
Tests for BiomechanicsPipeline.

Uses a synthetic video (20 frames) by mocking cv2.VideoCapture so no
real camera is needed. Verifies that PipelineFrame has the expected
types and that the pipeline completes without error.
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.config import BiomechanicsConfig
from biomechanics.utils.types import PipelineFrame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fake_capture(num_frames: int = 20):
    """Create a mock cv2.VideoCapture that yields synthetic frames."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.set.return_value = True

    call_count = 0

    def read_side_effect():
        nonlocal call_count
        if call_count >= num_frames:
            return False, None
        call_count += 1
        # 720p synthetic frame with random noise
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        return True, frame

    mock_cap.read.side_effect = read_side_effect
    mock_cap.release.return_value = None
    return mock_cap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBiomechanicsPipeline:

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_pipeline_processes_frames(self, mock_video_capture_cls):
        """Pipeline should process synthetic frames and return PipelineFrames."""
        mock_video_capture_cls.return_value = _make_fake_capture(20)

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)

        frames_processed = 0
        for _ in range(20):
            result = pipeline.process_frame()

            assert isinstance(result, PipelineFrame)
            assert isinstance(result.frame_index, int)
            assert isinstance(result.timestamp, float)
            assert isinstance(result.latency_ms, dict)
            assert "capture" in result.latency_ms

            frames_processed += 1

        pipeline.release()
        assert frames_processed == 20

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_pipeline_frame_types(self, mock_video_capture_cls):
        """PipelineFrame fields should have correct types when populated."""
        mock_video_capture_cls.return_value = _make_fake_capture(5)

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)

        result = pipeline.process_frame()

        # Always present
        assert result.frame_index >= 1
        assert result.timestamp > 0
        assert all(isinstance(v, float) for v in result.latency_ms.values())

        # Faults is always a list (possibly empty)
        assert isinstance(result.faults, list)

        pipeline.release()

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_pipeline_handles_no_capture(self, mock_video_capture_cls):
        """Pipeline should return a valid PipelineFrame even when capture fails."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.set.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cap.release.return_value = None
        mock_video_capture_cls.return_value = mock_cap

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)

        result = pipeline.process_frame()

        assert isinstance(result, PipelineFrame)
        assert result.skeleton_2d is None
        assert result.skeleton_3d is None
        assert result.joint_angles is None
        assert "capture" in result.latency_ms

        pipeline.release()

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_pipeline_latency_keys(self, mock_video_capture_cls):
        """When pose succeeds, latency_ms should include all layer keys."""
        mock_video_capture_cls.return_value = _make_fake_capture(5)

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)

        # Process a few frames — at least one should get pose if mediapipe works,
        # but on CI without a real person, pose may return None. That's fine;
        # we just check that capture key is always present.
        for _ in range(5):
            result = pipeline.process_frame()
            assert "capture" in result.latency_ms
            # If pose succeeded, ik and faults should also be present
            if result.joint_angles is not None:
                assert "pose" in result.latency_ms
                assert "ik" in result.latency_ms
                assert "faults" in result.latency_ms

        pipeline.release()

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_pipeline_release(self, mock_video_capture_cls):
        """release() should not raise."""
        mock_video_capture_cls.return_value = _make_fake_capture(1)

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)
        pipeline.process_frame()
        pipeline.release()  # Should not raise
