"""
Trunk Stability Fault Detection Rule

Detects trunk angle drift during exercises where the torso
should remain fixed (barbell row, RDL, Bulgarian split squat).
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType


class TrunkStabilityRule(FaultRule):
    """
    Rule for detecting trunk angle drift during a rep.

    Records trunk flexion at rep entry and fires if the trunk
    moves more than the threshold during the rep. Unlike
    BackRoundingRule (which detects rounding under load), this
    rule detects any trunk movement — rocking, swaying, or
    using momentum.

    Severity bands (degrees of total trunk movement during rep):
    - Mild: 10-20°
    - Moderate: 20-30°
    - Severe: >30°
    """

    def __init__(
        self,
        mild_threshold: float = 10.0,
        moderate_threshold: float = 20.0,
        severe_threshold: float = 30.0,
    ):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        self._min_trunk: float = 360.0
        self._max_trunk: float = 0.0
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.TRUNK_STABILITY

    def reset(self) -> None:
        self._min_trunk = 360.0
        self._max_trunk = 0.0
        self._in_rep_prev = False

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        if in_rep:
            self._min_trunk = min(self._min_trunk, angles.trunk_flexion)
            self._max_trunk = max(self._max_trunk, angles.trunk_flexion)
            self._in_rep_prev = True
            return None

        # Rep just ended
        if self._in_rep_prev and self._evaluated_rep != rep_number:
            self._in_rep_prev = False
            self._evaluated_rep = rep_number

            trunk_range = self._max_trunk - self._min_trunk
            self._min_trunk = 360.0
            self._max_trunk = 0.0

            if trunk_range < self.mild_threshold:
                return None

            severity, score = self._get_severity(
                trunk_range,
                {
                    "mild": self.mild_threshold,
                    "moderate": self.moderate_threshold,
                    "severe": self.severe_threshold,
                },
            )

            if severity == FaultSeverity.NONE:
                return None

            return self._create_fault_event(
                severity=severity,
                severity_score=score,
                message="Keep torso stable — avoid rocking",
                angles=angles,
                rep_number=rep_number,
                details={
                    "trunk_range": trunk_range,
                },
            )

        return None
