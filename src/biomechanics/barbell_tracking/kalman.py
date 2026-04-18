"""
2D constant-velocity Kalman filter.

State vector: [x, y, vx, vy]  (position in pixels, velocity in pixels/sec).
Measurement vector: [x, y].

Used to smooth bar keypoint positions across frames and to fill gaps when a
detection is missing.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


class KalmanFilter2D:
    """
    Constant-velocity 2D Kalman filter.

    ``predict(dt)`` should be called every frame. ``correct(measurement)``
    should be called only on frames where a fresh measurement exists; on
    missing frames, state carries forward on the prediction alone.

    Parameters
    ----------
    q : float
        Process noise scalar. Larger = trusts predictions less, tracks
        faster changes, noisier. Default 1e-2.
    r : float
        Measurement noise scalar (variance in px^2). Larger = smooths more.
        Default 1.0.
    """

    def __init__(self, q: float = 1e-2, r: float = 1.0):
        self._q = float(q)
        self._r = float(r)

        self.x = np.zeros(4, dtype=np.float64)            # state
        self.P = np.eye(4, dtype=np.float64) * 1000.0     # covariance (huge until first measurement)

        self._H = np.array(
            [[1.0, 0.0, 0.0, 0.0],
             [0.0, 1.0, 0.0, 0.0]],
            dtype=np.float64,
        )
        self._R = np.eye(2, dtype=np.float64) * self._r

        self._initialized = False

    @property
    def state(self) -> Tuple[float, float, float, float]:
        return float(self.x[0]), float(self.x[1]), float(self.x[2]), float(self.x[3])

    @property
    def position(self) -> Tuple[float, float]:
        return float(self.x[0]), float(self.x[1])

    @property
    def velocity(self) -> Tuple[float, float]:
        return float(self.x[2]), float(self.x[3])

    def reset(self) -> None:
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 1000.0
        self._initialized = False

    def predict(self, dt: float) -> None:
        """Advance state by ``dt`` seconds under the constant-velocity model."""
        if not self._initialized or dt <= 0.0:
            return

        F = np.array(
            [[1.0, 0.0, dt, 0.0],
             [0.0, 1.0, 0.0, dt],
             [0.0, 0.0, 1.0, 0.0],
             [0.0, 0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

        # Process noise for constant-velocity — standard discrete-time formulation.
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        Q = self._q * np.array(
            [[dt4 / 4.0, 0.0,        dt3 / 2.0, 0.0      ],
             [0.0,       dt4 / 4.0,  0.0,       dt3 / 2.0],
             [dt3 / 2.0, 0.0,        dt2,       0.0      ],
             [0.0,       dt3 / 2.0,  0.0,       dt2      ]],
            dtype=np.float64,
        )

        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def correct(self, measurement: Tuple[float, float]) -> None:
        """Apply a new position measurement."""
        z = np.asarray(measurement, dtype=np.float64).reshape(2)

        if not self._initialized:
            # Cold start: snap position to measurement, reset velocity to zero,
            # shrink covariance so the first few predicts don't explode.
            self.x[:] = [z[0], z[1], 0.0, 0.0]
            self.P = np.eye(4, dtype=np.float64) * 10.0
            self._initialized = True
            return

        y = z - self._H @ self.x                 # innovation
        S = self._H @ self.P @ self._H.T + self._R
        K = self.P @ self._H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4, dtype=np.float64) - K @ self._H) @ self.P
