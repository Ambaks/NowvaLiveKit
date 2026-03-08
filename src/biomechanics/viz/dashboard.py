"""
OpenCV-based Debug Dashboard

Renders a composite view showing:
  - Camera feed with skeleton overlay (left)
  - Joint angles / rep counter / faults text panel (right)
  - Per-layer latency bars + FPS counter (bottom)
"""

import time
from collections import deque
from typing import Optional

import cv2
import numpy as np

from biomechanics.utils.types import (
    PipelineFrame,
    Skeleton2D,
    FaultSeverity,
)
from biomechanics.faults import RepCounter


# Colors (BGR)
_GREEN = (0, 255, 0)
_YELLOW = (0, 255, 255)
_ORANGE = (0, 165, 255)
_RED = (0, 0, 255)
_WHITE = (255, 255, 255)
_GRAY = (128, 128, 128)
_BLACK = (0, 0, 0)
_CYAN = (255, 255, 0)

_SEVERITY_COLORS = {
    FaultSeverity.NONE: _GREEN,
    FaultSeverity.MILD: _YELLOW,
    FaultSeverity.MODERATE: _ORANGE,
    FaultSeverity.SEVERE: _RED,
}

_PHASE_COLORS = {
    "idle": _WHITE,
    "descending": _CYAN,
    "bottom": _YELLOW,
    "ascending": _GREEN,
}

# Latency bar colors per layer
_LAYER_COLORS = {
    "capture": (200, 200, 200),
    "pose": (255, 180, 0),
    "ik": (0, 200, 0),
    "faults": (0, 100, 255),
}


class DebugDashboard:
    """Renders an OpenCV debug dashboard from PipelineFrame data."""

    PANEL_WIDTH = 320
    BAR_HEIGHT = 40

    def __init__(self):
        self._frame_times: deque = deque(maxlen=60)
        self._last_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        camera_frame: np.ndarray,
        pf: PipelineFrame,
        rep_counter: RepCounter,
    ) -> np.ndarray:
        """
        Compose the full dashboard image.

        Args:
            camera_frame: Raw BGR frame from webcam.
            pf: Current PipelineFrame result.
            rep_counter: RepCounter instance for phase/count info.

        Returns:
            Composited BGR image ready for cv2.imshow.
        """
        h, w = camera_frame.shape[:2]

        # -- Draw skeleton on camera frame --
        vis = camera_frame.copy()
        if pf.skeleton_2d is not None:
            skel_color = _RED if pf.faults else (_YELLOW if rep_counter.in_rep else _GREEN)
            self._draw_skeleton(vis, pf.skeleton_2d, skel_color)

        # -- Build right panel --
        panel = np.zeros((h, self.PANEL_WIDTH, 3), dtype=np.uint8)
        self._draw_text_panel(panel, pf, rep_counter)

        # -- Combine left + right --
        combined = np.hstack([vis, panel])

        # -- Draw latency bar at bottom --
        bar = np.zeros((self.BAR_HEIGHT, combined.shape[1], 3), dtype=np.uint8)
        self._draw_latency_bar(bar, pf.latency_ms)

        # -- FPS --
        now = time.time()
        self._frame_times.append(now - self._last_time)
        self._last_time = now
        fps = 1.0 / (sum(self._frame_times) / len(self._frame_times)) if self._frame_times else 0
        cv2.putText(
            bar, f"FPS: {fps:.1f}",
            (combined.shape[1] - 120, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, _WHITE, 1,
        )

        return np.vstack([combined, bar])

    # ------------------------------------------------------------------
    # Internal drawing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_skeleton(frame: np.ndarray, skeleton_2d: Skeleton2D, color: tuple):
        connections = [
            (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16),
        ]
        for i, j in connections:
            kp1 = skeleton_2d.keypoints[i]
            kp2 = skeleton_2d.keypoints[j]
            if kp1.confidence > 0.3 and kp2.confidence > 0.3:
                pt1 = (int(kp1.x), int(kp1.y))
                pt2 = (int(kp2.x), int(kp2.y))
                cv2.line(frame, pt1, pt2, color, 2)
        for kp in skeleton_2d.keypoints:
            if kp.confidence > 0.3:
                cv2.circle(frame, (int(kp.x), int(kp.y)), 5, color, -1)

    @staticmethod
    def _draw_text_panel(panel: np.ndarray, pf: PipelineFrame, rc: RepCounter):
        y = 30
        lh = 24  # line height

        cv2.putText(panel, "BIOMECHANICS", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, _WHITE, 2)
        y += lh + 10

        # Rep count
        cv2.putText(panel, f"Reps: {rc.rep_count}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, _GREEN, 2)
        y += lh

        # Phase
        phase = rc.phase.upper()
        pc = _PHASE_COLORS.get(phase.lower(), _WHITE)
        cv2.putText(panel, f"Phase: {phase}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, pc, 1)
        y += lh + 5

        # Joint angles
        angles = pf.joint_angles
        if angles is not None:
            cv2.putText(panel, "Joint Angles:", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GRAY, 1)
            y += lh - 4
            knee = angles.avg_knee_flexion
            hip = (angles.hip_flexion_l + angles.hip_flexion_r) / 2
            cv2.putText(panel, f"  Knee: {knee:.1f} deg", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _WHITE, 1)
            y += lh - 6
            cv2.putText(panel, f"  Hip:  {hip:.1f} deg", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _WHITE, 1)
            y += lh - 6
            cv2.putText(panel, f"  Trunk: {angles.trunk_flexion:.1f} deg", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _WHITE, 1)
            y += lh

        # Faults
        if pf.faults:
            cv2.putText(panel, "Active Faults:", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _RED, 1)
            y += lh - 4
            for fault in pf.faults[:4]:
                fc = _SEVERITY_COLORS.get(fault.severity, _RED)
                cv2.putText(panel, f"  {fault.fault_type} ({fault.severity.value})", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, fc, 1)
                y += lh - 6
        else:
            cv2.putText(panel, "No faults", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GREEN, 1)
            y += lh

        # Rep data (if just completed)
        if pf.rep_data is not None:
            y += 5
            rd = pf.rep_data
            cv2.putText(panel, f"Rep {rd.rep_number} done!", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, _GREEN, 2)
            y += lh
            cv2.putText(panel, f"  Depth: {rd.max_depth_angle:.0f} deg", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _WHITE, 1)

    @staticmethod
    def _draw_latency_bar(bar: np.ndarray, latency_ms: dict):
        total = sum(latency_ms.values()) or 1.0
        bar_w = bar.shape[1] - 140  # leave space for FPS text
        x = 5
        for layer, ms in latency_ms.items():
            w = max(int(bar_w * ms / total), 1)
            color = _LAYER_COLORS.get(layer, (100, 100, 100))
            cv2.rectangle(bar, (x, 5), (x + w, 30), color, -1)
            if w > 40:
                label = f"{layer} {ms:.0f}ms"
                cv2.putText(bar, label, (x + 3, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.35, _BLACK, 1)
            x += w + 2
