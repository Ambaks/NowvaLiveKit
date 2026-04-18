"""
BarPathTracker — Kalman-smoothed barbell tracking.

Responsibilities:
- Smooth left + right bar keypoints through independent constant-velocity
  Kalman filters. State carries forward on frames where the detector drops.
- Cache a ``px_per_meter`` calibration factor computed from the known
  Olympic-bar length; used to convert pixel velocities into m/s.
- Maintain a rolling center-path history for overlay visualization.
- Emit a lightweight rep-phase hint (standing / descending / ascending)
  from the sign of the center's vertical velocity. This is for UX only —
  authoritative rep counting still comes from the pose-based counters.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Optional, Tuple

from biomechanics.barbell_tracking.kalman import KalmanFilter2D
from biomechanics.utils.types import BarbellDetection, BarTrackState


_PHASE_VEL_EPS_MPS = 0.05  # |vy| below this → standing / transition


class BarPathTracker:
    """
    Wraps two ``KalmanFilter2D`` instances (left and right bar endpoints) plus
    calibration and path-history bookkeeping.

    Call ``update(detection)`` once per frame. When detection is None, the
    Kalman state is still advanced on prediction alone, so smoothed_* fields
    remain valid through short gaps.
    """

    def __init__(
        self,
        bar_length_m: float = 2.2,
        kalman_q: float = 1e-2,
        kalman_r: float = 1.0,
        path_history_len: int = 120,
    ):
        self._bar_length_m = float(bar_length_m)
        self._path_history_len = int(path_history_len)

        self._kf_left = KalmanFilter2D(q=kalman_q, r=kalman_r)
        self._kf_right = KalmanFilter2D(q=kalman_q, r=kalman_r)

        self._last_ts: Optional[float] = None
        self._px_per_meter: Optional[float] = None

        self._path: Deque[Tuple[float, float]] = deque(maxlen=self._path_history_len)

        # 2-point velocity derivative → acceleration (m/s²).
        self._prev_velocity_mps: Optional[Tuple[float, float]] = None
        self._prev_vel_ts: Optional[float] = None

        self._initialized = False

    @property
    def px_per_meter(self) -> Optional[float]:
        return self._px_per_meter

    def reset(self) -> None:
        self._kf_left.reset()
        self._kf_right.reset()
        self._last_ts = None
        self._px_per_meter = None
        self._path.clear()
        self._prev_velocity_mps = None
        self._prev_vel_ts = None
        self._initialized = False

    def update(self, detection: Optional[BarbellDetection], timestamp: Optional[float] = None) -> BarTrackState:
        now = float(timestamp) if timestamp is not None else time.time()
        dt = (now - self._last_ts) if self._last_ts is not None else 0.0
        if dt < 0.0:
            dt = 0.0

        # Predict step first (for both filters)
        if self._initialized and dt > 0.0:
            self._kf_left.predict(dt)
            self._kf_right.predict(dt)

        # Correct when we have a measurement
        if detection is not None:
            self._kf_left.correct((detection.left_end.x, detection.left_end.y))
            self._kf_right.correct((detection.right_end.x, detection.right_end.y))
            # Refresh calibration from the freshest raw measurement
            raw_len_px = math.hypot(
                detection.right_end.x - detection.left_end.x,
                detection.right_end.y - detection.left_end.y,
            )
            if raw_len_px > 1.0 and self._bar_length_m > 0.0:
                self._px_per_meter = raw_len_px / self._bar_length_m
            self._initialized = True

        self._last_ts = now

        # Pull smoothed state
        lx, ly = self._kf_left.position
        rx, ry = self._kf_right.position
        cx, cy = (lx + rx) / 2.0, (ly + ry) / 2.0

        # Tilt from smoothed endpoints
        dx = rx - lx
        dy = ry - ly
        tilt_deg = math.degrees(math.atan2(dy, dx)) if (dx != 0.0 or dy != 0.0) else 0.0

        # Velocity: average of the two endpoints' velocities, in px/sec → m/s via calibration
        vlx, vly = self._kf_left.velocity
        vrx, vry = self._kf_right.velocity
        vx_px, vy_px = (vlx + vrx) / 2.0, (vly + vry) / 2.0
        if self._px_per_meter and self._px_per_meter > 0.0:
            vx_mps = vx_px / self._px_per_meter
            vy_mps = vy_px / self._px_per_meter
        else:
            vx_mps = 0.0
            vy_mps = 0.0
        velocity_mps = (vx_mps, vy_mps)

        # Acceleration via finite difference of velocity
        if self._prev_velocity_mps is not None and self._prev_vel_ts is not None:
            d = now - self._prev_vel_ts
            if d > 1e-6:
                ax = (vx_mps - self._prev_velocity_mps[0]) / d
                ay = (vy_mps - self._prev_velocity_mps[1]) / d
            else:
                ax = ay = 0.0
        else:
            ax = ay = 0.0
        acceleration_mps2 = (ax, ay)
        self._prev_velocity_mps = velocity_mps
        self._prev_vel_ts = now

        # Path history (only push when we have a valid init)
        if self._initialized:
            self._path.append((cx, cy))

        rep_phase = self._derive_phase(vy_mps)

        return BarTrackState(
            raw=detection,
            smoothed_left=(lx, ly),
            smoothed_right=(rx, ry),
            smoothed_center=(cx, cy),
            tilt_degrees=tilt_deg,
            velocity_mps=velocity_mps,
            acceleration_mps2=acceleration_mps2,
            px_per_meter=self._px_per_meter,
            path_history=list(self._path),
            rep_phase_hint=rep_phase,
            timestamp=now,
            frame_index=detection.frame_index if detection is not None else 0,
        )

    @staticmethod
    def _derive_phase(vy_mps: float) -> str:
        """
        Image coordinates have y increasing downward. So vy > 0 → bar going
        DOWN (descending), vy < 0 → bar going UP (ascending).
        """
        if vy_mps > _PHASE_VEL_EPS_MPS:
            return "descending"
        if vy_mps < -_PHASE_VEL_EPS_MPS:
            return "ascending"
        return "standing"
