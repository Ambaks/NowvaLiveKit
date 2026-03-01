"""
Bilateral Asymmetry Fault Detection Rule

Compares left vs right hip and knee flexion angles to detect
weight shifts and imbalanced movement patterns.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES


class SymmetryRule(FaultRule):
    """
    Rule for detecting bilateral asymmetry.

    Compares left vs right joint angles to identify:
    - Weight shifting to one side
    - Uneven descent patterns
    - Compensatory movement

    Fires when the absolute difference between L/R exceeds thresholds.
    Evaluates both hip and knee asymmetry, reporting the larger deviation.

    Severity thresholds:
    - Mild: 5-10° difference
    - Moderate: 10-15° difference
    - Severe: >15° difference
    """

    def __init__(
        self,
        mild_threshold: float = 5.0,
        moderate_threshold: float = 10.0,
        severe_threshold: float = 15.0,
    ):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        # Track asymmetry history for smoothing
        self._last_fault_frame: int = -30  # Prevent rapid re-firing

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

        # Calculate asymmetries
        hip_asymmetry = abs(angles.hip_flexion_l - angles.hip_flexion_r)
        knee_asymmetry = abs(angles.knee_flexion_l - angles.knee_flexion_r)

        # Use the larger asymmetry
        max_asymmetry = max(hip_asymmetry, knee_asymmetry)
        asymmetry_type = "hip" if hip_asymmetry > knee_asymmetry else "knee"

        # Check against thresholds
        if max_asymmetry < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            max_asymmetry,
            {
                "mild": self.mild_threshold,
                "moderate": self.moderate_threshold,
                "severe": self.severe_threshold,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        self._last_fault_frame = angles.frame_index

        # Determine which side is higher (more flexed)
        if asymmetry_type == "hip":
            heavier_side = "left" if angles.hip_flexion_l > angles.hip_flexion_r else "right"
        else:
            heavier_side = "left" if angles.knee_flexion_l > angles.knee_flexion_r else "right"

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
                "hip_asymmetry": hip_asymmetry,
                "knee_asymmetry": knee_asymmetry,
                "max_asymmetry": max_asymmetry,
                "asymmetry_type": asymmetry_type,
                "heavier_side": heavier_side,
            },
        )
