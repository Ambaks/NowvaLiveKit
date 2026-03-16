"""
Squat Exercise Profile

Extracts the current hardcoded squat behavior from RuleEngine._create_rules()
and the pipeline's hip-position signal computation into a pluggable profile.
This is a pure extraction refactor — zero behavioral change.
"""

from typing import Dict, List, Optional

from biomechanics.config import BiomechanicsConfig
from biomechanics.faults.fault_types import FaultRule
from biomechanics.faults.rules.depth import DepthRule
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.profiles.base import ExerciseProfile
from biomechanics.profiles.registry import register_profile
from biomechanics.utils.types import CocoKeypoints, JointAngles, Skeleton3D


@register_profile(
    "squat",
    "back_squat",
    "front_squat",
    "goblet_squat",
    "bodyweight_squat",
    "barbell_back_squat",
    "barbell_front_squat",
)
class SquatProfile(ExerciseProfile):
    """Profile for all squat variants.

    Reproduces the exact behavior that was previously hardcoded in
    RuleEngine._create_rules() and pipeline.py lines 314-318.
    """

    name = "squat"
    movement_pattern = "squat"

    def create_fault_rules(self, config: BiomechanicsConfig) -> List[FaultRule]:
        """Create the 5 squat fault rules with config thresholds.

        Identical to the previous RuleEngine._create_rules() implementation.
        """
        fc = config.faults
        return [
            DepthRule(
                quarter_threshold=60.0,
                half_threshold=fc.depth.parallel,
                parallel_threshold=fc.depth.below_parallel,
            ),
            SymmetryRule(
                mild_threshold=fc.bilateral_asymmetry.mild,
                moderate_threshold=fc.bilateral_asymmetry.moderate,
                severe_threshold=fc.bilateral_asymmetry.severe,
            ),
            HeelRiseRule(
                threshold_degrees=fc.heel_rise.threshold_cm * 5,
            ),
            ForwardLeanRule(
                mild_threshold=fc.forward_lean.mild,
                moderate_threshold=fc.forward_lean.moderate,
                severe_threshold=fc.forward_lean.severe,
            ),
            KneeValgusRule(
                mild_threshold=fc.knee_valgus.mild,
                moderate_threshold=fc.knee_valgus.moderate,
                severe_threshold=fc.knee_valgus.severe,
            ),
        ]

    def get_rep_signal(
        self, skeleton_3d: Skeleton3D, angles: Optional[JointAngles] = None
    ) -> float:
        """Compute hip vertical position relative to ankle (cm).

        Identical to the previous pipeline.py lines 314-318.
        Convention: more negative = standing, less negative = squat bottom.
        """
        kpts = skeleton_3d.to_numpy()  # (17, 3)
        hip_mid_y = (
            kpts[CocoKeypoints.LEFT_HIP][1] + kpts[CocoKeypoints.RIGHT_HIP][1]
        ) / 2
        ankle_mid_y = (
            kpts[CocoKeypoints.LEFT_ANKLE][1] + kpts[CocoKeypoints.RIGHT_ANKLE][1]
        ) / 2
        return (hip_mid_y - ankle_mid_y) * 100.0
