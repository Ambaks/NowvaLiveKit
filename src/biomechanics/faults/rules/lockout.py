"""
Lockout Fault Detection Rule

Detects incomplete joint extension at the top or bottom of a rep.
Used for OHP (full extension overhead), curl (full extension at bottom),
tricep extensions, etc.
"""

from collections import deque
from typing import Callable, Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType


class LockoutRule(FaultRule):
    """
    Rule for detecting incomplete lockout/extension.

    Tracks the joint value at the end of the rep and fires if the user
    didn't reach full extension (or full flexion, depending on ``at``).

    Args:
        joint_getter: Extracts the joint angle from JointAngles.
        threshold_deg: Maximum acceptable residual flexion at lockout.
                       E.g. 10° means elbow must be within 10° of full
                       extension to count as locked out.
        at: "top" — evaluate when rep ends (ascending→idle transition).
            "bottom" — evaluate at rep start of next rep.
            Default "top".
        fault_message: Custom cue string.
    """

    def __init__(
        self,
        joint_getter: Callable[[JointAngles], float],
        threshold_deg: float = 10.0,
        at: str = "top",
        fault_message: str = "Lock out fully",
    ):
        self._joint_getter = joint_getter
        self.threshold_deg = threshold_deg
        self._at = at
        self._fault_message = fault_message

        # Track extremes during rep
        self._min_in_rep: float = 360.0
        self._max_in_rep: float = 0.0
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.LOCKOUT

    def reset(self) -> None:
        self._min_in_rep = 360.0
        self._max_in_rep = 0.0
        self._in_rep_prev = False

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        value = self._joint_getter(angles)

        if in_rep:
            self._min_in_rep = min(self._min_in_rep, value)
            self._max_in_rep = max(self._max_in_rep, value)
            self._in_rep_prev = True
            return None

        # Rep just ended — evaluate
        if self._in_rep_prev and self._evaluated_rep != rep_number:
            self._in_rep_prev = False
            self._evaluated_rep = rep_number

            if self._at == "top":
                # At lockout the joint should be near 0° (fully extended).
                # Use the minimum value seen in the rep as the "lockout attempt".
                residual = self._min_in_rep
            else:
                # "bottom" lockout: at the start of the rep the joint should
                # be near 0° (e.g. curl bottom = fully extended).
                # First frame of the rep captured the starting position.
                residual = self._min_in_rep

            self._min_in_rep = 360.0
            self._max_in_rep = 0.0

            if residual <= self.threshold_deg:
                return None  # Good lockout

            excess = residual - self.threshold_deg

            if excess > 25.0:
                severity = FaultSeverity.MODERATE
                score = 2.0
            else:
                severity = FaultSeverity.MILD
                score = 0.5 + 1.5 * (excess / 25.0)

            return self._create_fault_event(
                severity=severity,
                severity_score=score,
                message=self._fault_message,
                angles=angles,
                rep_number=rep_number,
                details={
                    "residual_flexion": residual,
                    "threshold": self.threshold_deg,
                    "at": self._at,
                },
            )

        return None
