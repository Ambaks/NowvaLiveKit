"""
Exercise Profile Base Class

Defines the ExerciseProfile interface that bundles exercise-specific concerns:
fault rules, rep counting signal, coaching cues, calibration config, and
depth categorization. The pipeline delegates to the active profile for all
exercise-specific behavior.

Subclasses override only the methods that differ from the default (squat)
behavior. This is a concrete base class, not an ABC — every method has a
sensible default so new exercises can be added incrementally.
"""

from typing import Dict, List, Optional

from biomechanics.config import BiomechanicsConfig, HipPositionCounterConfig
from biomechanics.faults.fault_types import FaultRule
from biomechanics.utils.types import JointAngles, Skeleton3D, depth_category


class ExerciseProfile:
    """
    Base exercise profile with squat defaults.

    Subclasses override methods to customize behavior for their exercise.
    The pipeline calls these methods during initialization and per-frame
    processing — profiles are factories, not owners.
    """

    name: str = "default"
    movement_pattern: str = "squat"

    def create_fault_rules(self, config: BiomechanicsConfig) -> List[FaultRule]:
        """Create the fault rules for this exercise.

        Returns a list of FaultRule instances configured with appropriate
        thresholds. The pipeline passes these to the RuleEngine.

        Default: returns None to let RuleEngine use its built-in _create_rules().
        """
        return None

    def get_rep_signal(
        self, skeleton_3d: Skeleton3D, angles: Optional[JointAngles] = None
    ) -> float:
        """Compute the rep counting signal from the current frame.

        The returned float drives the HipPositionRepCounter FSM. Different
        exercises use different signals:
        - Squats: hip Y-position relative to ankle (cm)
        - Deadlifts: trunk flexion angle
        - Bench press: elbow flexion angle

        Args:
            skeleton_3d: Current frame's 3D skeleton.
            angles: Current frame's joint angles (may be None early in pipeline).

        Returns:
            Signal value for the rep counter.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement get_rep_signal()"
        )

    def create_rep_counter_config(
        self, config: BiomechanicsConfig
    ) -> HipPositionCounterConfig:
        """Return rep counter config tuned for this exercise's signal range.

        Default: uses the pipeline's hip_counter config as-is.
        """
        return config.hip_counter

    def get_cue_dict(self) -> Optional[Dict[str, str]]:
        """Return exercise-specific cue dictionary, or None to use cue_cache defaults."""
        return None

    def get_fault_to_cue_map(self) -> Optional[Dict[str, str]]:
        """Return fault-type to cue-key mapping, or None to use cue_cache defaults."""
        return None

    def categorize_depth(self, angle: float) -> str:
        """Categorize rep depth from the max angle achieved.

        Default: delegates to the standard squat depth_category().
        """
        return depth_category(angle)
