"""
Heel Rise Fault Detection Rule

Detects when heels lift off the ground during squats by
tracking ankle vertical position relative to rep start.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, FAULT_MESSAGES


class HeelRiseRule(FaultRule):
    """
    Rule for detecting heel rise during squats.

    Tracks ankle dorsiflexion angle changes during the rep.
    When dorsiflexion decreases significantly (indicating heel rise),
    a fault is reported.

    Note: In single-camera mode without 3D data, we approximate
    heel rise from ankle angle changes. With 3D data, we could
    directly track ankle Z position.

    The rule uses dorsiflexion angle as a proxy:
    - Baseline dorsiflexion at rep start
    - Significant decrease in dorsiflexion suggests heels rising
    """

    def __init__(
        self,
        threshold_degrees: float = 10.0,  # Dorsiflexion decrease threshold
    ):
        self.threshold_degrees = threshold_degrees

        # Track baseline at rep start
        self._baseline_dorsiflexion_l: float = 0.0
        self._baseline_dorsiflexion_r: float = 0.0
        self._baseline_set: bool = False
        self._last_fault_frame: int = -30

    @property
    def fault_type(self) -> FaultType:
        return FaultType.HEEL_RISE

    def reset(self) -> None:
        """Reset baseline tracking for new rep."""
        self._baseline_dorsiflexion_l = 0.0
        self._baseline_dorsiflexion_r = 0.0
        self._baseline_set = False

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate for heel rise.

        Sets baseline at rep entry, then monitors for significant
        decrease in dorsiflexion during the rep.
        """
        if not in_rep:
            # Reset when not in rep
            if self._baseline_set:
                self.reset()
            return None

        # Set baseline at rep start
        if not self._baseline_set:
            self._baseline_dorsiflexion_l = angles.ankle_dorsiflexion_l
            self._baseline_dorsiflexion_r = angles.ankle_dorsiflexion_r
            self._baseline_set = True
            return None

        # Cooldown between fault reports
        if angles.frame_index - self._last_fault_frame < 30:
            return None

        # Calculate decrease from baseline (heel rise = dorsiflexion decrease)
        decrease_l = self._baseline_dorsiflexion_l - angles.ankle_dorsiflexion_l
        decrease_r = self._baseline_dorsiflexion_r - angles.ankle_dorsiflexion_r
        max_decrease = max(decrease_l, decrease_r)

        if max_decrease < self.threshold_degrees:
            return None

        self._last_fault_frame = angles.frame_index

        # Calculate severity based on magnitude
        if max_decrease >= self.threshold_degrees * 2:
            severity = FaultSeverity.SEVERE
            score = 2.5
        elif max_decrease >= self.threshold_degrees * 1.5:
            severity = FaultSeverity.MODERATE
            score = 2.0
        else:
            severity = FaultSeverity.MILD
            score = 1.0

        affected_side = "left" if decrease_l > decrease_r else "right"

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=FAULT_MESSAGES[FaultType.HEEL_RISE]["detected"],
            angles=angles,
            rep_number=rep_number,
            details={
                "decrease_left": decrease_l,
                "decrease_right": decrease_r,
                "max_decrease": max_decrease,
                "affected_side": affected_side,
            },
        )
