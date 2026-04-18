"""
Bar Path Fault Detection Rule

Tracks horizontal bar drift across a rep. A straight bar path
is critical for efficiency in OHP, deadlift, and bench press.

Prefers a real barbell detection (set via ``set_frame_context()`` by the rule
engine) so drift is measured from the actual bar center. Falls back to
averaging the two wrist x-positions when no detection is available — the
historical behavior that keeps this rule useful for pose-only pipelines.
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType


class BarPathRule(FaultRule):
    """
    Rule for detecting excessive bar path drift.

    Drift signal priority:
        1. If a ``BarbellDetection`` is present, use the detected bar center's
           x-position in shoulder-relative cm (projected using the pose's
           shoulder midpoint + the calibration implied by the bar length).
        2. Otherwise, fall back to the average of left/right wrist_x, which
           the IK already reports in shoulder-relative cm.

    Thresholds (cm of drift):
    - Mild: 8-15 cm
    - Moderate: 15-22 cm
    - Severe: >22 cm
    """

    # Standard Olympic bar length in meters (matches BarbellTrackingConfig default).
    _BAR_LENGTH_M: float = 2.2

    def __init__(
        self,
        mild_threshold: float = 8.0,
        moderate_threshold: float = 15.0,
        severe_threshold: float = 22.0,
    ):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold

        self._min_x: float = float("inf")
        self._max_x: float = float("-inf")
        self._in_rep_prev: bool = False
        self._evaluated_rep: int = -1
        self._used_bar_detection: bool = False

    @property
    def fault_type(self) -> FaultType:
        return FaultType.BAR_PATH

    def reset(self) -> None:
        self._min_x = float("inf")
        self._max_x = float("-inf")
        self._in_rep_prev = False
        self._used_bar_detection = False

    def _drift_signal_cm(self, angles: JointAngles) -> Optional[float]:
        """Return the current frame's bar-x signal in shoulder-relative cm."""
        detection = self._bar_detection
        if detection is not None:
            # Build px→cm calibration from the bar's pixel length and its known
            # real length, then convert bar-center-x to cm. We report it in
            # absolute image-cm; drift is (max - min), so any constant offset
            # cancels out — we don't need the shoulder midpoint for drift.
            bar_px = detection.bar_length_px
            if bar_px > 1.0:
                cm_per_px = (self._BAR_LENGTH_M * 100.0) / bar_px
                cx, _ = detection.center
                self._used_bar_detection = True
                return float(cx) * cm_per_px

        # Fallback: pose wrist proxy
        self._used_bar_detection = False
        return (angles.wrist_x_l + angles.wrist_x_r) / 2.0

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        if in_rep:
            x_cm = self._drift_signal_cm(angles)
            if x_cm is not None:
                self._min_x = min(self._min_x, x_cm)
                self._max_x = max(self._max_x, x_cm)
            self._in_rep_prev = True
            return None

        # Rep just ended
        if self._in_rep_prev and self._evaluated_rep != rep_number:
            self._in_rep_prev = False
            self._evaluated_rep = rep_number

            drift = self._max_x - self._min_x
            used_detection = self._used_bar_detection
            self._min_x = float("inf")
            self._max_x = float("-inf")
            self._used_bar_detection = False

            if drift < self.mild_threshold:
                return None

            severity, score = self._get_severity(
                drift,
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
                message="Bar drifting — keep path straight",
                angles=angles,
                rep_number=rep_number,
                details={
                    "drift_cm": drift,
                    "source": "barbell_detection" if used_detection else "wrist_proxy",
                },
            )

        return None
