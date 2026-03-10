"""
Hip-Position Rep Counter — Causal Real-Time Version of the Post-Hoc Segmenter

Counts reps using hip vertical position (cm, relative to ankle) and its
causal velocity.  Uses the same signal and thresholds as the post-hoc
``rep_segmenter`` but in a 4-state machine that operates frame-by-frame
without any look-ahead.

Coordinate convention (same as segmenter):
    hip_position_cm = (hip_mid_y - ankle_mid_y) * 100
    More negative  → standing (hip far above ankle)
    Less negative  → squat bottom (hip close to ankle)

    Descent → velocity POSITIVE  (position increasing toward zero)
    Ascent  → velocity NEGATIVE  (position decreasing away from zero)

State machine:
    IDLE  →  DESCENDING  →  BOTTOM  →  ASCENDING  →  IDLE
"""

from enum import Enum
from typing import Optional, List, Tuple
import time

from biomechanics.config import HipPositionCounterConfig
from biomechanics.utils.types import JointAngles, FaultEvent, RepData
from biomechanics.utils.filters import OneEuroFilter, ExponentialMovingAverage


class HipPositionState(str, Enum):
    """State machine states — string values match RepState for compatibility."""
    IDLE = "idle"
    DESCENDING = "descending"
    BOTTOM = "bottom"
    ASCENDING = "ascending"


class HipPositionRepCounter:
    """
    Real-time rep counter driven by hip vertical position.

    Drop-in replacement for RepCounter — exposes the same public interface
    (in_rep, phase, rep_count, update, snapshot_rep_metrics, etc.) so the
    pipeline, dashboard, and BiLSTM enrichment code work without changes.
    """

    def __init__(self, config: Optional[HipPositionCounterConfig] = None):
        self.config = config or HipPositionCounterConfig()
        self.state = HipPositionState.IDLE
        self.rep_count = 0

        # ---- signal processing ----
        self._pos_filter = OneEuroFilter(
            min_cutoff=self.config.position_min_cutoff,
            beta=self.config.position_beta,
        )
        self._vel_ema = ExponentialMovingAverage(alpha=self.config.velocity_ema_alpha)
        self._prev_position: Optional[float] = None
        self._prev_timestamp: Optional[float] = None

        # ---- standing baseline ----
        self._standing_baseline: Optional[float] = None
        self._baseline_ema = ExponentialMovingAverage(alpha=0.15)

        # ---- state dwell tracking ----
        self._frames_in_state: int = 0

        # ---- current-rep hip tracking ----
        self._max_position_in_rep: float = 0.0  # peak (least-negative) = squat bottom

        # ---- current-rep metric tracking (from JointAngles) ----
        self._rep_start_time: float = 0.0
        self._rep_start_frame: int = 0
        self._frames_in_rep: int = 0
        self._max_depth_angle: float = 0.0
        self._min_depth_angle: float = 180.0
        self._bottom_time: float = 0.0
        self._current_faults: List[FaultEvent] = []
        self._knee_asymmetry_sum: float = 0.0
        self._hip_asymmetry_sum: float = 0.0
        self._angle_samples: int = 0

    # ------------------------------------------------------------------
    # Public properties (same interface as RepCounter)
    # ------------------------------------------------------------------

    @property
    def in_rep(self) -> bool:
        return self.state in (
            HipPositionState.DESCENDING,
            HipPositionState.BOTTOM,
            HipPositionState.ASCENDING,
        )

    @property
    def phase(self) -> str:
        return self.state.value

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.state = HipPositionState.IDLE
        self.rep_count = 0
        self._reset_rep_tracking()
        self._frames_in_state = 0
        self._pos_filter.reset()
        self._vel_ema.reset()
        self._baseline_ema.reset()
        self._prev_position = None
        self._prev_timestamp = None
        self._standing_baseline = None

    def add_fault(self, fault: FaultEvent) -> None:
        self._current_faults.append(fault)

    def clear_current_faults(self) -> None:
        self._current_faults.clear()

    def snapshot_rep_metrics(self) -> dict:
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
            "descent_time": (self._bottom_time - self._rep_start_time)
                if self._bottom_time > 0 else 0.0,
            "ascent_time": (now - self._bottom_time)
                if self._bottom_time > 0 else 0.0,
            "faults": self._current_faults.copy(),
            "avg_knee_asymmetry": avg_knee,
            "avg_hip_asymmetry": avg_hip,
            "in_rep": self.in_rep,
        }

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(
        self,
        hip_position_cm: float,
        timestamp: float,
        angles: Optional[JointAngles] = None,
        faults: Optional[List[FaultEvent]] = None,
    ) -> Tuple[Optional[RepData], Optional[str]]:
        """
        Process one frame.

        Args:
            hip_position_cm: (hip_mid_y - ankle_mid_y) * 100 from skeleton.
            timestamp: Wall-clock time for this frame.
            angles: JointAngles for metric tracking (knee depth, asymmetry).
            faults: Faults detected this frame.

        Returns:
            (RepData, None) when a rep completes.
            (None, "go_deeper") when a rep ends but depth was insufficient.
            (None, None) otherwise.
        """
        if faults:
            self._current_faults.extend(faults)

        # ---- smooth position & compute causal velocity ----
        smoothed_pos = self._pos_filter.filter(hip_position_cm, timestamp)

        velocity = 0.0
        if self._prev_position is not None and self._prev_timestamp is not None:
            dt = timestamp - self._prev_timestamp
            if dt > 0:
                raw_vel = (smoothed_pos - self._prev_position) / dt
                velocity = self._vel_ema.filter(raw_vel)

        self._prev_position = smoothed_pos
        self._prev_timestamp = timestamp

        # ---- initialise standing baseline from first frames ----
        if self._standing_baseline is None:
            self._standing_baseline = smoothed_pos
            self._baseline_ema.value = smoothed_pos

        # ---- track state dwell ----
        self._frames_in_state += 1

        # ---- track rep frame count and angle metrics ----
        if self.in_rep:
            self._frames_in_rep += 1
            if angles is not None:
                self._track_angles(angles)

        # ---- state machine ----
        completed_rep: Optional[RepData] = None
        feedback: Optional[str] = None

        if self.state == HipPositionState.IDLE:
            # Update standing baseline while idle
            self._standing_baseline = self._baseline_ema.filter(smoothed_pos)

            if velocity > self.config.entry_vel_threshold:
                self._change_state(HipPositionState.DESCENDING)
                self._start_rep(smoothed_pos, timestamp, angles)

        elif self.state == HipPositionState.DESCENDING:
            # Track peak position (squat bottom = local max)
            if smoothed_pos > self._max_position_in_rep:
                self._max_position_in_rep = smoothed_pos
                self._bottom_time = timestamp

            if self._frames_in_state >= self.config.min_frames_descending:
                if abs(velocity) < self.config.bottom_vel_threshold:
                    self._change_state(HipPositionState.BOTTOM)

        elif self.state == HipPositionState.BOTTOM:
            # Still track depth in case bottom drifts deeper
            if smoothed_pos > self._max_position_in_rep:
                self._max_position_in_rep = smoothed_pos
                self._bottom_time = timestamp

            if self._frames_in_state >= self.config.min_frames_bottom:
                if velocity < -self.config.ascending_vel_threshold:
                    self._change_state(HipPositionState.ASCENDING)

        elif self.state == HipPositionState.ASCENDING:
            if self._frames_in_state >= self.config.min_frames_ascending:
                returned = smoothed_pos < self._standing_baseline + self.config.standing_return_cm
                if returned:
                    # Validate rep
                    depth = self._max_position_in_rep - self._standing_baseline
                    if (
                        self._frames_in_rep >= self.config.min_rep_duration_frames
                        and depth >= self.config.min_depth_cm
                    ):
                        self.rep_count += 1
                        completed_rep = self._create_rep_data(timestamp, angles)
                    elif depth < self.config.min_depth_cm:
                        feedback = "go_deeper"

                    self._change_state(HipPositionState.IDLE)
                    self._reset_rep_tracking()

        return completed_rep, feedback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _change_state(self, new_state: HipPositionState) -> None:
        self.state = new_state
        self._frames_in_state = 0

    def _start_rep(
        self,
        position: float,
        timestamp: float,
        angles: Optional[JointAngles],
    ) -> None:
        self._rep_start_time = timestamp
        self._rep_start_frame = angles.frame_index if angles else 0
        self._frames_in_rep = 1
        self._max_position_in_rep = position
        self._max_depth_angle = 0.0
        self._min_depth_angle = 180.0
        self._bottom_time = 0.0
        self._current_faults = []
        self._knee_asymmetry_sum = 0.0
        self._hip_asymmetry_sum = 0.0
        self._angle_samples = 0

        if angles is not None:
            self._track_angles(angles)

    def _track_angles(self, angles: JointAngles) -> None:
        knee = angles.avg_knee_flexion

        if knee > self._max_depth_angle:
            self._max_depth_angle = knee

        if knee < self._min_depth_angle:
            self._min_depth_angle = knee

        self._knee_asymmetry_sum += angles.knee_asymmetry
        self._hip_asymmetry_sum += angles.hip_asymmetry
        self._angle_samples += 1

    def _reset_rep_tracking(self) -> None:
        self._rep_start_time = 0.0
        self._rep_start_frame = 0
        self._frames_in_rep = 0
        self._max_position_in_rep = 0.0
        self._max_depth_angle = 0.0
        self._min_depth_angle = 180.0
        self._bottom_time = 0.0
        self._current_faults = []
        self._knee_asymmetry_sum = 0.0
        self._hip_asymmetry_sum = 0.0
        self._angle_samples = 0

    def _create_rep_data(
        self, end_time: float, angles: Optional[JointAngles]
    ) -> RepData:
        descent_time = (
            (self._bottom_time - self._rep_start_time)
            if self._bottom_time > 0 else 0.0
        )
        ascent_time = (
            (end_time - self._bottom_time)
            if self._bottom_time > 0 else 0.0
        )
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
            end_frame=angles.frame_index if angles else 0,
            max_depth_angle=self._max_depth_angle,
            min_depth_angle=self._min_depth_angle,
            descent_time=descent_time,
            ascent_time=ascent_time,
            faults=self._current_faults.copy(),
            avg_knee_asymmetry=avg_knee_asym,
            avg_hip_asymmetry=avg_hip_asym,
        )
