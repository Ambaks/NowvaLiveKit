"""
Depth Fault Detection Rule

Evaluates squat depth based on knee flexion angle.
Categories: quarter (<60°), half (60-90°), parallel (90-100°), below parallel (>100°)
"""

from collections import deque
from typing import Optional

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.fault_types import FaultRule, FaultType, DEFAULT_THRESHOLDS, FAULT_MESSAGES


class DepthCategory:
    """Depth category constants."""
    QUARTER = "quarter"
    HALF = "half"
    PARALLEL = "parallel"
    BELOW_PARALLEL = "below_parallel"


# BiLSTM depth class (0-4) → depth category. Used when the classifier, not
# the knee angle, is the authority on whether a rep was deep enough.
DEPTH_CLASS_TO_CATEGORY = {
    0: DepthCategory.QUARTER,
    1: DepthCategory.QUARTER,
    2: DepthCategory.HALF,
    3: DepthCategory.PARALLEL,
    4: DepthCategory.BELOW_PARALLEL,
}


class DepthRule(FaultRule):
    """
    Rule for evaluating squat depth.

    This rule fires at the end of a rep (when depth can be fully assessed)
    and reports the achieved depth category.

    Thresholds:
    - Quarter: < 60° knee flexion
    - Half: 60-90° knee flexion
    - Parallel: 90-100° knee flexion (hip crease at knee level)
    - Below Parallel: > 100° knee flexion

    A fault is reported for quarter or half depth; parallel and below
    are considered acceptable depth levels.
    """

    def __init__(
        self,
        quarter_threshold: float = 60.0,
        half_threshold: float = 90.0,
        parallel_threshold: float = 100.0,
    ):
        self.quarter_threshold = quarter_threshold
        self.half_threshold = half_threshold
        self.parallel_threshold = parallel_threshold

        # Track maximum depth seen in current rep
        self._max_depth_in_rep: float = 0.0
        self._depth_evaluated_for_rep: int = -1

    @property
    def fault_type(self) -> FaultType:
        return FaultType.DEPTH

    def reset(self) -> None:
        """Reset tracking for new rep."""
        self._max_depth_in_rep = 0.0
        self._depth_evaluated_for_rep = -1

    def get_depth_category(self, knee_flexion: float) -> str:
        """Categorize depth based on knee flexion angle."""
        if knee_flexion >= self.parallel_threshold:
            return DepthCategory.BELOW_PARALLEL
        elif knee_flexion >= self.half_threshold:
            return DepthCategory.PARALLEL
        elif knee_flexion >= self.quarter_threshold:
            return DepthCategory.HALF
        else:
            return DepthCategory.QUARTER

    def evaluate(
        self,
        angles: JointAngles,
        history: deque,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate depth during a rep.

        Only fires at rep completion (when in_rep transitions to False)
        or when explicitly evaluating at max depth.
        """
        avg_knee = angles.avg_knee_flexion

        # Track max depth during rep
        if in_rep:
            if avg_knee > self._max_depth_in_rep:
                self._max_depth_in_rep = avg_knee
            return None

        # Rep ended or not in rep - evaluate if we have tracked depth
        if self._max_depth_in_rep > 0 and self._depth_evaluated_for_rep != rep_number:
            self._depth_evaluated_for_rep = rep_number
            max_depth = self._max_depth_in_rep
            self._max_depth_in_rep = 0.0  # Reset for next rep

            category = self.get_depth_category(max_depth)

            # Only report as fault for insufficient depth
            if category == DepthCategory.QUARTER:
                return self._create_fault_event(
                    severity=FaultSeverity.MODERATE,
                    severity_score=2.0,
                    message=FAULT_MESSAGES[FaultType.DEPTH]["quarter"],
                    angles=angles,
                    rep_number=rep_number,
                    details={
                        "max_knee_flexion": max_depth,
                        "category": category,
                    },
                )
            elif category == DepthCategory.HALF:
                return self._create_fault_event(
                    severity=FaultSeverity.MILD,
                    severity_score=1.0,
                    message=FAULT_MESSAGES[FaultType.DEPTH]["half"],
                    angles=angles,
                    rep_number=rep_number,
                    details={
                        "max_knee_flexion": max_depth,
                        "category": category,
                    },
                )

        return None

    def evaluate_depth_class(
        self,
        max_depth_class: int,
        angles: JointAngles,
        rep_number: int = 0,
        max_knee_flexion: float = 0.0,
    ) -> Optional[FaultEvent]:
        """
        Evaluate depth from a BiLSTM depth class rather than a knee angle.

        Used for shallow reps, where the classifier already rejected the rep
        for depth — deriving the fault from the same signal keeps the cue and
        the rep count from ever disagreeing.
        """
        category = DEPTH_CLASS_TO_CATEGORY.get(max_depth_class, DepthCategory.QUARTER)

        if category not in (DepthCategory.QUARTER, DepthCategory.HALF):
            return None

        severity = (
            FaultSeverity.MODERATE if category == DepthCategory.QUARTER
            else FaultSeverity.MILD
        )
        return self._create_fault_event(
            severity=severity,
            severity_score=2.0 if category == DepthCategory.QUARTER else 1.0,
            message=FAULT_MESSAGES[FaultType.DEPTH][category],
            angles=angles,
            rep_number=rep_number,
            details={
                "max_knee_flexion": max_knee_flexion,
                "max_depth_class": max_depth_class,
                "category": category,
                "shallow_rep": True,
            },
        )

    def evaluate_max_depth(
        self,
        max_knee_flexion: float,
        angles: JointAngles,
        rep_number: int = 0,
    ) -> Optional[FaultEvent]:
        """
        Directly evaluate depth from known max flexion.

        Used when rep completes and max depth is already known.
        """
        category = self.get_depth_category(max_knee_flexion)

        if category == DepthCategory.QUARTER:
            return self._create_fault_event(
                severity=FaultSeverity.MODERATE,
                severity_score=2.0,
                message=FAULT_MESSAGES[FaultType.DEPTH]["quarter"],
                angles=angles,
                rep_number=rep_number,
                details={
                    "max_knee_flexion": max_knee_flexion,
                    "category": category,
                },
            )
        elif category == DepthCategory.HALF:
            return self._create_fault_event(
                severity=FaultSeverity.MILD,
                severity_score=1.0,
                message=FAULT_MESSAGES[FaultType.DEPTH]["half"],
                angles=angles,
                rep_number=rep_number,
                details={
                    "max_knee_flexion": max_knee_flexion,
                    "category": category,
                },
            )

        return None
