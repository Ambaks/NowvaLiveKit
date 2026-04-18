"""
Range of Motion Fault Detection Rule

Generalized depth/ROM rule that tracks a metric during the rep
and evaluates at rep completion. Works for any exercise by
accepting a metric getter and direction.
"""

from collections import deque
from typing import Callable, Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, FAULT_MESSAGES


class RangeOfMotionRule(FaultRule):
    """
    Generalized range-of-motion rule.

    Tracks the peak value of a metric during the rep and evaluates
    at rep completion. Supports both "max" direction (e.g. knee flexion
    where higher = deeper) and "min" direction (e.g. elbow extension
    where lower = more extended).

    Fires at rep completion with severity based on how far the user
    got relative to the target.

    Args:
        metric_getter: Callable that extracts the metric from JointAngles.
        target_threshold: The "full ROM" value — at or beyond this, no fault.
        min_threshold: Below this, fault is MODERATE (clearly insufficient).
        direction: "max" if the metric increases at full ROM (squat knee
                   flexion, curl elbow flexion). "min" if the metric
                   decreases at full ROM (OHP elbow extension).
        metric_name: Human-readable name for logs/details.
    """

    def __init__(
        self,
        metric_getter: Callable[[JointAngles], float],
        target_threshold: float = 90.0,
        min_threshold: float = 60.0,
        direction: str = "max",
        metric_name: str = "ROM",
    ):
        self._metric_getter = metric_getter
        self.target_threshold = target_threshold
        self.min_threshold = min_threshold
        self._direction = direction
        self._metric_name = metric_name

        # Track peak during rep
        self._peak_value: float = 0.0 if direction == "max" else 360.0
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.RANGE_OF_MOTION

    def reset(self) -> None:
        self._peak_value = 0.0 if self._direction == "max" else 360.0
        self._in_rep_prev = False

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Track peak metric during rep; evaluate when rep ends.
        """
        value = self._metric_getter(angles)

        if in_rep:
            if self._direction == "max":
                self._peak_value = max(self._peak_value, value)
            else:
                self._peak_value = min(self._peak_value, value)
            self._in_rep_prev = True
            return None

        # Rep just ended
        if self._in_rep_prev and self._evaluated_rep != rep_number:
            self._in_rep_prev = False
            self._evaluated_rep = rep_number
            peak = self._peak_value
            self._peak_value = 0.0 if self._direction == "max" else 360.0

            return self._evaluate_peak(peak, angles, rep_number)

        return None

    def evaluate_max_depth(
        self,
        max_knee_flexion: float,
        angles: JointAngles,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """Compat shim so RuleEngine.evaluate_rep_complete() works."""
        return self._evaluate_peak(max_knee_flexion, angles, rep_number)

    def _evaluate_peak(
        self,
        peak: float,
        angles: JointAngles,
        rep_number: int,
    ) -> Optional[FaultEvent]:
        """Evaluate the peak metric value against thresholds."""
        if self._direction == "max":
            # Higher is better — fault if peak didn't reach target
            if peak >= self.target_threshold:
                return None  # Full ROM achieved
            if peak < self.min_threshold:
                severity = FaultSeverity.MODERATE
                score = 2.0
                message = f"Insufficient {self._metric_name} — go deeper"
            else:
                severity = FaultSeverity.MILD
                score = 1.0
                message = f"Partial {self._metric_name} — push a bit further"
        else:
            # Lower is better (e.g. extension) — fault if peak too high
            if peak <= self.target_threshold:
                return None
            if peak > self.min_threshold:
                severity = FaultSeverity.MODERATE
                score = 2.0
                message = f"Insufficient {self._metric_name} — extend further"
            else:
                severity = FaultSeverity.MILD
                score = 1.0
                message = f"Partial {self._metric_name} — a bit more extension"

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "peak_value": peak,
                "target": self.target_threshold,
                "min_threshold": self.min_threshold,
                "metric": self._metric_name,
                "direction": self._direction,
            },
        )
