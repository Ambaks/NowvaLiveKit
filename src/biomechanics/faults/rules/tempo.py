"""
Tempo-Based Fault Detection Rule (rep-level).

Evaluates at rep close using the per-rep velocity stats populated on RepData
by SignalRepCounter (peak/avg descent and ascent velocities, in cm/s of the
exercise's rep signal).

Emits one of three fault sub-types via the fault_type string on FaultEvent:
  - "tempo_uncontrolled" — descent too fast (peak descent velocity above bound)
  - "tempo_stalled"      — descent too slow (peak descent velocity below bound)
  - "tempo_grind"        — ascent too slow (peak ascent velocity below bound)

Per-frame evaluate() is a no-op — this rule only fires on rep complete.
"""

from collections import deque
from typing import List, Optional

from biomechanics.faults.fault_types import FaultRule, FaultType
from biomechanics.utils.types import (
    FaultEvent,
    FaultSeverity,
    JointAngles,
    RepData,
)


class TempoRule(FaultRule):
    """Rep-level tempo fault rule based on hip-velocity peaks.

    Bounds default to a teaching-friendly window for unloaded squats.
    They can be widened post-calibration via apply_baseline (squat profile).
    """

    def __init__(
        self,
        descent_min_cm_s: float = 60.0,
        descent_max_cm_s: float = 200.0,
        ascent_min_cm_s: float = 50.0,
    ):
        self.descent_min_cm_s = descent_min_cm_s
        self.descent_max_cm_s = descent_max_cm_s
        self.ascent_min_cm_s = ascent_min_cm_s

    @property
    def fault_type(self) -> FaultType:
        return FaultType.TEMPO

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        # Per-frame evaluation intentionally a no-op; this rule fires only
        # at rep close via evaluate_rep_complete(rep_data).
        return None

    def evaluate_rep_complete(self, rep_data: RepData) -> List[FaultEvent]:
        """Evaluate tempo at rep close. Returns 0..N FaultEvents."""
        out: List[FaultEvent] = []

        peak_d = rep_data.peak_descent_velocity_cm_s
        peak_a = rep_data.peak_ascent_velocity_cm_s

        if peak_d > self.descent_max_cm_s:
            excess = peak_d - self.descent_max_cm_s
            severity, score = self._severity_from_excess(excess, ref=self.descent_max_cm_s)
            out.append(self._fault(
                "tempo_uncontrolled",
                severity, score,
                f"Descent too fast ({peak_d:.0f} cm/s)",
                rep_data,
                {"peak_descent_velocity_cm_s": peak_d, "max_cm_s": self.descent_max_cm_s},
            ))
        elif peak_d < self.descent_min_cm_s and peak_d > 0:
            deficit = self.descent_min_cm_s - peak_d
            severity, score = self._severity_from_excess(deficit, ref=self.descent_min_cm_s)
            out.append(self._fault(
                "tempo_stalled",
                severity, score,
                f"Descent too slow ({peak_d:.0f} cm/s)",
                rep_data,
                {"peak_descent_velocity_cm_s": peak_d, "min_cm_s": self.descent_min_cm_s},
            ))

        if peak_a < self.ascent_min_cm_s and peak_a > 0:
            deficit = self.ascent_min_cm_s - peak_a
            severity, score = self._severity_from_excess(deficit, ref=self.ascent_min_cm_s)
            out.append(self._fault(
                "tempo_grind",
                severity, score,
                f"Ascent too slow ({peak_a:.0f} cm/s)",
                rep_data,
                {"peak_ascent_velocity_cm_s": peak_a, "min_cm_s": self.ascent_min_cm_s},
            ))

        return out

    @staticmethod
    def _severity_from_excess(excess: float, ref: float) -> tuple:
        """Map (excess / ref) ratio into MILD/MODERATE/SEVERE."""
        ratio = excess / ref if ref > 0 else 0.0
        if ratio >= 0.5:
            return FaultSeverity.SEVERE, min(3.0, 2.5 + ratio)
        if ratio >= 0.25:
            return FaultSeverity.MODERATE, 1.5 + ratio
        return FaultSeverity.MILD, 0.5 + ratio

    @staticmethod
    def _fault(
        fault_type: str,
        severity: FaultSeverity,
        score: float,
        message: str,
        rep_data: RepData,
        details: dict,
    ) -> FaultEvent:
        return FaultEvent(
            fault_type=fault_type,
            severity=severity,
            severity_score=score,
            message=message,
            timestamp=rep_data.end_time,
            frame_index=rep_data.end_frame,
            rep_number=rep_data.rep_number,
            details=details,
        )
