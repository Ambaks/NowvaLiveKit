"""Bar Drift Fault Detection Rule.

Measures horizontal drift of the load reference point (C7-ish) from the
midfoot center in the XZ plane.  A well-balanced squat keeps the load
stacked over midfoot; excessive drift indicates a shift forward or
backward.

Requires ``skeleton_state`` dict with ``load_reference_xz`` and
``midfoot_xz`` arrays, passed via ``set_frame_context()``.  These are
computed externally from the q vector using ``forward_kin.load_reference_point``
and ``forward_kin.midfoot_xz``.
"""

from collections import deque
from typing import Optional

import numpy as np

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, FAULT_MESSAGES


class BarDriftRule(FaultRule):
    """Detect excessive load-reference drift from midfoot during a rep.

    Accumulates the max XZ distance between the load reference and the
    midfoot center across the rep, then evaluates at rep end.

    Thresholds are in centimeters.
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

        self._max_drift_cm: float = 0.0
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.BAR_DRIFT

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        state = self._skeleton_state
        if state is not None and in_rep:
            load_xz = state.get("load_reference_xz")
            mid_xz = state.get("midfoot_xz")
            if load_xz is not None and mid_xz is not None:
                dist_m = float(np.linalg.norm(np.asarray(load_xz) - np.asarray(mid_xz)))
                self._max_drift_cm = max(self._max_drift_cm, dist_m * 100.0)

        if in_rep:
            self._in_rep_prev = True
            return None

        if not self._in_rep_prev or self._evaluated_rep == rep_number:
            return None

        self._in_rep_prev = False
        self._evaluated_rep = rep_number

        drift_cm = self._max_drift_cm
        self._max_drift_cm = 0.0

        if drift_cm < self.mild_threshold:
            return None

        severity, score = self._get_severity(
            drift_cm,
            {
                "mild": self.mild_threshold,
                "moderate": self.moderate_threshold,
                "severe": self.severe_threshold,
            },
        )

        if severity == FaultSeverity.NONE:
            return None

        message = FAULT_MESSAGES[FaultType.BAR_DRIFT].get(
            severity.value, "Bar drifting off midfoot"
        )

        return self._create_fault_event(
            severity=severity,
            severity_score=score,
            message=message,
            angles=angles,
            rep_number=rep_number,
            details={
                "drift_cm": round(drift_cm, 1),
            },
        )
