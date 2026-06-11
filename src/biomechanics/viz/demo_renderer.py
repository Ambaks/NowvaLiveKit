"""Choreographed coaching-demo rendering: yoyo pose animations in the live cv2 window."""

from __future__ import annotations

import time
from typing import Callable

import cv2
import numpy as np

from biomechanics.diagnosis.demo_builder import DemoData
from biomechanics.pose.base import COCO_SKELETON_CONNECTIONS

MORPH_IN_SECONDS = 0.8
MORPH_OUT_SECONDS = 0.8
YOYO_TRAVEL_SECONDS = 1.2
YOYO_HOLD_SECONDS = 0.25
SETTLE_SECONDS = 0.4
FINAL_HOLD_SECONDS = 1.0
POSE_HEIGHT_FRAC = 0.7

BG_COLOR = (20, 16, 12)
BONE_COLOR = (255, 255, 255)
JOINT_COLOR = (0, 255, 0)
HIGHLIGHT_COLOR = (0, 180, 255)
CAPTION_COLOR = (255, 255, 255)
JOINT_RADIUS_PX = 6
HIGHLIGHT_RADIUS_PX = 9
BONE_THICKNESS_PX = 3
CAPTION_FONT_SCALE = 0.9
CAPTION_MARGIN_PX = 40

FOOT_FADE_IN_WEIGHT = 0.5

DRAWN_JOINTS: tuple[int, ...] = tuple(range(5, 19))
DEMO_CONNECTIONS: tuple[tuple[int, int], ...] = tuple(
    (a, b) for a, b in COCO_SKELETON_CONNECTIONS
    if a >= min(DRAWN_JOINTS) and b >= min(DRAWN_JOINTS)
)
FOOT_CONNECTIONS: tuple[tuple[int, int], ...] = ((15, 17), (16, 18))
SHARED_JOINT_COUNT = 17

HIGHLIGHT_JOINTS: dict[str, tuple[int, ...]] = {
    "narrow_stance": (13, 14, 15, 16, 17, 18),
    "narrow_foot_angle": (15, 16, 17, 18),
    "knee_track_cue": (13, 14),
    "weight_shift_cue": (5, 6, 11, 12),
    "depth_cue_unfamiliar": (11, 12, 13, 14),
}

_IDLE = "idle"
_MORPH_IN = "morph_in"
_CUE_LOOP = "cue_loop"
_SETTLE = "settle"
_FINAL_HOLD = "final_hold"
_MORPH_OUT = "morph_out"

_HIP_L_IDX, _HIP_R_IDX = 11, 12


def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def yoyo_weight(elapsed_s: float, travel_s: float, hold_s: float) -> float:
    period = 2.0 * (travel_s + hold_s)
    phase = elapsed_s % period
    if phase < hold_s:
        return 0.0
    phase -= hold_s
    if phase < travel_s:
        return ease_in_out(phase / travel_s)
    phase -= travel_s
    if phase < hold_s:
        return 1.0
    return 1.0 - ease_in_out((phase - hold_s) / travel_s)


def project_pose_stack(
    pose_stack: np.ndarray, frame_width: int, frame_height: int,
) -> np.ndarray:
    """Project all stack poses to pixels using one transform anchored on the observed pose."""
    reference = pose_stack[0]
    lateral = reference[_HIP_R_IDX] - reference[_HIP_L_IDX]
    lateral_xz = np.array([lateral[0], lateral[2]], dtype=np.float64)
    norm = np.linalg.norm(lateral_xz)
    if norm < 1e-9:
        lateral_xz = np.array([0.0, 1.0])
    else:
        lateral_xz /= norm

    hip_mid = (reference[_HIP_L_IDX] + reference[_HIP_R_IDX]) / 2.0
    y_min = float(reference[:, 1].min())
    y_max = float(reference[:, 1].max())
    pose_height = max(y_max - y_min, 1e-6)
    scale = POSE_HEIGHT_FRAC * frame_height / pose_height
    y_mid = (y_min + y_max) / 2.0

    offsets = pose_stack - hip_mid
    lateral_px = (
        offsets[:, :, 0] * lateral_xz[0] + offsets[:, :, 2] * lateral_xz[1]
    ) * scale
    vertical_px = (pose_stack[:, :, 1] - y_mid) * scale

    projected = np.empty((pose_stack.shape[0], pose_stack.shape[1], 2), dtype=np.float32)
    projected[:, :, 0] = frame_width / 2.0 + lateral_px
    projected[:, :, 1] = frame_height / 2.0 - vertical_px
    return projected


def interpolate_pose(
    pose_a: np.ndarray, pose_b: np.ndarray, weight: float, out: np.ndarray,
) -> np.ndarray:
    np.subtract(pose_b, pose_a, out=out)
    out *= weight
    out += pose_a
    return out


def draw_demo_skeleton(
    canvas: np.ndarray,
    screen_pts: np.ndarray,
    highlight: tuple[int, ...] = (),
    draw_feet: bool = True,
) -> None:
    for start_idx, end_idx in DEMO_CONNECTIONS:
        if not draw_feet and (start_idx, end_idx) in FOOT_CONNECTIONS:
            continue
        highlighted = start_idx in highlight and end_idx in highlight
        color = HIGHLIGHT_COLOR if highlighted else BONE_COLOR
        pt1 = (int(screen_pts[start_idx, 0]), int(screen_pts[start_idx, 1]))
        pt2 = (int(screen_pts[end_idx, 0]), int(screen_pts[end_idx, 1]))
        cv2.line(canvas, pt1, pt2, color, BONE_THICKNESS_PX)

    for joint_idx in DRAWN_JOINTS:
        if not draw_feet and joint_idx >= SHARED_JOINT_COUNT:
            continue
        center = (int(screen_pts[joint_idx, 0]), int(screen_pts[joint_idx, 1]))
        if joint_idx in highlight:
            cv2.circle(canvas, center, HIGHLIGHT_RADIUS_PX, HIGHLIGHT_COLOR, -1)
        else:
            cv2.circle(canvas, center, JOINT_RADIUS_PX, JOINT_COLOR, -1)


class DemoChoreographer:
    """State machine driving the demo display: morph-in, per-cue yoyo loops, morph-out."""

    def __init__(self, now_fn: Callable[[], float] = time.monotonic) -> None:
        self._now_fn = now_fn
        self._state = _IDLE
        self._state_start = 0.0
        self._demo: DemoData | None = None
        self._live_start_px: np.ndarray | None = None
        self._pending_cue: int | None = None
        self._cue_index = 0
        self._stack_px: np.ndarray | None = None
        self._settle_from: np.ndarray | None = None
        self._settle_to: np.ndarray | None = None
        self._after_settle_cue: int | None = None
        self._canvas: np.ndarray | None = None
        self._background: np.ndarray | None = None
        self._points_buffer: np.ndarray | None = None

    @property
    def is_active(self) -> bool:
        return self._state != _IDLE

    def start(self, demo: DemoData, live_skeleton_px: np.ndarray | None) -> None:
        self._demo = demo
        self._live_start_px = live_skeleton_px
        self._pending_cue = None
        self._stack_px = None
        self._state = _MORPH_IN
        self._state_start = self._now_fn()

    def advance_cue(self, cue_index: int) -> None:
        if self._demo is None or cue_index >= len(self._demo.cues):
            return
        morphing_in = (
            self._state == _MORPH_IN
            and self._now_fn() - self._state_start < MORPH_IN_SECONDS
        )
        if self._stack_px is None or morphing_in:
            self._pending_cue = cue_index
            return
        self._begin_settle(target=self._stack_px[cue_index], next_cue=cue_index)

    def finish(self) -> None:
        if self._demo is None:
            self._state = _IDLE
            return
        if self._stack_px is None:
            self._state = _IDLE
            self._demo = None
            return
        self._begin_settle(target=self._stack_px[-1], next_cue=None)

    def render(self, camera_frame: np.ndarray) -> np.ndarray:
        if self._state == _IDLE:
            return camera_frame
        if self._stack_px is None:
            self._init_buffers(camera_frame)

        now = self._now_fn()
        elapsed = now - self._state_start

        if self._state == _SETTLE and elapsed >= SETTLE_SECONDS:
            if self._after_settle_cue is not None:
                self._cue_index = self._after_settle_cue
                self._state = _CUE_LOOP
            else:
                self._state = _FINAL_HOLD
            self._state_start = now
            elapsed = 0.0
        elif self._state == _FINAL_HOLD and elapsed >= FINAL_HOLD_SECONDS:
            self._state = _MORPH_OUT
            self._state_start = now
            elapsed = 0.0
        elif self._state == _MORPH_OUT and elapsed >= MORPH_OUT_SECONDS:
            self._state = _IDLE
            self._demo = None
            return camera_frame
        elif self._state == _MORPH_IN and self._pending_cue is not None:
            if elapsed >= MORPH_IN_SECONDS:
                cue_index = self._pending_cue
                self._pending_cue = None
                self._begin_settle(target=self._stack_px[cue_index], next_cue=cue_index)
                elapsed = 0.0

        if self._state == _MORPH_IN:
            return self._render_morph_in(camera_frame, elapsed)
        if self._state == _MORPH_OUT:
            return self._render_morph_out(camera_frame, elapsed)

        np.copyto(self._canvas, self._background)
        if self._state == _CUE_LOOP:
            cue = self._demo.cues[self._cue_index]
            weight = yoyo_weight(elapsed, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS)
            points = interpolate_pose(
                self._stack_px[self._cue_index],
                self._stack_px[self._cue_index + 1],
                weight,
                self._points_buffer,
            )
            draw_demo_skeleton(
                self._canvas, points, highlight=HIGHLIGHT_JOINTS.get(cue.cause_id, ()),
            )
            self._draw_caption(cue.magnitude_text)
        elif self._state == _SETTLE:
            weight = ease_in_out(elapsed / SETTLE_SECONDS)
            points = interpolate_pose(
                self._settle_from, self._settle_to, weight, self._points_buffer,
            )
            draw_demo_skeleton(self._canvas, points)
        else:
            draw_demo_skeleton(self._canvas, self._stack_px[-1])

        return self._canvas

    def _init_buffers(self, camera_frame: np.ndarray) -> None:
        frame_height, frame_width = camera_frame.shape[:2]
        self._stack_px = project_pose_stack(
            self._demo.pose_stack, frame_width, frame_height,
        )
        self._canvas = np.empty_like(camera_frame)
        self._background = np.empty_like(camera_frame)
        self._background[:] = BG_COLOR
        self._points_buffer = np.empty((self._stack_px.shape[1], 2), dtype=np.float32)

    def _begin_settle(self, target: np.ndarray, next_cue: int | None) -> None:
        self._settle_from = self._current_points().copy()
        self._settle_to = target
        self._after_settle_cue = next_cue
        self._state = _SETTLE
        self._state_start = self._now_fn()

    def _current_points(self) -> np.ndarray:
        elapsed = self._now_fn() - self._state_start
        if self._state == _CUE_LOOP:
            weight = yoyo_weight(elapsed, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS)
            return interpolate_pose(
                self._stack_px[self._cue_index],
                self._stack_px[self._cue_index + 1],
                weight,
                self._points_buffer,
            )
        if self._state == _SETTLE:
            weight = ease_in_out(elapsed / SETTLE_SECONDS)
            return interpolate_pose(
                self._settle_from, self._settle_to, weight, self._points_buffer,
            )
        if self._state == _MORPH_IN:
            return self._morph_in_points(min(elapsed / MORPH_IN_SECONDS, 1.0))
        return self._stack_px[-1]

    def _morph_in_points(self, weight: float) -> np.ndarray:
        observed = self._stack_px[0]
        if self._live_start_px is None:
            return observed
        eased = ease_in_out(weight)
        buffer = self._points_buffer
        np.subtract(
            observed[:SHARED_JOINT_COUNT], self._live_start_px,
            out=buffer[:SHARED_JOINT_COUNT],
        )
        buffer[:SHARED_JOINT_COUNT] *= eased
        buffer[:SHARED_JOINT_COUNT] += self._live_start_px
        buffer[SHARED_JOINT_COUNT:] = observed[SHARED_JOINT_COUNT:]
        return buffer

    def _render_morph_in(self, camera_frame: np.ndarray, elapsed: float) -> np.ndarray:
        weight = min(elapsed / MORPH_IN_SECONDS, 1.0)
        eased = ease_in_out(weight)
        cv2.addWeighted(
            camera_frame, 1.0 - eased, self._background, eased, 0.0, dst=self._canvas,
        )
        points = self._morph_in_points(weight)
        draw_demo_skeleton(self._canvas, points, draw_feet=weight >= FOOT_FADE_IN_WEIGHT)
        return self._canvas

    def _render_morph_out(self, camera_frame: np.ndarray, elapsed: float) -> np.ndarray:
        weight = ease_in_out(min(elapsed / MORPH_OUT_SECONDS, 1.0))
        cv2.addWeighted(
            self._background, 1.0 - weight, camera_frame, weight, 0.0, dst=self._canvas,
        )
        if weight < FOOT_FADE_IN_WEIGHT:
            draw_demo_skeleton(self._canvas, self._stack_px[-1])
        return self._canvas

    def _draw_caption(self, text: str) -> None:
        frame_height, frame_width = self._canvas.shape[:2]
        text_size = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, CAPTION_FONT_SCALE, 2,
        )[0]
        origin = (
            (frame_width - text_size[0]) // 2,
            frame_height - CAPTION_MARGIN_PX,
        )
        cv2.putText(
            self._canvas, text, origin,
            cv2.FONT_HERSHEY_SIMPLEX, CAPTION_FONT_SCALE, CAPTION_COLOR, 2,
        )
