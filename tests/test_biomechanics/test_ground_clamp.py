"""Tests for ground plane clamping of ankle keypoints."""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.utils.ground_clamp import GroundClamp
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK


def _make_skeleton(
    positions: np.ndarray,
    confidences: np.ndarray | None = None,
    timestamp: float = 0.0,
    frame_index: int = 0,
) -> Skeleton3D:
    if confidences is None:
        confidences = np.ones(len(positions))
    return Skeleton3D.from_numpy(
        positions, confidences=confidences,
        timestamp=timestamp, frame_index=frame_index,
    )


def _standing_skeleton(
    ankle_l_y: float = 0.9,
    ankle_r_y: float = 0.9,
    ankle_l_x: float = -0.15,
    ankle_r_x: float = 0.15,
) -> np.ndarray:
    """19-keypoint skeleton in hip-centered coords (Y-down, standing)."""
    pts = np.zeros((19, 3))
    # Shoulders
    pts[CK.LEFT_SHOULDER] = [-0.18, -0.25, 0.0]
    pts[CK.RIGHT_SHOULDER] = [0.18, -0.25, 0.0]
    # Hips at origin
    pts[CK.LEFT_HIP] = [-0.12, 0.0, 0.0]
    pts[CK.RIGHT_HIP] = [0.12, 0.0, 0.0]
    # Knees
    pts[CK.LEFT_KNEE] = [ankle_l_x, 0.45, 0.0]
    pts[CK.RIGHT_KNEE] = [ankle_r_x, 0.45, 0.0]
    # Ankles
    pts[CK.LEFT_ANKLE] = [ankle_l_x, ankle_l_y, 0.0]
    pts[CK.RIGHT_ANKLE] = [ankle_r_x, ankle_r_y, 0.0]
    # Foot indices
    pts[CK.LEFT_FOOT_INDEX] = [ankle_l_x, ankle_l_y + 0.02, 0.05]
    pts[CK.RIGHT_FOOT_INDEX] = [ankle_r_x, ankle_r_y + 0.02, 0.05]
    return pts


def _folded_skeleton() -> np.ndarray:
    """Hallucinated folded-leg skeleton matching session 2026-07-22_11-39-49:
    ankles at hip height, feet at knee height, bone lengths plausible."""
    pts = np.zeros((19, 3))
    pts[CK.LEFT_SHOULDER] = [-0.18, -0.42, 0.0]
    pts[CK.RIGHT_SHOULDER] = [0.18, -0.42, 0.0]
    pts[CK.LEFT_HIP] = [-0.10, 0.0, 0.03]
    pts[CK.RIGHT_HIP] = [0.10, 0.0, -0.03]
    pts[CK.LEFT_KNEE] = [-0.15, 0.34, -0.24]
    pts[CK.RIGHT_KNEE] = [0.15, 0.34, -0.24]
    pts[CK.LEFT_ANKLE] = [-0.12, 0.05, 0.07]
    pts[CK.RIGHT_ANKLE] = [0.12, 0.05, 0.07]
    pts[CK.LEFT_FOOT_INDEX] = [-0.25, 0.36, -0.18]
    pts[CK.RIGHT_FOOT_INDEX] = [0.25, 0.36, -0.18]
    return pts


def _calibrate(clamp: GroundClamp, frames: int = 30) -> None:
    for i in range(frames):
        clamp.clamp(_make_skeleton(
            _standing_skeleton(), frame_index=i, timestamp=i / 30.0,
        ))
    assert clamp.is_calibrated


class TestGroundClamp:

    def test_passthrough_during_calibration(self):
        clamp = GroundClamp(calibration_frames=5)
        pts = _standing_skeleton()
        for i in range(5):
            result = clamp.clamp(_make_skeleton(pts, frame_index=i))
            assert np.allclose(result.to_numpy(), pts, atol=1e-10)

    def test_calibrates_after_n_frames(self):
        clamp = GroundClamp(calibration_frames=10)
        assert not clamp.is_calibrated
        _calibrate(clamp, frames=10)
        assert clamp.is_calibrated

    def test_ankle_y_equalization(self):
        """When one ankle drifts higher, both are averaged to the same Y."""
        clamp = GroundClamp(calibration_frames=5, ankle_y_tolerance_m=0.005)
        _calibrate(clamp, frames=5)

        # Both below calibrated max (0.9) so floor clamp doesn't interfere
        pts = _standing_skeleton()
        pts[CK.LEFT_ANKLE, 1] = 0.85
        pts[CK.RIGHT_ANKLE, 1] = 0.89

        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()
        assert result_pts[CK.LEFT_ANKLE, 1] == pytest.approx(
            result_pts[CK.RIGHT_ANKLE, 1], abs=1e-10,
        )
        assert result_pts[CK.LEFT_ANKLE, 1] == pytest.approx(0.87, abs=1e-6)

    def test_ankle_y_within_tolerance_unchanged(self):
        """Ankle Y difference within tolerance is not corrected."""
        clamp = GroundClamp(calibration_frames=5, ankle_y_tolerance_m=0.05)
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton(ankle_l_y=0.88, ankle_r_y=0.90)
        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()
        assert result_pts[CK.LEFT_ANKLE, 1] == pytest.approx(0.88, abs=1e-6)
        assert result_pts[CK.RIGHT_ANKLE, 1] == pytest.approx(0.90, abs=1e-6)

    def test_floor_penetration_clamped(self):
        """Ankle Y beyond calibrated maximum is clamped (can't go through floor)."""
        clamp = GroundClamp(calibration_frames=5)
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton()
        pts[CK.LEFT_ANKLE, 1] = 0.95
        pts[CK.RIGHT_ANKLE, 1] = 0.95

        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()
        assert result_pts[CK.LEFT_ANKLE, 1] == pytest.approx(0.9, abs=1e-6)
        assert result_pts[CK.RIGHT_ANKLE, 1] == pytest.approx(0.9, abs=1e-6)

    def test_stance_width_preserved(self):
        """If ankles slide apart, they are pushed back to calibrated width."""
        clamp = GroundClamp(
            calibration_frames=5, stance_width_tolerance_m=0.01,
        )
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton()
        pts[CK.LEFT_ANKLE, 0] = -0.25
        pts[CK.RIGHT_ANKLE, 0] = 0.25

        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()
        width = abs(result_pts[CK.LEFT_ANKLE, 0] - result_pts[CK.RIGHT_ANKLE, 0])
        calibrated_width = 0.30
        assert width == pytest.approx(calibrated_width, abs=0.011)

    def test_stance_width_within_tolerance_unchanged(self):
        """Stance width within tolerance passes through."""
        clamp = GroundClamp(
            calibration_frames=5, stance_width_tolerance_m=0.05,
        )
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton(ankle_l_x=-0.16, ankle_r_x=0.16)
        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()
        assert result_pts[CK.LEFT_ANKLE, 0] == pytest.approx(-0.16, abs=1e-6)
        assert result_pts[CK.RIGHT_ANKLE, 0] == pytest.approx(0.16, abs=1e-6)

    def test_foot_indices_propagated(self):
        """Foot index keypoints move with their ankle corrections."""
        clamp = GroundClamp(calibration_frames=5, ankle_y_tolerance_m=0.005)
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton()
        original_foot_l = pts[CK.LEFT_FOOT_INDEX].copy()
        pts[CK.LEFT_ANKLE, 1] = 0.95
        pts[CK.RIGHT_ANKLE, 1] = 0.95

        result = clamp.clamp(_make_skeleton(pts, frame_index=10))
        result_pts = result.to_numpy()

        ankle_delta_y = result_pts[CK.LEFT_ANKLE, 1] - 0.95
        foot_delta_y = result_pts[CK.LEFT_FOOT_INDEX, 1] - original_foot_l[1]
        assert foot_delta_y == pytest.approx(ankle_delta_y, abs=1e-6)

    def test_low_confidence_ankle_skipped(self):
        """Skeleton returned unchanged when ankle confidence is too low."""
        clamp = GroundClamp(calibration_frames=5)
        _calibrate(clamp, frames=5)

        pts = _standing_skeleton()
        pts[CK.LEFT_ANKLE, 1] = 0.95
        confs = np.ones(19)
        confs[CK.LEFT_ANKLE] = 0.05

        result = clamp.clamp(_make_skeleton(pts, confs, frame_index=10))
        assert np.allclose(result.to_numpy(), pts, atol=1e-10)

    def test_reset_clears_calibration(self):
        clamp = GroundClamp(calibration_frames=5)
        _calibrate(clamp, frames=5)
        assert clamp.is_calibrated
        clamp.reset()
        assert not clamp.is_calibrated


class TestCalibrationSanity:
    """Calibration must be rejected when the observed leg extension is
    implausible for a standing person — otherwise a hallucinated folded
    pose (ankles at hip height) gets locked in and enforced all session
    (regression from session 2026-07-22_11-39-49)."""

    def test_folded_calibration_rejected(self):
        clamp = GroundClamp(calibration_frames=5)
        pts = _folded_skeleton()
        for i in range(20):
            result = clamp.clamp(_make_skeleton(pts, frame_index=i))
            assert np.allclose(result.to_numpy(), pts, atol=1e-10)
        assert not clamp.is_calibrated

    def test_recovers_after_rejected_calibration(self):
        clamp = GroundClamp(calibration_frames=5)
        for i in range(5):
            clamp.clamp(_make_skeleton(_folded_skeleton(), frame_index=i))
        assert not clamp.is_calibrated

        _calibrate(clamp, frames=5)
        assert clamp.is_calibrated

        # Calibrated values must come from the sane frames: a floor-
        # penetrating ankle clamps to the sane 0.9, not the folded 0.05.
        pts = _standing_skeleton()
        pts[CK.LEFT_ANKLE, 1] = 0.95
        pts[CK.RIGHT_ANKLE, 1] = 0.95
        result = clamp.clamp(_make_skeleton(pts, frame_index=20))
        assert result.to_numpy()[CK.LEFT_ANKLE, 1] == pytest.approx(0.9, abs=1e-6)

    def test_sane_calibration_still_accepted(self):
        clamp = GroundClamp(calibration_frames=5)
        _calibrate(clamp, frames=5)
        assert clamp.is_calibrated
