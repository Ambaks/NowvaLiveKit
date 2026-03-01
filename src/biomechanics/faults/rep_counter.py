"""
Rep Counter with State Machine

Tracks rep boundaries using hip flexion angle transitions.
Uses IDLE/IN_REP state machine with minimum duration filtering.
"""

from enum import Enum
from typing import Optional, List
from dataclasses import dataclass, field
import time

from biomechanics.utils.types import JointAngles, FaultEvent, RepData


class RepState(str, Enum):
    """State machine states for rep detection."""
    IDLE = "idle"       # Standing, not in a rep
    IN_REP = "in_rep"   # Currently performing a rep


@dataclass
class RepCounterConfig:
    """Configuration for rep detection."""
    entry_threshold: float = 30.0       # Hip flexion angle to enter rep (degrees)
    exit_threshold: float = 25.0        # Hip flexion angle to exit rep (degrees)
    min_rep_duration_frames: int = 20   # Minimum frames for valid rep
    use_knee_flexion: bool = False      # If True, use knee flexion instead of hip


class RepCounter:
    """
    Counts reps using a state machine based on hip/knee flexion.

    State transitions:
    - IDLE -> IN_REP: When avg hip flexion crosses entry_threshold (descending)
    - IN_REP -> IDLE: When avg hip flexion drops below exit_threshold (ascending)
                      AND minimum rep duration has elapsed

    On rep completion, returns RepData with:
    - max_depth_angle: Maximum knee flexion achieved during rep
    - faults: List of faults detected during rep
    - timing data
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

        # For timing analysis
        self._bottom_frame: int = 0
        self._bottom_time: float = 0.0

        # History for asymmetry averaging
        self._knee_asymmetry_sum: float = 0.0
        self._hip_asymmetry_sum: float = 0.0
        self._angle_samples: int = 0

    def reset(self) -> None:
        """Reset the counter to initial state."""
        self.state = RepState.IDLE
        self.rep_count = 0
        self._reset_rep_tracking()

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

    def _get_flexion_angle(self, angles: JointAngles) -> float:
        """Get the primary flexion angle for rep detection."""
        if self.config.use_knee_flexion:
            return angles.avg_knee_flexion
        else:
            return (angles.hip_flexion_l + angles.hip_flexion_r) / 2

    @property
    def in_rep(self) -> bool:
        """Return True if currently in a rep."""
        return self.state == RepState.IN_REP

    def add_fault(self, fault: FaultEvent) -> None:
        """Add a fault to the current rep's fault list."""
        self._current_faults.append(fault)

    def update(
        self,
        angles: JointAngles,
        faults: Optional[List[FaultEvent]] = None,
    ) -> Optional[RepData]:
        """
        Update rep counter with new joint angles.

        Args:
            angles: Current frame's joint angles
            faults: List of faults detected this frame (optional)

        Returns:
            RepData if a rep just completed, None otherwise
        """
        if faults:
            self._current_faults.extend(faults)

        flexion = self._get_flexion_angle(angles)
        knee_flexion = angles.avg_knee_flexion
        completed_rep: Optional[RepData] = None

        if self.state == RepState.IDLE:
            # Check for rep entry (flexion increasing above threshold)
            if flexion >= self.config.entry_threshold:
                self.state = RepState.IN_REP
                self._rep_start_time = angles.timestamp if angles.timestamp is not None else time.time()
                self._rep_start_frame = angles.frame_index
                self._frames_in_rep = 1
                self._max_depth_angle = knee_flexion
                self._min_depth_angle = knee_flexion
                self._knee_asymmetry_sum = angles.knee_asymmetry
                self._hip_asymmetry_sum = angles.hip_asymmetry
                self._angle_samples = 1

        elif self.state == RepState.IN_REP:
            self._frames_in_rep += 1

            # Track depth
            if knee_flexion > self._max_depth_angle:
                self._max_depth_angle = knee_flexion
                self._bottom_frame = angles.frame_index
                self._bottom_time = angles.timestamp if angles.timestamp is not None else time.time()

            if knee_flexion < self._min_depth_angle:
                self._min_depth_angle = knee_flexion

            # Track asymmetry
            self._knee_asymmetry_sum += angles.knee_asymmetry
            self._hip_asymmetry_sum += angles.hip_asymmetry
            self._angle_samples += 1

            # Check for rep exit (flexion dropping below threshold)
            if flexion < self.config.exit_threshold:
                # Only count if minimum duration met
                if self._frames_in_rep >= self.config.min_rep_duration_frames:
                    self.rep_count += 1
                    completed_rep = self._create_rep_data(angles)

                # Reset regardless
                self.state = RepState.IDLE
                self._reset_rep_tracking()

        return completed_rep

    def _create_rep_data(self, angles: JointAngles) -> RepData:
        """Create RepData for a completed rep."""
        end_time = angles.timestamp if angles.timestamp is not None else time.time()

        # Calculate descent and ascent times
        descent_time = self._bottom_time - self._rep_start_time
        ascent_time = end_time - self._bottom_time

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
