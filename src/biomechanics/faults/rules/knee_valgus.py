"""
Knee Valgus Fault Detection Rule

Detects knee cave (valgus) using hip adduction angle as a proxy.
V1 implementation uses rule-based detection; future versions
will use TCN model for dynamic trajectory analysis.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES


class KneeValgusRule(FaultRule):
    """
    V1 rule-based knee valgus detection.

    Uses hip adduction angle as a proxy for knee valgus:
    - Increased hip adduction during squat indicates knees
      tracking inward relative to feet
    - This correlates with knee valgus in most cases

    Severity thresholds (hip adduction degrees):
    - Mild: 5-10° hip adduction
    - Moderate: 10-15° hip adduction
    - Severe: >15° hip adduction

    Note: This is a simplified v1 approach. The v2 implementation
    will use a TCN model trained on labeled valgus data to detect
    the dynamic trajectory pattern of knee cave, which is more
    accurate but requires training data.

    Hip adduction convention:
    - 0° = neutral (knee tracking over toe)
    - Positive = adduction (knee caving in)
    - Negative = abduction (knee pushing out)
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

        self._last_fault_frame: int = -30

    @property
    def fault_type(self) -> FaultType:
        return FaultType.KNEE_VALGUS

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate for knee valgus using hip adduction.

        Only fires during reps and when hip adduction exceeds
        the mild threshold.
        """
        if not in_rep:
            return None

        # Cooldown between fault reports
        if angles.frame_index - self._last_fault_frame < 30:
            return None

        # Check hip adduction on both sides (positive = adduction = valgus)
        adduction_l = angles.hip_adduction_l
        adduction_r = angles.hip_adduction_r

        # Only consider positive adduction (actual valgus)
        max_adduction = max(adduction_l, adduction_r)

        if max_adduction < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            max_adduction,
            {
                "mild": self.mild_threshold,
                "moderate": self.moderate_threshold,
                "severe": self.severe_threshold,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        self._last_fault_frame = angles.frame_index

        # Determine which side has worse valgus
        affected_side = "left" if adduction_l > adduction_r else "right"
        if abs(adduction_l - adduction_r) < 2.0:
            affected_side = "both"

        message_key = severity.value
        message = FAULT_MESSAGES[FaultType.KNEE_VALGUS].get(
            message_key, "Knee valgus detected"
        )

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "hip_adduction_l": adduction_l,
                "hip_adduction_r": adduction_r,
                "max_adduction": max_adduction,
                "affected_side": affected_side,
            },
        )
