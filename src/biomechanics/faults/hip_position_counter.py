"""
Signal-Based Rep Counter — Causal Real-Time 4-State Machine

Counts reps using a configurable signal and its causal velocity in a
4-state machine that operates frame-by-frame without any look-ahead.

The signal is exercise-specific and provided by the active ExerciseProfile:
    - Squats:    hip vertical position (cm, relative to ankle)
    - Deadlifts: trunk flexion angle
    - Curls:     elbow flexion angle
    - OHP:       wrist Y position relative to shoulder

State machine:
    IDLE  →  DESCENDING  →  BOTTOM  →  ASCENDING  →  IDLE
"""

from enum import Enum
from typing import Callable, Dict, Optional, List, Tuple
import time

from biomechanics.config import HipPositionCounterConfig
from biomechanics.utils.types import JointAngles, FaultEvent, RepData
from biomechanics.utils.filters import OneEuroFilter, ExponentialMovingAverage


class SignalRepState(str, Enum):
    """State machine states."""
    IDLE = "idle"
    DESCENDING = "descending"
    BOTTOM = "bottom"
    ASCENDING = "ascending"

# Backward compat alias
HipPositionState = SignalRepState


class SignalRepCounter:
    """
    Real-time rep counter driven by a configurable signal.

    The signal is provided per-frame by the active ExerciseProfile's
    get_rep_signal() method. Depth and asymmetry metrics are extracted
    via pluggable callables from the profile.

    Exposes the same public interface (in_rep, phase, rep_count, update,
    snapshot_rep_metrics, etc.) so the pipeline, dashboard, and BiLSTM
    enrichment code work without changes.
    """

    def __init__(
        self,
        config: Optional[HipPositionCounterConfig] = None,
        depth_metric_fn: Optional[Callable[[JointAngles], float]] = None,
        asymmetry_fn: Optional[Callable[[JointAngles], Dict[str, float]]] = None,
    ):
        self.config = config or HipPositionCounterConfig()
        self.state = SignalRepState.IDLE
        self.rep_count = 0

        # Pluggable metric extractors (default: squat knee-based)
        self._depth_metric_fn = depth_metric_fn or (lambda a: a.avg_knee_flexion)
        self._asymmetry_fn = asymmetry_fn or (
            lambda a: {"knee": a.knee_asymmetry, "hip": a.hip_asymmetry}
        )

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

        # ---- current-rep signal tracking ----
        self._max_position_in_rep: float = 0.0  # peak signal = rep bottom

        # ---- current-rep metric tracking (from JointAngles) ----
        self._rep_start_time: float = 0.0
        self._rep_start_frame: int = 0
        self._frames_in_rep: int = 0
        self._max_depth_angle: float = 0.0
        self._min_depth_angle: float = 180.0
        self._bottom_time: float = 0.0
        self._current_faults: List[FaultEvent] = []
        self._asymmetry_sums: Dict[str, float] = {}
        self._angle_samples: int = 0

        # ---- assessment mode ----
        self._assessment_mode: bool = False

    # ------------------------------------------------------------------
    # Public properties (same interface as RepCounter)
    # ------------------------------------------------------------------

    @property
    def in_rep(self) -> bool:
        return self.state in (
            SignalRepState.DESCENDING,
            SignalRepState.BOTTOM,
            SignalRepState.ASCENDING,
        )

    @property
    def phase(self) -> str:
        return self.state.value

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_assessment_mode(self, enabled: bool) -> None:
        """Bypass the min-depth validation so any completed rep counts."""
        self._assessment_mode = enabled

    def reset(self) -> None:
        self.state = SignalRepState.IDLE
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
        avg_asymmetry = {}
        for key, total in self._asymmetry_sums.items():
            avg_asymmetry[key] = total / self._angle_samples if self._angle_samples > 0 else 0.0
        now = time.time()
        return {
            "max_depth_angle": self._max_depth_angle,
            "min_depth_angle": self._min_depth_angle,
            "descent_time": (self._bottom_time - self._rep_start_time)
                if self._bottom_time > 0 else 0.0,
            "ascent_time": (now - self._bottom_time)
                if self._bottom_time > 0 else 0.0,
            "faults": self._current_faults.copy(),
            "asymmetry": avg_asymmetry,
            # Backward compat
            "avg_knee_asymmetry": avg_asymmetry.get("knee", 0.0),
            "avg_hip_asymmetry": avg_asymmetry.get("hip", 0.0),
            "in_rep": self.in_rep,
        }

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(
        self,
        signal_value: float = None,
        timestamp: float = None,
        angles: Optional[JointAngles] = None,
        faults: Optional[List[FaultEvent]] = None,
        *,
        hip_position_cm: float = None,
    ) -> Tuple[Optional[RepData], Optional[str]]:
        """
        Process one frame.

        Args:
            signal_value: Rep counting signal from the exercise profile.
                For squats this is (hip_mid_y - ankle_mid_y) * 100.
                Other exercises feed different signals (trunk flexion, etc.).
            timestamp: Wall-clock time for this frame.
            angles: JointAngles for metric tracking (knee depth, asymmetry).
            faults: Faults detected this frame.
            hip_position_cm: Deprecated alias for signal_value (backward compat).

        Returns:
            (RepData, None) when a rep completes.
            (None, "go_deeper") when a rep ends but depth was insufficient.
            (None, None) otherwise.
        """
        # Backward compatibility: accept hip_position_cm as alias
        if signal_value is None and hip_position_cm is not None:
            signal_value = hip_position_cm
        elif signal_value is None:
            raise ValueError("signal_value (or hip_position_cm) is required")
        if faults:
            self._current_faults.extend(faults)

        # ---- smooth position & compute causal velocity ----
        smoothed_pos = self._pos_filter.filter(signal_value, timestamp)

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

        if self.state == SignalRepState.IDLE:
            # Update standing baseline while idle
            self._standing_baseline = self._baseline_ema.filter(smoothed_pos)

            if velocity > self.config.entry_vel_threshold:
                self._change_state(SignalRepState.DESCENDING)
                self._start_rep(smoothed_pos, timestamp, angles)

        elif self.state == SignalRepState.DESCENDING:
            # Track peak position (squat bottom = local max)
            if smoothed_pos > self._max_position_in_rep:
                self._max_position_in_rep = smoothed_pos
                self._bottom_time = timestamp

            if self._frames_in_state >= self.config.min_frames_descending:
                if abs(velocity) < self.config.bottom_vel_threshold:
                    self._change_state(SignalRepState.BOTTOM)

        elif self.state == SignalRepState.BOTTOM:
            # Still track depth in case bottom drifts deeper
            if smoothed_pos > self._max_position_in_rep:
                self._max_position_in_rep = smoothed_pos
                self._bottom_time = timestamp

            if self._frames_in_state >= self.config.min_frames_bottom:
                if velocity < -self.config.ascending_vel_threshold:
                    self._change_state(SignalRepState.ASCENDING)

        elif self.state == SignalRepState.ASCENDING:
            if self._frames_in_state >= self.config.min_frames_ascending:
                returned = smoothed_pos < self._standing_baseline + self.config.standing_return_cm
                if returned:
                    # Validate rep
                    depth = self._max_position_in_rep - self._standing_baseline
                    depth_ok = self._assessment_mode or depth >= self.config.min_depth_cm
                    if (
                        self._frames_in_rep >= self.config.min_rep_duration_frames
                        and depth_ok
                    ):
                        self.rep_count += 1
                        completed_rep = self._create_rep_data(timestamp, angles)
                    elif not depth_ok:
                        feedback = "go_deeper"

                    self._change_state(SignalRepState.IDLE)
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
        self._asymmetry_sums = {}
        self._angle_samples = 0

        if angles is not None:
            self._track_angles(angles)

    def _track_angles(self, angles: JointAngles) -> None:
        depth = self._depth_metric_fn(angles)

        if depth > self._max_depth_angle:
            self._max_depth_angle = depth

        if depth < self._min_depth_angle:
            self._min_depth_angle = depth

        asym = self._asymmetry_fn(angles)
        for key, val in asym.items():
            self._asymmetry_sums[key] = self._asymmetry_sums.get(key, 0.0) + val
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
        self._asymmetry_sums = {}
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
        avg_asymmetry = {}
        for key, total in self._asymmetry_sums.items():
            avg_asymmetry[key] = total / self._angle_samples if self._angle_samples > 0 else 0.0

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
            asymmetry=avg_asymmetry,
            # Backward compat
            avg_knee_asymmetry=avg_asymmetry.get("knee", 0.0),
            avg_hip_asymmetry=avg_asymmetry.get("hip", 0.0),
        )


# Backward compat alias — pipeline and other consumers may still import this name
HipPositionRepCounter = SignalRepCounter
