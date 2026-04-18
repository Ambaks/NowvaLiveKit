"""
OpenCV drawing helpers for barbell detection / tracking visualizations.

Two entry points:

- ``draw_detection_only(frame, detection)`` — bare-bones: bbox + horizontal bar line.
  Used by ``scripts/test_barbell_detection.py`` for real-time model validation.

- ``draw_barbell_overlay(frame, track_state, tilt_warn_deg, tilt_error_deg)`` — full:
  bbox (if raw detection), smoothed bar line color-coded by tilt, fading path trail,
  and a top-left text block with tilt/velocity/rep-phase.
  Used by ``scripts/barbell_tracker_demo.py``.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from biomechanics.utils.types import BarbellDetection, BarTrackState


# BGR colors
_WHITE = (255, 255, 255)
_CYAN = (255, 255, 0)
_GREEN = (0, 220, 0)
_YELLOW = (0, 220, 220)
_RED = (0, 0, 220)
_GRAY = (140, 140, 140)


def _tilt_color(tilt_deg: float, warn_deg: float, error_deg: float) -> tuple:
    t = abs(tilt_deg)
    if t <= warn_deg:
        return _GREEN
    if t <= error_deg:
        return _YELLOW
    return _RED


def draw_detection_only(
    frame: np.ndarray,
    detection: Optional[BarbellDetection],
) -> np.ndarray:
    """
    Minimal overlay: YOLO bbox + cyan line connecting the two bar keypoints.

    Intended for real-time model validation — no smoothing, no rep state,
    no dependencies on the tracker. Mutates and returns the input frame.
    """
    if detection is None:
        cv2.putText(
            frame, "no barbell", (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, _GRAY, 1, cv2.LINE_AA,
        )
        return frame

    if detection.bbox_xyxy is not None:
        x1, y1, x2, y2 = [int(v) for v in detection.bbox_xyxy]
        cv2.rectangle(frame, (x1, y1), (x2, y2), _WHITE, 2)

    lx, ly = int(detection.left_end.x), int(detection.left_end.y)
    rx, ry = int(detection.right_end.x), int(detection.right_end.y)
    cv2.line(frame, (lx, ly), (rx, ry), _CYAN, 3, cv2.LINE_AA)
    cv2.circle(frame, (lx, ly), 6, _CYAN, -1)
    cv2.circle(frame, (rx, ry), 6, _CYAN, -1)

    text = f"conf={detection.bbox_conf:.2f}  tilt={detection.tilt_degrees:+.1f}deg"
    cv2.putText(
        frame, text, (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, _WHITE, 1, cv2.LINE_AA,
    )
    return frame


def draw_barbell_overlay(
    frame: np.ndarray,
    track_state: Optional[BarTrackState],
    tilt_warn_deg: float = 2.0,
    tilt_error_deg: float = 5.0,
) -> np.ndarray:
    """
    Full tracker overlay: bbox (if raw detection), tilt-colored smoothed bar,
    fading center-path trail, text block with tilt/velocity/rep-phase.
    """
    if track_state is None:
        cv2.putText(
            frame, "no track state", (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, _GRAY, 1, cv2.LINE_AA,
        )
        return frame

    # Raw YOLO bbox (if present this frame)
    if track_state.raw is not None and track_state.raw.bbox_xyxy is not None:
        x1, y1, x2, y2 = [int(v) for v in track_state.raw.bbox_xyxy]
        cv2.rectangle(frame, (x1, y1), (x2, y2), _WHITE, 1)

    # Smoothed bar line, color-coded by tilt
    color = _tilt_color(track_state.tilt_degrees, tilt_warn_deg, tilt_error_deg)
    lx, ly = int(track_state.smoothed_left[0]), int(track_state.smoothed_left[1])
    rx, ry = int(track_state.smoothed_right[0]), int(track_state.smoothed_right[1])
    cx, cy = int(track_state.smoothed_center[0]), int(track_state.smoothed_center[1])
    cv2.line(frame, (lx, ly), (rx, ry), color, 3, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 5, color, -1)

    # Fading center path trail (older = darker)
    history = track_state.path_history
    n = len(history)
    if n >= 2:
        for i in range(1, n):
            age = i / max(n - 1, 1)          # 0 → oldest, 1 → newest
            shade = int(80 + 175 * age)
            trail_color = (shade, shade, shade)
            p0 = (int(history[i - 1][0]), int(history[i - 1][1]))
            p1 = (int(history[i][0]), int(history[i][1]))
            cv2.line(frame, p0, p1, trail_color, 2, cv2.LINE_AA)

    # Text block
    vx, vy = track_state.velocity_mps
    speed = float(np.hypot(vx, vy))
    lines = [
        f"tilt  {track_state.tilt_degrees:+.1f} deg",
        f"vel   {speed:.2f} m/s",
        f"phase {track_state.rep_phase_hint}",
    ]
    y = 26
    for ln in lines:
        cv2.putText(
            frame, ln, (12, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, _WHITE, 1, cv2.LINE_AA,
        )
        y += 24

    return frame
