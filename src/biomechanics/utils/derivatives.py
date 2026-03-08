"""
Derivative Computation for Joint Angles

Computes velocity (first derivative) and acceleration (second derivative)
of joint angles for cycle detection and tempo analysis.

Velocity = dθ/dt (degrees per second)
Acceleration = dv/dt (degrees per second squared)
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict

from biomechanics.utils.filters import ExponentialMovingAverage


@dataclass
class AngleDerivatives:
    """
    Velocity and acceleration for key joint angles.

    All velocities are in degrees/second.
    All accelerations are in degrees/second².

    Sign convention:
    - Positive velocity = angle increasing (flexion/bending)
    - Negative velocity = angle decreasing (extension/straightening)
    """

    # Knee derivatives
    knee_velocity_l: float = 0.0
    knee_velocity_r: float = 0.0
    knee_acceleration_l: float = 0.0
    knee_acceleration_r: float = 0.0

    # Hip derivatives
    hip_velocity_l: float = 0.0
    hip_velocity_r: float = 0.0
    hip_acceleration_l: float = 0.0
    hip_acceleration_r: float = 0.0

    # Timestamp
    timestamp: float = 0.0

    @property
    def avg_knee_velocity(self) -> float:
        """Average knee flexion velocity (deg/sec)."""
        return (self.knee_velocity_l + self.knee_velocity_r) / 2

    @property
    def avg_knee_acceleration(self) -> float:
        """Average knee flexion acceleration (deg/sec²)."""
        return (self.knee_acceleration_l + self.knee_acceleration_r) / 2

    @property
    def avg_hip_velocity(self) -> float:
        """Average hip flexion velocity (deg/sec)."""
        return (self.hip_velocity_l + self.hip_velocity_r) / 2

    @property
    def avg_hip_acceleration(self) -> float:
        """Average hip flexion acceleration (deg/sec²)."""
        return (self.hip_acceleration_l + self.hip_acceleration_r) / 2


class DerivativeTracker:
    """
    Computes smoothed velocity and acceleration from angle timeseries.

    Uses exponential moving average to smooth derivatives and reduce noise.
    Tracks both first derivative (velocity) and second derivative (acceleration).

    Usage:
        tracker = DerivativeTracker(smoothing_alpha=0.3)
        derivatives = tracker.update(joint_angles)
        print(f"Knee velocity: {derivatives.avg_knee_velocity} deg/sec")
    """

    def __init__(self, smoothing_alpha: float = 0.3):
        """
        Initialize derivative tracker.

        Args:
            smoothing_alpha: EMA smoothing factor (0-1).
                             Higher = less smoothing, more responsive.
                             Lower = more smoothing, less noise.
                             0.3 is good for 30fps pose data.
        """
        self.smoothing_alpha = smoothing_alpha

        # Previous frame data
        self._prev_angles = None
        self._prev_velocities: Optional[AngleDerivatives] = None
        self._prev_timestamp: Optional[float] = None

        # Smoothing filters for each velocity
        self._velocity_filters: Dict[str, ExponentialMovingAverage] = {
            'knee_l': ExponentialMovingAverage(alpha=smoothing_alpha),
            'knee_r': ExponentialMovingAverage(alpha=smoothing_alpha),
            'hip_l': ExponentialMovingAverage(alpha=smoothing_alpha),
            'hip_r': ExponentialMovingAverage(alpha=smoothing_alpha),
        }

        # Smoothing filters for each acceleration
        self._accel_filters: Dict[str, ExponentialMovingAverage] = {
            'knee_l': ExponentialMovingAverage(alpha=smoothing_alpha),
            'knee_r': ExponentialMovingAverage(alpha=smoothing_alpha),
            'hip_l': ExponentialMovingAverage(alpha=smoothing_alpha),
            'hip_r': ExponentialMovingAverage(alpha=smoothing_alpha),
        }

    def update(self, angles) -> AngleDerivatives:
        """
        Compute derivatives from new angle frame.

        Args:
            angles: JointAngles object with current angle values

        Returns:
            AngleDerivatives with smoothed velocity and acceleration
        """
        current_time = angles.timestamp if angles.timestamp is not None else time.time()

        # First frame - no derivatives yet
        if self._prev_angles is None:
            self._prev_angles = angles
            self._prev_timestamp = current_time
            self._prev_velocities = AngleDerivatives(timestamp=current_time)
            return AngleDerivatives(timestamp=current_time)

        # Compute time delta
        dt = current_time - self._prev_timestamp
        if dt <= 0:
            dt = 1e-6  # Prevent division by zero

        # Compute raw velocities (dθ/dt)
        raw_knee_vel_l = (angles.knee_flexion_l - self._prev_angles.knee_flexion_l) / dt
        raw_knee_vel_r = (angles.knee_flexion_r - self._prev_angles.knee_flexion_r) / dt
        raw_hip_vel_l = (angles.hip_flexion_l - self._prev_angles.hip_flexion_l) / dt
        raw_hip_vel_r = (angles.hip_flexion_r - self._prev_angles.hip_flexion_r) / dt

        # Smooth velocities
        knee_vel_l = self._velocity_filters['knee_l'].filter(raw_knee_vel_l)
        knee_vel_r = self._velocity_filters['knee_r'].filter(raw_knee_vel_r)
        hip_vel_l = self._velocity_filters['hip_l'].filter(raw_hip_vel_l)
        hip_vel_r = self._velocity_filters['hip_r'].filter(raw_hip_vel_r)

        # Compute raw accelerations (dv/dt) from previous velocities
        if self._prev_velocities is not None:
            raw_knee_accel_l = (knee_vel_l - self._prev_velocities.knee_velocity_l) / dt
            raw_knee_accel_r = (knee_vel_r - self._prev_velocities.knee_velocity_r) / dt
            raw_hip_accel_l = (hip_vel_l - self._prev_velocities.hip_velocity_l) / dt
            raw_hip_accel_r = (hip_vel_r - self._prev_velocities.hip_velocity_r) / dt
        else:
            raw_knee_accel_l = raw_knee_accel_r = 0.0
            raw_hip_accel_l = raw_hip_accel_r = 0.0

        # Smooth accelerations
        knee_accel_l = self._accel_filters['knee_l'].filter(raw_knee_accel_l)
        knee_accel_r = self._accel_filters['knee_r'].filter(raw_knee_accel_r)
        hip_accel_l = self._accel_filters['hip_l'].filter(raw_hip_accel_l)
        hip_accel_r = self._accel_filters['hip_r'].filter(raw_hip_accel_r)

        # Create result
        derivatives = AngleDerivatives(
            knee_velocity_l=knee_vel_l,
            knee_velocity_r=knee_vel_r,
            knee_acceleration_l=knee_accel_l,
            knee_acceleration_r=knee_accel_r,
            hip_velocity_l=hip_vel_l,
            hip_velocity_r=hip_vel_r,
            hip_acceleration_l=hip_accel_l,
            hip_acceleration_r=hip_accel_r,
            timestamp=current_time,
        )

        # Store for next iteration
        self._prev_angles = angles
        self._prev_timestamp = current_time
        self._prev_velocities = derivatives

        return derivatives

    def reset(self):
        """Reset tracker state."""
        self._prev_angles = None
        self._prev_velocities = None
        self._prev_timestamp = None

        for f in self._velocity_filters.values():
            f.reset()
        for f in self._accel_filters.values():
            f.reset()
