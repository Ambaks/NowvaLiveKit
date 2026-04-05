"""
Knee Valgus Fault Detection Rule

Detects knee cave (valgus) using the frontal-plane deviation of the knee
from the hip-to-big-toe reference line (primary), with fallback to hip
adduction angle when foot landmarks are unavailable.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES

# Minimum foot landmark confidence to use toe-based valgus metric
FOOT_CONFIDENCE_THRESHOLD = 0.3


class KneeValgusRule(FaultRule):
    """
    Knee valgus detection using knee-to-toe deviation with hip adduction fallback.

    Primary metric (when foot landmarks available):
    - Frontal-plane angle between the hip-to-toe reference line and the
      hip-to-knee vector. Positive = knee medial to toe (valgus).

    Fallback metric (when foot landmarks unavailable):
    - Hip adduction angle (thigh medial deviation from sagittal plane).
      Used when foot_confidence is below FOOT_CONFIDENCE_THRESHOLD.

    Severity thresholds apply to both metrics identically.
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
        Evaluate for knee valgus using toe-based metric or hip adduction fallback.

        Only fires during reps and when valgus exceeds the mild threshold.
        """
        if not in_rep:
            return None

        # Cooldown between fault reports
        if angles.frame_index - self._last_fault_frame < 30:
            return None

        # Prefer toe-based valgus when both feet have sufficient confidence
        foot_conf = min(angles.foot_confidence_l, angles.foot_confidence_r)

        if foot_conf >= FOOT_CONFIDENCE_THRESHOLD:
            valgus_l = angles.knee_valgus_l
            valgus_r = angles.knee_valgus_r
            metric_source = "toe"
        else:
            valgus_l = angles.hip_adduction_l
            valgus_r = angles.hip_adduction_r
            metric_source = "hip_adduction"

        max_valgus = max(abs(valgus_l), abs(valgus_r))

        if max_valgus < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            max_valgus,
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
        affected_side = "left" if abs(valgus_l) > abs(valgus_r) else "right"
        if abs(abs(valgus_l) - abs(valgus_r)) < 2.0:
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
                "knee_valgus_l": valgus_l,
                "knee_valgus_r": valgus_r,
                "max_valgus": max_valgus,
                "affected_side": affected_side,
                "metric_source": metric_source,
                "hip_adduction_l": angles.hip_adduction_l,
                "hip_adduction_r": angles.hip_adduction_r,
            },
        )
