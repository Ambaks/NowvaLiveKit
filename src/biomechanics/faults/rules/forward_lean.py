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

    Monitors trunk flexion angle during reps.  Trunk flexion uses the
    180-convention: 180° = upright, decreasing with lean.

    Some forward lean is normal and necessary in squats,
    but excessive lean can indicate:
    - Poor ankle mobility
    - Weak posterior chain
    - Bar position issues

    Severity thresholds (180-convention — lower = more lean):
    - Mild: below 145°
    - Moderate: below 135°
    - Severe: below 125°

    Note: These thresholds may need adjustment based on
    squat style (high bar vs low bar) and body proportions.
    """

    def __init__(
        self,
        mild_threshold: float = 145.0,
        moderate_threshold: float = 135.0,
        severe_threshold: float = 125.0,
    ):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        self._last_fault_frame: int = -150  # ~5s at 30fps — avoid spamming

    def scale_for_proportions(self, proportions) -> None:
        self.mild_threshold *= proportions.forward_lean_scale
        self.moderate_threshold *= proportions.forward_lean_scale
        self.severe_threshold *= proportions.forward_lean_scale

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

        trunk_flexion = angles.trunk_flexion  # 180° = upright, lower = more lean

        # Above mild threshold → upright enough → no fault
        if trunk_flexion > self.mild_threshold:
            return None

        # Invert so _get_severity works (higher = more severe)
        lean_amount = self.mild_threshold - trunk_flexion
        severity, score = self._get_severity(
            lean_amount,
            {
                "mild": 0.0,
                "moderate": self.mild_threshold - self.moderate_threshold,
                "severe": self.mild_threshold - self.severe_threshold,
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
