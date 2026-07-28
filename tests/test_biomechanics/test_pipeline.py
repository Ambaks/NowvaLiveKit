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
from biomechanics.utils.types import CocoKeypoints as CK, PipelineFrame, Skeleton3D


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _standing_points() -> np.ndarray:
    """Standing skeleton that passes both standing and readiness gates."""
    points = np.zeros((17, 3))
    points[CK.NOSE] = [0.0, 1.70, 0.0]
    points[CK.LEFT_EYE] = [0.03, 1.72, -0.02]
    points[CK.RIGHT_EYE] = [-0.03, 1.72, -0.02]
    points[CK.LEFT_EAR] = [0.07, 1.70, 0.0]
    points[CK.RIGHT_EAR] = [-0.07, 1.70, 0.0]
    points[CK.LEFT_SHOULDER] = [0.20, 1.50, 0.0]
    points[CK.RIGHT_SHOULDER] = [-0.20, 1.50, 0.0]
    points[CK.LEFT_ELBOW] = [0.25, 1.25, 0.0]
    points[CK.RIGHT_ELBOW] = [-0.25, 1.25, 0.0]
    points[CK.LEFT_WRIST] = [0.25, 1.00, 0.0]
    points[CK.RIGHT_WRIST] = [-0.25, 1.00, 0.0]
    points[CK.LEFT_HIP] = [0.10, 1.00, 0.0]
    points[CK.RIGHT_HIP] = [-0.10, 1.00, 0.0]
    points[CK.LEFT_KNEE] = [0.10, 0.55, 0.0]
    points[CK.RIGHT_KNEE] = [-0.10, 0.55, 0.0]
    points[CK.LEFT_ANKLE] = [0.10, 0.10, 0.0]
    points[CK.RIGHT_ANKLE] = [-0.10, 0.10, 0.0]
    return points


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


class TestPresenceOnlyMode:
    """Rest periods must not advance gates or collect analysis data."""

    def _pipeline_with_standing_pose(self, mock_video_capture_cls):
        """Pipeline with mocked capture and a pose estimator that always
        returns a valid standing skeleton."""
        mock_video_capture_cls.return_value = _make_fake_capture(60)

        from biomechanics.pipeline import BiomechanicsPipeline

        config = BiomechanicsConfig()
        pipeline = BiomechanicsPipeline(config)

        points = _standing_points()

        def fake_estimate_both(frame):
            skeleton_3d = Skeleton3D.from_numpy(
                points, confidences=np.ones(17),
                timestamp=time.time(), frame_index=0,
            )
            return None, skeleton_3d

        pipeline._pose_estimator = MagicMock()
        pipeline._pose_estimator.estimate_both.side_effect = fake_estimate_both

        # Seed a frame directly so the first process_frame() call does not
        # race the background capture thread.
        with pipeline._frame_lock:
            pipeline._latest_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        return pipeline

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_presence_only_skips_gate_and_analysis(self, mock_video_capture_cls):
        """Standing frames during rest must not latch the readiness gate,
        produce joint angles, count reps, or emit faults."""
        pipeline = self._pipeline_with_standing_pose(mock_video_capture_cls)
        pipeline.presence_only = True

        for _ in range(10):
            result = pipeline.process_frame()

        # Presence is still tracked
        assert result.skeleton_3d is not None

        # But nothing downstream runs
        assert result.joint_angles is None
        assert result.rep_data is None
        assert result.faults == []
        assert not pipeline.is_ready
        assert pipeline._readiness_gate.progress[0] == 0

        pipeline.release()

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_gate_advances_when_presence_only_cleared(self, mock_video_capture_cls):
        """Identical standing frames DO advance the readiness gate in
        normal mode — the contrast case for presence-only."""
        pipeline = self._pipeline_with_standing_pose(mock_video_capture_cls)

        for _ in range(4):
            result = pipeline.process_frame()

        assert pipeline._readiness_gate.progress[0] == 4
        assert result.joint_angles is None  # gate not yet latched

        pipeline.release()


class TestLoggedRepCount:
    """The displayed count must be the count that actually gets logged."""

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_rep_count_follows_hip_counter_without_bilstm(self, mock_video_capture_cls):
        mock_video_capture_cls.return_value = _make_fake_capture(1)

        from biomechanics.pipeline import BiomechanicsPipeline

        pipeline = BiomechanicsPipeline(BiomechanicsConfig())
        assert pipeline._bilstm is None

        pipeline._rep_counter.rep_count = 7
        assert pipeline.rep_count == 7

        pipeline.release()

    @patch("biomechanics.pipeline.cv2.VideoCapture")
    def test_rep_count_follows_bilstm_when_enabled(self, mock_video_capture_cls):
        """The hip counter accepts shallow reps the BiLSTM rejects — the
        HUD has to follow the counter that feeds the session tracker."""
        mock_video_capture_cls.return_value = _make_fake_capture(1)

        from biomechanics.pipeline import BiomechanicsPipeline

        pipeline = BiomechanicsPipeline(BiomechanicsConfig())
        pipeline._bilstm = MagicMock()
        pipeline._bilstm.rep_count = 6

        pipeline._rep_counter.rep_count = 11
        assert pipeline.rep_count == 6

        pipeline.release()
