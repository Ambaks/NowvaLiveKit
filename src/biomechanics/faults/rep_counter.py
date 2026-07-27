"""
Rep Counter with Robust Phase Detection

Tracks rep boundaries using knee angle position and velocity.
Uses 4-state machine: IDLE → DESCENDING → BOTTOM → ASCENDING

Key robustness features:
- Uses knee angle as primary signal (more stable than hip)
- Velocity sign determines direction with hysteresis
- Minimum dwell time in each state prevents noise-induced flipping
- Angle-based bottom detection (max knee flexion) with velocity confirmation
"""

from collections import deque
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
import time

from biomechanics.utils.types import JointAngles, FaultEvent, RepData


class RepState(str, Enum):
    """State machine states for rep detection."""
    IDLE = "idle"              # Standing, not in a rep
    DESCENDING = "descending"  # Moving down (positive velocity, angle increasing)
    BOTTOM = "bottom"          # At bottom, velocity near zero or reversing
    ASCENDING = "ascending"    # Moving up (negative velocity, angle decreasing)


@dataclass
class RepCounterConfig:
    """Configuration for rep detection."""
    # Angle thresholds (degrees)
    entry_knee_angle: float = 30.0      # Knee flexion to start tracking rep
    exit_knee_angle: float = 25.0       # Knee flexion to complete rep (hysteresis)
    min_depth_knee_angle: float = 95.0  # Knee must reach this for valid rep

    # Hip-based entry (backup)
    entry_hip_angle: float = 20.0       # Hip flexion threshold for entry
    exit_hip_angle: float = 18.0        # Hip flexion threshold for exit

    # Velocity thresholds (deg/sec)
    # Positive = descending (angle increasing), Negative = ascending (angle decreasing)
    descending_velocity: float = 10.0   # Min velocity to confirm descending
    ascending_velocity: float = -10.0   # Max velocity to confirm ascending (negative)
    stopped_velocity: float = 8.0       # Abs velocity below this = stopped

    # Minimum frames in each state (prevents noise flipping)
    min_frames_descending: int = 2      # ~66ms at 30fps
    min_frames_bottom: int = 2          # ~66ms at 30fps
    min_frames_ascending: int = 2       # ~66ms at 30fps

    # Rep validation
    min_rep_duration_frames: int = 15   # ~0.5 sec at 30fps

    # Bottom detection
    bottom_angle_tolerance: float = 5.0  # Degrees from max to consider "at bottom"


class RepCounter:
    """
    Counts reps using a 4-state machine with robust phase detection.

    State transitions:
    - IDLE -> DESCENDING:
        * knee_angle > entry_threshold AND velocity > descending_velocity

    - DESCENDING -> BOTTOM:
        * velocity drops below stopped_velocity (direction reversal)
        * OR knee_angle within tolerance of max depth AND velocity < descending_velocity

    - BOTTOM -> ASCENDING:
        * velocity < ascending_velocity (moving up)
        * AND minimum dwell time in BOTTOM

    - ASCENDING -> IDLE:
        * knee_angle < exit_threshold
        * Validates: depth requirement, minimum duration
    """

    def __init__(self, config: Optional[RepCounterConfig] = None):
        self.config = config or RepCounterConfig()
        self.state = RepState.IDLE
        self.rep_count = 0

        # Current rep tracking
        self._rep_start_time: float = 0.0
        self._rep_start_frame: int = 0
        self._frames_in_rep: int = 0
        self._max_depth_angle: float = 0.0
        self._min_depth_angle: float = 180.0
        self._current_faults: List[FaultEvent] = []

        # State dwell tracking
        self._frames_in_state: int = 0
        self._prev_state: RepState = RepState.IDLE

        # For timing analysis
        self._bottom_frame: int = 0
        self._bottom_time: float = 0.0

        # History for asymmetry averaging
        self._knee_asymmetry_sum: float = 0.0
        self._hip_asymmetry_sum: float = 0.0
        self._angle_samples: int = 0

        # Velocity history for smoothing state decisions
        self._velocity_window: int = 3  # frames
        self._velocity_history: deque[float] = deque(maxlen=self._velocity_window)

        self._assessment_mode: bool = False

    def set_assessment_mode(self, enabled: bool) -> None:
        """Bypass the min-depth validation so any completed rep counts."""
        self._assessment_mode = enabled

    def reset(self) -> None:
        """Reset the counter to initial state."""
        self.state = RepState.IDLE
        self.rep_count = 0
        self._reset_rep_tracking()
        self._frames_in_state = 0
        self._velocity_history.clear()

    def _reset_rep_tracking(self) -> None:
        """Reset tracking variables for a new rep."""
        self._rep_start_time = 0.0
        self._rep_start_frame = 0
        self._frames_in_rep = 0
        self._max_depth_angle = 0.0
        self._min_depth_angle = 180.0
        self._current_faults = []
        self._bottom_frame = 0
        self._bottom_time = 0.0
        self._knee_asymmetry_sum = 0.0
        self._hip_asymmetry_sum = 0.0
        self._angle_samples = 0

    def _get_hip_flexion(self, angles: JointAngles) -> float:
        """Get average hip flexion angle."""
        return (angles.hip_flexion_l + angles.hip_flexion_r) / 2

    def _get_smoothed_velocity(self, velocity: float) -> float:
        """Get smoothed velocity using short history."""
        self._velocity_history.append(velocity)  # deque auto-evicts past maxlen
        return sum(self._velocity_history) / len(self._velocity_history)

    @property
    def in_rep(self) -> bool:
        """Return True if currently in a rep (any active state)."""
        return self.state in (RepState.DESCENDING, RepState.BOTTOM, RepState.ASCENDING)

    @property
    def phase(self) -> str:
        """Return current phase name."""
        return self.state.value

    def add_fault(self, fault: FaultEvent) -> None:
        """Add a fault to the current rep's fault list."""
        self._current_faults.append(fault)

    def _start_rep(self, angles: JointAngles) -> None:
        """Initialize tracking for a new rep."""
        current_time = angles.timestamp if angles.timestamp is not None else time.time()
        knee_flexion = angles.avg_knee_flexion

        self._rep_start_time = current_time
        self._rep_start_frame = angles.frame_index
        self._frames_in_rep = 1
        self._max_depth_angle = knee_flexion
        self._min_depth_angle = knee_flexion
        self._knee_asymmetry_sum = angles.knee_asymmetry
        self._hip_asymmetry_sum = angles.hip_asymmetry
        self._angle_samples = 1

    def _track_depth(self, angles: JointAngles) -> None:
        """Track depth and asymmetry during rep."""
        knee_flexion = angles.avg_knee_flexion
        current_time = angles.timestamp if angles.timestamp is not None else time.time()

        self._frames_in_rep += 1

        if knee_flexion > self._max_depth_angle:
            self._max_depth_angle = knee_flexion
            self._bottom_frame = angles.frame_index
            self._bottom_time = current_time

        if knee_flexion < self._min_depth_angle:
            self._min_depth_angle = knee_flexion

        self._knee_asymmetry_sum += angles.knee_asymmetry
        self._hip_asymmetry_sum += angles.hip_asymmetry
        self._angle_samples += 1

    def _change_state(self, new_state: RepState) -> None:
        """Change state and reset dwell counter."""
        self._prev_state = self.state
        self.state = new_state
        self._frames_in_state = 0

    def update(
        self,
        angles: JointAngles,
        derivatives=None,
        faults: Optional[List[FaultEvent]] = None,
    ) -> Tuple[Optional[RepData], Optional[str]]:
        """
        Update rep counter with new joint angles and derivatives.

        Args:
            angles: Current frame's joint angles
            derivatives: AngleDerivatives with velocity/acceleration (optional)
            faults: List of faults detected this frame (optional)

        Returns:
            Tuple of (RepData if rep completed, feedback message if any)
            feedback can be: "go_deeper" if rep didn't hit depth
        """
        if faults:
            self._current_faults.extend(faults)

        knee_angle = angles.avg_knee_flexion
        hip_angle = self._get_hip_flexion(angles)

        # Get velocity (default to position-based if no derivatives)
        if derivatives is not None:
            raw_velocity = derivatives.avg_knee_velocity
            velocity = self._get_smoothed_velocity(raw_velocity)
        else:
            velocity = 0.0

        # Track state dwell time
        self._frames_in_state += 1

        completed_rep: Optional[RepData] = None
        feedback: Optional[str] = None

        # ===== STATE MACHINE =====

        if self.state == RepState.IDLE:
            # Entry condition: knee angle above threshold AND moving down (positive velocity)
            # Or fallback: hip angle threshold if no derivatives
            entry_by_position = knee_angle >= self.config.entry_knee_angle
            entry_by_hip = hip_angle >= self.config.entry_hip_angle

            if derivatives is not None:
                # With derivatives: require positive velocity (descending)
                descending = velocity > self.config.descending_velocity
                if (entry_by_position or entry_by_hip) and descending:
                    self._change_state(RepState.DESCENDING)
                    self._start_rep(angles)
            else:
                # Without derivatives: use position only
                if entry_by_position or entry_by_hip:
                    self._change_state(RepState.DESCENDING)
                    self._start_rep(angles)

        elif self.state == RepState.DESCENDING:
            self._track_depth(angles)

            # Transition to BOTTOM when:
            # 1. Velocity drops (no longer descending fast)
            # 2. AND we've been descending for minimum frames
            if derivatives is not None:
                stopped = abs(velocity) < self.config.stopped_velocity
                reversing = velocity < 0  # Starting to go back up
                at_depth = knee_angle >= (self._max_depth_angle - self.config.bottom_angle_tolerance)

                if self._frames_in_state >= self.config.min_frames_descending:
                    if stopped or (reversing and at_depth):
                        self._change_state(RepState.BOTTOM)
                        self._bottom_time = angles.timestamp if angles.timestamp is not None else time.time()
            else:
                # Without derivatives: position-based - angle started decreasing
                if knee_angle < self._max_depth_angle - self.config.bottom_angle_tolerance:
                    self._change_state(RepState.ASCENDING)

        elif self.state == RepState.BOTTOM:
            self._track_depth(angles)

            # Transition to ASCENDING when velocity becomes clearly negative
            if derivatives is not None:
                ascending = velocity < self.config.ascending_velocity

                if self._frames_in_state >= self.config.min_frames_bottom:
                    if ascending:
                        self._change_state(RepState.ASCENDING)
            else:
                # Without derivatives: immediate transition
                self._change_state(RepState.ASCENDING)

        elif self.state == RepState.ASCENDING:
            self._track_depth(angles)

            # Rep completion: knee angle drops below exit threshold
            exit_condition = knee_angle < self.config.exit_knee_angle

            # Also check hip angle as backup
            exit_by_hip = hip_angle < self.config.exit_hip_angle

            if self._frames_in_state >= self.config.min_frames_ascending:
                if exit_condition or exit_by_hip:
                    # Validate rep
                    if self._frames_in_rep >= self.config.min_rep_duration_frames:
                        if self._assessment_mode or self._max_depth_angle >= self.config.min_depth_knee_angle:
                            self.rep_count += 1
                            completed_rep = self._create_rep_data(angles)
                        else:
                            feedback = "go_deeper"

                    self._change_state(RepState.IDLE)
                    self._reset_rep_tracking()
                    self._velocity_history.clear()

        return completed_rep, feedback

    def update_legacy(
        self,
        angles: JointAngles,
        faults: Optional[List[FaultEvent]] = None,
    ) -> Optional[RepData]:
        """
        Legacy update method for backward compatibility.
        Uses simple threshold-based detection without derivatives.
        """
        rep_data, _ = self.update(angles, derivatives=None, faults=faults)
        return rep_data

    def snapshot_rep_metrics(self) -> dict:
        """Return current in-progress rep metrics without mutating state.

        Used by the pipeline to enrich BiLSTM RepData with angle-based
        measurements that only the rule-based counter tracks.
        """
        avg_knee = (
            self._knee_asymmetry_sum / self._angle_samples
            if self._angle_samples > 0 else 0.0
        )
        avg_hip = (
            self._hip_asymmetry_sum / self._angle_samples
            if self._angle_samples > 0 else 0.0
        )
        now = time.time()
        return {
            "max_depth_angle": self._max_depth_angle,
            "min_depth_angle": self._min_depth_angle,
            "descent_time": (self._bottom_time - self._rep_start_time) if self._bottom_time > 0 else 0.0,
            "ascent_time": (now - self._bottom_time) if self._bottom_time > 0 else 0.0,
            "faults": self._current_faults.copy(),
            "avg_knee_asymmetry": avg_knee,
            "avg_hip_asymmetry": avg_hip,
            "in_rep": self.in_rep,
        }

    def clear_current_faults(self) -> None:
        """Clear accumulated faults after they've been consumed by BiLSTM."""
        self._current_faults.clear()

    def _create_rep_data(self, angles: JointAngles) -> RepData:
        """Create RepData for a completed rep."""
        end_time = angles.timestamp if angles.timestamp is not None else time.time()

        # Calculate descent and ascent times
        descent_time = self._bottom_time - self._rep_start_time if self._bottom_time > 0 else 0
        ascent_time = end_time - self._bottom_time if self._bottom_time > 0 else 0

        # Calculate average asymmetry
        avg_knee_asym = (
            self._knee_asymmetry_sum / self._angle_samples
            if self._angle_samples > 0 else 0.0
        )
        avg_hip_asym = (
            self._hip_asymmetry_sum / self._angle_samples
            if self._angle_samples > 0 else 0.0
        )

        return RepData(
            rep_number=self.rep_count,
            start_time=self._rep_start_time,
            end_time=end_time,
            start_frame=self._rep_start_frame,
            end_frame=angles.frame_index,
            max_depth_angle=self._max_depth_angle,
            min_depth_angle=self._min_depth_angle,
            descent_time=descent_time,
            ascent_time=ascent_time,
            faults=self._current_faults.copy(),
            avg_knee_asymmetry=avg_knee_asym,
            avg_hip_asymmetry=avg_hip_asym,
        )
