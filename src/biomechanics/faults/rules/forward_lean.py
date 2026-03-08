"""
Forward Lean Fault Detection Rule

Evaluates trunk flexion angle during squats.
Excessive forward lean can indicate mobility issues or
compensatory patterns.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES


class ForwardLeanRule(FaultRule):
    """
    Rule for detecting excessive forward lean.

    Monitors trunk flexion angle during reps.
    Some forward lean is normal and necessary in squats,
    but excessive lean can indicate:
    - Poor ankle mobility
    - Weak posterior chain
    - Bar position issues

    Severity thresholds:
    - Mild: 35-45° trunk flexion
    - Moderate: 45-55° trunk flexion
    - Severe: >55° trunk flexion

    Note: These thresholds may need adjustment based on
    squat style (high bar vs low bar) and body proportions.
    """

    def __init__(
        self,
        mild_threshold: float = 35.0,
        moderate_threshold: float = 45.0,
        severe_threshold: float = 55.0,
    ):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        self._last_fault_frame: int = -150  # ~5s at 30fps — avoid spamming

    @property
    def fault_type(self) -> FaultType:
        return FaultType.FORWARD_LEAN

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate trunk flexion for excessive forward lean.

        Only fires during reps - standing position lean is not
        a fault.
        """
        if not in_rep:
            return None

        # Cooldown between fault reports
        if angles.frame_index - self._last_fault_frame < 150:
            return None

        trunk_flexion = abs(angles.trunk_flexion)

        if trunk_flexion < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            trunk_flexion,
            {
                "mild": self.mild_threshold,
                "moderate": self.moderate_threshold,
                "severe": self.severe_threshold,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        self._last_fault_frame = angles.frame_index

        message_key = severity.value
        message = FAULT_MESSAGES[FaultType.FORWARD_LEAN].get(
            message_key, "Excessive forward lean"
        )

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "trunk_flexion": trunk_flexion,
            },
        )
