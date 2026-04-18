"""
Bilateral Asymmetry Fault Detection Rule

Compares left vs right joint angles to detect weight shifts
and imbalanced movement patterns. Parameterized with getter
lambdas so one class works for any joint pair.
"""

from collections import deque
from typing import Callable, Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, FAULT_MESSAGES


class SymmetryRule(FaultRule):
    """
    Rule for detecting bilateral asymmetry between any left/right joint pair.

    By default compares hip and knee flexion (squat behavior). Override
    ``left_getter`` / ``right_getter`` to compare elbows, wrists, etc.

    Severity thresholds:
    - Mild: 5-10° difference
    - Moderate: 10-15° difference
    - Severe: >15° difference
    """

    def __init__(
        self,
        left_getter: Optional[Callable[[JointAngles], float]] = None,
        right_getter: Optional[Callable[[JointAngles], float]] = None,
        joint_name: str = "knee",
        mild_threshold: float = 5.0,
        moderate_threshold: float = 10.0,
        severe_threshold: float = 15.0,
    ):
        # Primary joint pair (defaults to knee flexion for backward compat)
        self._left_getter = left_getter or (lambda a: a.knee_flexion_l)
        self._right_getter = right_getter or (lambda a: a.knee_flexion_r)
        self._joint_name = joint_name

        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        self._last_fault_frame: int = -30

    @property
    def fault_type(self) -> FaultType:
        return FaultType.BILATERAL_ASYMMETRY

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate bilateral symmetry.

        Only fires during reps to avoid false positives from
        asymmetric standing positions.
        """
        if not in_rep:
            return None

        # Cooldown between fault reports
        if angles.frame_index - self._last_fault_frame < 30:
            return None

        # Calculate asymmetry from the configured getter pair
        left_val = self._left_getter(angles)
        right_val = self._right_getter(angles)
        asymmetry = abs(left_val - right_val)

        if asymmetry < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            asymmetry,
            {
                "mild": self.mild_threshold,
                "moderate": self.moderate_threshold,
                "severe": self.severe_threshold,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        self._last_fault_frame = angles.frame_index

        heavier_side = "left" if left_val > right_val else "right"

        message_key = severity.value
        message = FAULT_MESSAGES[FaultType.BILATERAL_ASYMMETRY].get(
            message_key, "Uneven weight distribution"
        )

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "joint": self._joint_name,
                "asymmetry": asymmetry,
                "heavier_side": heavier_side,
            },
        )
