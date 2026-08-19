"""
Tests for RTMPose batched estimation.

Uses a fake ONNX session so no model download is required. The fake emits
SimCC logits whose argmax position depends on the batch row, letting tests
verify per-frame decoding, batch padding, and result alignment.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.pose.rtmpose import (
    ONNXRUNTIME_AVAILABLE,
    NUM_HALPE26_KEYPOINTS,
    RTMPoseEstimator,
)

COORD_TOL = 1e-6

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
SCALE_X = FRAME_WIDTH / RTMPoseEstimator.INPUT_WIDTH
SCALE_Y = FRAME_HEIGHT / RTMPoseEstimator.INPUT_HEIGHT

# Per-row SimCC peak positions: row i peaks at index (_PEAK + i * _ROW_STRIDE),
# so each camera view decodes to distinct coordinates.
_X_PEAK = 20
_Y_PEAK = 30
_ROW_STRIDE = 2
_SIMCC_SPLIT_RATIO = 2.0


class _FakeSession:
    def __init__(self, dead_rows=frozenset()):
        self.received_shapes = []
        self._dead_rows = dead_rows

    def run(self, output_names, feed):
        batch = next(iter(feed.values()))
        self.received_shapes.append(batch.shape)
        n = batch.shape[0]
        x_logits = np.zeros((n, NUM_HALPE26_KEYPOINTS, 384), dtype=np.float32)
        y_logits = np.zeros((n, NUM_HALPE26_KEYPOINTS, 512), dtype=np.float32)
        for row in range(n):
            if row in self._dead_rows:
                x_logits[row] -= 10.0
                y_logits[row] -= 10.0
                continue
            x_logits[row, :, _X_PEAK + row * _ROW_STRIDE] = 5.0
            y_logits[row, :, _Y_PEAK + row * _ROW_STRIDE] = 5.0
        return [x_logits, y_logits]


def _make_estimator(batch_size=1, dead_rows=frozenset()):
    estimator = RTMPoseEstimator(keypoint_format="halpe26", batch_size=batch_size)
    fake = _FakeSession(dead_rows=dead_rows)
    estimator._session = fake
    estimator._input_name = "input"
    estimator._initialized = True
    return estimator, fake


def _make_frame():
    return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)


def _expected_x(row):
    return (_X_PEAK + row * _ROW_STRIDE) / _SIMCC_SPLIT_RATIO * SCALE_X


def _expected_y(row):
    return (_Y_PEAK + row * _ROW_STRIDE) / _SIMCC_SPLIT_RATIO * SCALE_Y


@pytest.mark.skipif(not ONNXRUNTIME_AVAILABLE, reason="onnxruntime not installed")
class TestEstimateBatch:

    def test_batch_returns_skeleton_per_frame(self):
        estimator, _ = _make_estimator(batch_size=3)
        frames = [_make_frame() for _ in range(3)]

        skeletons = estimator.estimate_batch(frames)

        assert len(skeletons) == 3
        for row, skeleton in enumerate(skeletons):
            assert skeleton is not None
            kpt = skeleton.keypoints[0]
            assert kpt.x == pytest.approx(_expected_x(row), abs=COORD_TOL)
            assert kpt.y == pytest.approx(_expected_y(row), abs=COORD_TOL)

    def test_single_inference_call_for_batch(self):
        estimator, fake = _make_estimator(batch_size=3)
        estimator.estimate_batch([_make_frame() for _ in range(3)])

        assert fake.received_shapes == [(3, 3, 256, 192)]

    def test_partial_batch_pads_to_constant_shape(self):
        estimator, fake = _make_estimator(batch_size=3)

        skeletons = estimator.estimate_batch([_make_frame(), _make_frame()])

        assert fake.received_shapes == [(3, 3, 256, 192)]
        assert len(skeletons) == 2

    def test_single_estimate_pads_to_batch_size(self):
        estimator, fake = _make_estimator(batch_size=3)

        skeleton = estimator.estimate(_make_frame())

        assert fake.received_shapes == [(3, 3, 256, 192)]
        assert skeleton is not None
        assert skeleton.keypoints[0].x == pytest.approx(_expected_x(0), abs=COORD_TOL)

    def test_low_confidence_view_returns_none(self):
        estimator, _ = _make_estimator(batch_size=3, dead_rows={1})

        skeletons = estimator.estimate_batch([_make_frame() for _ in range(3)])

        assert skeletons[0] is not None
        assert skeletons[1] is None
        assert skeletons[2] is not None

    def test_too_many_frames_raises(self):
        estimator, _ = _make_estimator(batch_size=2)

        with pytest.raises(ValueError):
            estimator.estimate_batch([_make_frame() for _ in range(3)])

    def test_empty_batch_returns_empty(self):
        estimator, fake = _make_estimator(batch_size=3)

        assert estimator.estimate_batch([]) == []
        assert fake.received_shapes == []

    def test_batch_shares_frame_index(self):
        estimator, _ = _make_estimator(batch_size=3)
        frames = [_make_frame() for _ in range(3)]

        first = estimator.estimate_batch(frames)
        second = estimator.estimate_batch(frames)

        assert len({s.frame_index for s in first}) == 1
        assert second[0].frame_index == first[0].frame_index + 1

    def test_invalid_batch_size_raises(self):
        with pytest.raises(ValueError):
            RTMPoseEstimator(batch_size=0)
