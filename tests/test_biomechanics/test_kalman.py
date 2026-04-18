"""Tests for the 2D constant-velocity Kalman filter used by bar tracking."""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.barbell_tracking.kalman import KalmanFilter2D


def test_cold_start_snaps_to_first_measurement():
    kf = KalmanFilter2D()
    kf.predict(0.033)  # no-op before init
    assert kf.position == (0.0, 0.0)

    kf.correct((100.0, 200.0))
    assert kf.position == (100.0, 200.0)
    assert kf.velocity == (0.0, 0.0)


def test_tracks_constant_velocity_trajectory():
    """Feed a known-velocity trajectory and confirm the filter converges."""
    kf = KalmanFilter2D(q=1e-2, r=1.0)
    dt = 1.0 / 60.0
    vx, vy = 120.0, -40.0  # pixels/sec
    x, y = 0.0, 0.0

    rng = np.random.default_rng(42)
    for _ in range(120):
        x += vx * dt
        y += vy * dt
        noisy = (x + rng.normal(0, 0.5), y + rng.normal(0, 0.5))
        kf.predict(dt)
        kf.correct(noisy)

    est_vx, est_vy = kf.velocity
    assert est_vx == pytest.approx(vx, rel=0.1)
    assert est_vy == pytest.approx(vy, rel=0.1)


def test_fills_detection_gap_with_prediction():
    """When correct() is skipped, state must advance on prediction alone."""
    kf = KalmanFilter2D(q=1e-2, r=1.0)
    dt = 1.0 / 30.0
    vx = 90.0  # px/s

    x = 0.0
    for _ in range(30):
        x += vx * dt
        kf.predict(dt)
        kf.correct((x, 0.0))

    # Record state, then simulate 5 dropped frames.
    x_at_gap_start, _ = kf.position
    vx_est, _ = kf.velocity
    assert vx_est == pytest.approx(vx, rel=0.1)

    for _ in range(5):
        kf.predict(dt)

    predicted_x, _ = kf.position
    expected_x = x_at_gap_start + vx_est * dt * 5
    assert predicted_x == pytest.approx(expected_x, rel=0.05)


def test_reset_clears_state():
    kf = KalmanFilter2D()
    kf.correct((50.0, 50.0))
    kf.predict(0.1)
    kf.reset()
    assert kf.position == (0.0, 0.0)
    assert kf.velocity == (0.0, 0.0)

    kf.correct((5.0, 5.0))
    assert kf.position == (5.0, 5.0)
