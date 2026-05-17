"""Limited Dorsiflexion Fault Detection Rule.

Flags reps where peak ankle dorsiflexion stays below a threshold,
indicating restricted ankle mobility that may force compensations
(excessive forward lean, heel rise, limited depth).

Severity is clamped to MODERATE — this is an informational mobility cue.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES


class LimitedDorsiflexionRule(FaultRule):
    """Detect limited ankle dorsiflexion during a rep.

    Accumulates the max dorsiflexion seen for each ankle across the rep
    and evaluates at rep end.  If the max stays below ``threshold``
    degrees, a fault is emitted with severity clamped to MODERATE.
    """

    def __init__(
        self,
        threshold: float = 25.0,
        mild_threshold: float = 20.0,
        moderate_threshold: float = 15.0,
    ):
        self.threshold = threshold
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold

        self._max_dorsi_l: float = 0.0
        self._max_dorsi_r: float = 0.0
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.LIMITED_DORSIFLEXION

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        if in_rep:
            self._max_dorsi_l = max(self._max_dorsi_l, angles.ankle_dorsiflexion_l)
            self._max_dorsi_r = max(self._max_dorsi_r, angles.ankle_dorsiflexion_r)
            self._in_rep_prev = True
            return None

        if not self._in_rep_prev or self._evaluated_rep == rep_number:
            return None

        self._in_rep_prev = False
        self._evaluated_rep = rep_number

        max_dorsi_l = self._max_dorsi_l
        max_dorsi_r = self._max_dorsi_r
        self._max_dorsi_l = 0.0
        self._max_dorsi_r = 0.0

        worst = min(max_dorsi_l, max_dorsi_r)
        if worst >= self.threshold:
            return None

        deficit = self.threshold - worst
        if deficit < (self.threshold - self.mild_threshold):
            return None

        severity, score = self._get_severity(
            deficit,
            {
                "mild": self.threshold - self.mild_threshold,
                "moderate": self.threshold - self.moderate_threshold,
                "severe": self.threshold - self.moderate_threshold + 10.0,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        # Clamp severity to MODERATE
        if severity == FaultSeverity.SEVERE:
            severity = FaultSeverity.MODERATE
            score = min(score, 2.5)

        message = FAULT_MESSAGES[FaultType.LIMITED_DORSIFLEXION].get(
            severity.value, "Limited ankle dorsiflexion"
        )

        affected = "left" if max_dorsi_l < max_dorsi_r else "right"
        if abs(max_dorsi_l - max_dorsi_r) < 2.0:
            affected = "both"

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "max_dorsiflexion_l": round(max_dorsi_l, 1),
                "max_dorsiflexion_r": round(max_dorsi_r, 1),
                "threshold": self.threshold,
                "affected_side": affected,
            },
        )
