"""Tests for demo_renderer easing, projection, and choreographer state machine."""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.diagnosis.demo_builder import DemoCue, DemoData
from biomechanics.viz.demo_renderer import (
    BG_COLOR,
    FINAL_HOLD_SECONDS,
    MORPH_IN_SECONDS,
    MORPH_OUT_SECONDS,
    POSE_HEIGHT_FRAC,
    SETTLE_SECONDS,
    YOYO_HOLD_SECONDS,
    YOYO_TRAVEL_SECONDS,
    DemoChoreographer,
    interpolate_pose,
    project_pose_stack,
    yoyo_weight,
)

WEIGHT_TOL = 1e-9
PIXEL_TOL = 1.0

FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def _make_pose(stance_half_width: float = 0.15) -> np.ndarray:
    pose = np.zeros((19, 3), dtype=np.float32)
    pose[0] = [0.0, 1.6, 0.0]
    pose[5] = [0.0, 1.2, -0.18]
    pose[6] = [0.0, 1.2, 0.18]
    pose[7] = [0.15, 1.0, -0.20]
    pose[8] = [0.15, 1.0, 0.20]
    pose[9] = [0.25, 0.85, -0.20]
    pose[10] = [0.25, 0.85, 0.20]
    pose[11] = [0.0, 0.50, -0.15]
    pose[12] = [0.0, 0.50, 0.15]
    pose[13] = [0.10, 0.30, -0.13]
    pose[14] = [0.10, 0.30, 0.13]
    pose[15] = [0.0, 0.0, -stance_half_width]
    pose[16] = [0.0, 0.0, stance_half_width]
    pose[17] = [0.15, 0.0, -stance_half_width]
    pose[18] = [0.15, 0.0, stance_half_width]
    return pose


def _make_demo(num_cues: int = 2) -> DemoData:
    pose_stack = np.stack(
        [_make_pose(stance_half_width=0.15 + 0.03 * k) for k in range(num_cues + 1)]
    )
    cues = [
        DemoCue(
            cue_index=k,
            cause_id="narrow_stance",
            explanation="test",
            magnitude_text="about 3 centimeters wider on each side",
        )
        for k in range(num_cues)
    ]
    return DemoData(pose_stack=pose_stack, cues=cues)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TestYoyoWeight:

    def test_weight_zero_at_start(self) -> None:
        assert yoyo_weight(0.0, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS) == pytest.approx(
            0.0, abs=WEIGHT_TOL,
        )

    def test_weight_one_after_hold_and_travel(self) -> None:
        elapsed = YOYO_HOLD_SECONDS + YOYO_TRAVEL_SECONDS
        assert yoyo_weight(elapsed, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS) == pytest.approx(
            1.0, abs=WEIGHT_TOL,
        )

    def test_weight_holds_at_endpoints(self) -> None:
        start_hold = YOYO_HOLD_SECONDS * 0.5
        end_hold = YOYO_HOLD_SECONDS + YOYO_TRAVEL_SECONDS + YOYO_HOLD_SECONDS * 0.5

        assert yoyo_weight(start_hold, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS) == pytest.approx(
            0.0, abs=WEIGHT_TOL,
        )
        assert yoyo_weight(end_hold, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS) == pytest.approx(
            1.0, abs=WEIGHT_TOL,
        )

    def test_weight_returns_to_zero_after_full_period(self) -> None:
        period = 2.0 * (YOYO_TRAVEL_SECONDS + YOYO_HOLD_SECONDS)
        assert yoyo_weight(period, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS) == pytest.approx(
            0.0, abs=WEIGHT_TOL,
        )

    def test_weight_periodic(self) -> None:
        period = 2.0 * (YOYO_TRAVEL_SECONDS + YOYO_HOLD_SECONDS)
        sample = YOYO_HOLD_SECONDS + YOYO_TRAVEL_SECONDS * 0.3

        first = yoyo_weight(sample, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS)
        second = yoyo_weight(sample + period, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS)

        assert first == pytest.approx(second, abs=WEIGHT_TOL)


class TestProjectPoseStack:

    def test_hip_midpoint_centered_horizontally(self) -> None:
        pose_stack = _make_demo(num_cues=1).pose_stack

        projected = project_pose_stack(pose_stack, FRAME_WIDTH, FRAME_HEIGHT)

        hip_mid_x = (projected[0, 11, 0] + projected[0, 12, 0]) / 2.0
        assert hip_mid_x == pytest.approx(FRAME_WIDTH / 2.0, abs=PIXEL_TOL)

    def test_pose_height_fills_target_fraction(self) -> None:
        pose_stack = _make_demo(num_cues=1).pose_stack

        projected = project_pose_stack(pose_stack, FRAME_WIDTH, FRAME_HEIGHT)

        height_px = projected[0, :, 1].max() - projected[0, :, 1].min()
        assert height_px == pytest.approx(POSE_HEIGHT_FRAC * FRAME_HEIGHT, abs=PIXEL_TOL)

    def test_higher_y_maps_to_smaller_pixel_row(self) -> None:
        pose_stack = _make_demo(num_cues=1).pose_stack

        projected = project_pose_stack(pose_stack, FRAME_WIDTH, FRAME_HEIGHT)

        nose_row = projected[0, 0, 1]
        ankle_row = projected[0, 15, 1]
        assert nose_row < ankle_row

    def test_same_transform_across_stack(self) -> None:
        pose_stack = _make_demo(num_cues=1).pose_stack

        projected = project_pose_stack(pose_stack, FRAME_WIDTH, FRAME_HEIGHT)

        shared_row = projected[:, 0, 1]
        assert shared_row[0] == pytest.approx(shared_row[1], abs=PIXEL_TOL)


class TestInterpolatePose:

    def test_endpoints(self) -> None:
        pose_a = np.zeros((19, 2), dtype=np.float32)
        pose_b = np.full((19, 2), 10.0, dtype=np.float32)
        out = np.empty((19, 2), dtype=np.float32)

        np.testing.assert_allclose(interpolate_pose(pose_a, pose_b, 0.0, out), pose_a)
        np.testing.assert_allclose(interpolate_pose(pose_a, pose_b, 1.0, out), pose_b)

    def test_midpoint(self) -> None:
        pose_a = np.zeros((19, 2), dtype=np.float32)
        pose_b = np.full((19, 2), 10.0, dtype=np.float32)
        out = np.empty((19, 2), dtype=np.float32)

        result = interpolate_pose(pose_a, pose_b, 0.5, out)

        np.testing.assert_allclose(result, np.full((19, 2), 5.0), atol=1e-6)


class TestDemoChoreographer:

    def _make_active_choreographer(self) -> tuple[DemoChoreographer, _FakeClock, np.ndarray]:
        clock = _FakeClock()
        choreographer = DemoChoreographer(now_fn=clock)
        frame = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 128, dtype=np.uint8)
        choreographer.start(_make_demo(), live_skeleton_px=None)
        return choreographer, clock, frame

    def test_inactive_before_start(self) -> None:
        choreographer = DemoChoreographer(now_fn=_FakeClock())
        frame = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 128, dtype=np.uint8)

        assert not choreographer.is_active
        assert choreographer.render(frame) is frame

    def test_active_after_start(self) -> None:
        choreographer, _, frame = self._make_active_choreographer()

        assert choreographer.is_active
        assert choreographer.render(frame) is not frame

    def test_morph_in_blends_toward_background(self) -> None:
        choreographer, clock, frame = self._make_active_choreographer()

        clock.now = MORPH_IN_SECONDS * 0.95
        display = choreographer.render(frame)

        corner = display[0, 0]
        background = np.array(BG_COLOR)
        assert np.abs(corner.astype(int) - background).max() < np.abs(
            frame[0, 0].astype(int) - background
        ).max()

    def test_advance_cue_then_finish_returns_to_idle(self) -> None:
        choreographer, clock, frame = self._make_active_choreographer()

        clock.now = MORPH_IN_SECONDS + 0.1
        choreographer.render(frame)
        choreographer.advance_cue(0)
        clock.now += SETTLE_SECONDS + 0.1
        choreographer.render(frame)
        assert choreographer.is_active

        choreographer.finish()
        clock.now += SETTLE_SECONDS + 0.1
        choreographer.render(frame)
        clock.now += FINAL_HOLD_SECONDS + 0.1
        choreographer.render(frame)
        clock.now += MORPH_OUT_SECONDS + 0.1
        result = choreographer.render(frame)

        assert not choreographer.is_active
        assert result is frame

    def test_cue_received_during_morph_in_is_deferred(self) -> None:
        choreographer, clock, frame = self._make_active_choreographer()

        choreographer.render(frame)
        clock.now = MORPH_IN_SECONDS * 0.5
        choreographer.advance_cue(0)
        display = choreographer.render(frame)

        assert choreographer.is_active
        assert display is not frame

    def test_out_of_range_cue_ignored(self) -> None:
        choreographer, clock, frame = self._make_active_choreographer()

        clock.now = MORPH_IN_SECONDS + 0.1
        choreographer.render(frame)
        choreographer.advance_cue(99)

        assert choreographer.is_active
