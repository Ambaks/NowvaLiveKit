"""
Fault Detection Rule Engine

Orchestrates all fault detection rules, maintains angle history,
and deduplicates consecutive same-fault frames.
"""

import logging
from collections import deque
from typing import List, Optional, Dict, Type

from biomechanics.utils.types import JointAngles, FaultEvent
from biomechanics.faults.fault_types import FaultRule, FaultType
from biomechanics.faults.rules.depth import DepthRule
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.utils.bone_constraints import BodyProportions
from biomechanics.config import BiomechanicsConfig, get_config

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Orchestrates all fault detection rules.

    Responsibilities:
    - Maintains rolling history of joint angles (maxlen=90 frames)
    - Runs all enabled fault rules on each frame
    - Deduplicates consecutive same-fault detections
    - Provides centralized fault reporting

    Usage:
        engine = RuleEngine()
        faults = engine.evaluate(angles, in_rep=True, rep_number=1)
    """

    def __init__(
        self,
        config: Optional[BiomechanicsConfig] = None,
        history_maxlen: int = 90,
    ):
        """
        Initialize the rule engine.

        Args:
            config: Pipeline configuration (uses global if not provided)
            history_maxlen: Maximum frames to keep in history (default 90 = ~3s at 30fps)
        """
        self.config = config or get_config()
        self.history: deque = deque(maxlen=history_maxlen)

        # Initialize all rules with config thresholds
        self.rules: List[FaultRule] = self._create_rules()

        # Deduplication tracking
        self._last_faults: Dict[str, int] = {}  # fault_type -> last frame
        self._dedup_frames: int = 15  # Minimum frames between same fault

        # Baseline calibration — after first clean rep, adjust thresholds
        # to the user's natural movement pattern
        self._calibrated: bool = False
        self._calibration_reps: int = 0
        self._calibration_target: int = 1  # Calibrate after 1 clean rep
        self._peak_trunk_flexion: float = 0.0
        self._peak_hip_adduction: float = 0.0
        self._peak_asymmetry: float = 0.0
        self._peak_dorsiflexion_drop: float = 0.0
        self._baseline_dorsiflexion_l: float = 0.0
        self._baseline_dorsiflexion_r: float = 0.0
        self._baseline_set: bool = False

    def _create_rules(self) -> List[FaultRule]:
        """Create all fault rules with config thresholds."""
        faults_config = self.config.faults

        return [
            DepthRule(
                quarter_threshold=60.0,
                half_threshold=faults_config.depth.parallel,
                parallel_threshold=faults_config.depth.below_parallel,
            ),
            SymmetryRule(
                mild_threshold=faults_config.bilateral_asymmetry.mild,
                moderate_threshold=faults_config.bilateral_asymmetry.moderate,
                severe_threshold=faults_config.bilateral_asymmetry.severe,
            ),
            HeelRiseRule(
                threshold_degrees=faults_config.heel_rise.threshold_cm * 5,  # Convert cm to degrees approx
            ),
            ForwardLeanRule(
                mild_threshold=faults_config.forward_lean.mild,
                moderate_threshold=faults_config.forward_lean.moderate,
                severe_threshold=faults_config.forward_lean.severe,
            ),
            KneeValgusRule(
                mild_threshold=faults_config.knee_valgus.mild,
                moderate_threshold=faults_config.knee_valgus.moderate,
                severe_threshold=faults_config.knee_valgus.severe,
            ),
        ]

    def apply_body_proportion_scaling(self, proportions: BodyProportions) -> None:
        """Scale fault thresholds based on the user's body proportions.

        Called once by the pipeline after bone-length calibration completes.
        Runs *before* the first-rep baseline calibration so the baseline
        adjustments layer on top of the anatomy-scaled values.
        """
        for rule in self.rules:
            if isinstance(rule, KneeValgusRule):
                rule.mild_threshold *= proportions.valgus_scale
                rule.moderate_threshold *= proportions.valgus_scale
                rule.severe_threshold *= proportions.valgus_scale
                logger.info(
                    "[RULE ENGINE] Proportion scaling — knee valgus: "
                    "hip/femur=%.3f, scale=%.2f → thresholds %.1f/%.1f/%.1f",
                    proportions.hip_to_femur_ratio,
                    proportions.valgus_scale,
                    rule.mild_threshold,
                    rule.moderate_threshold,
                    rule.severe_threshold,
                )
            elif isinstance(rule, HeelRiseRule):
                rule.threshold_degrees *= proportions.heel_rise_scale
                logger.info(
                    "[RULE ENGINE] Proportion scaling — heel rise: "
                    "tibia_ratio=%.2f, scale=%.2f → threshold %.1f°",
                    proportions.tibia_to_reference_ratio,
                    proportions.heel_rise_scale,
                    rule.threshold_degrees,
                )
            elif isinstance(rule, ForwardLeanRule):
                rule.mild_threshold *= proportions.forward_lean_scale
                rule.moderate_threshold *= proportions.forward_lean_scale
                rule.severe_threshold *= proportions.forward_lean_scale
                logger.info(
                    "[RULE ENGINE] Proportion scaling — forward lean: "
                    "femur/torso scale=%.2f → thresholds %.1f/%.1f/%.1f",
                    proportions.forward_lean_scale,
                    rule.mild_threshold,
                    rule.moderate_threshold,
                    rule.severe_threshold,
                )

    def reset(self) -> None:
        """Reset engine state (clear history and rule states)."""
        self.history.clear()
        self._last_faults.clear()

        # Reset stateful rules
        for rule in self.rules:
            if hasattr(rule, "reset"):
                rule.reset()

    def add_rule(self, rule: FaultRule) -> None:
        """Add a custom rule to the engine."""
        self.rules.append(rule)

    def remove_rule(self, fault_type: FaultType) -> bool:
        """Remove a rule by fault type. Returns True if removed."""
        for i, rule in enumerate(self.rules):
            if rule.fault_type == fault_type:
                self.rules.pop(i)
                return True
        return False

    def evaluate(
        self,
        angles: JointAngles,
        in_rep: bool = False,
        rep_number: int = 0,
    ) -> List[FaultEvent]:
        """
        Evaluate all rules for the current frame.

        Args:
            angles: Current frame's joint angles
            in_rep: Whether currently in a rep
            rep_number: Current rep number

        Returns:
            List of detected faults (deduplicated)
        """
        # Add to history
        self.history.append(angles)

        faults: List[FaultEvent] = []

        for rule in self.rules:
            fault = rule.evaluate(
                angles=angles,
                history=self.history,
                in_rep=in_rep,
                rep_number=rep_number,
            )

            if fault is not None:
                # Deduplicate consecutive same-fault frames
                if self._should_report_fault(fault, angles.frame_index):
                    faults.append(fault)
                    self._last_faults[fault.fault_type] = angles.frame_index

        return faults

    def _should_report_fault(self, fault: FaultEvent, frame_index: int) -> bool:
        """Check if fault should be reported (deduplication)."""
        last_frame = self._last_faults.get(fault.fault_type, -self._dedup_frames - 1)
        return frame_index - last_frame >= self._dedup_frames

    # ------------------------------------------------------------------
    # Baseline calibration
    # ------------------------------------------------------------------

    def record_frame_for_calibration(self, angles: JointAngles) -> None:
        """Track peak angle values during reps for baseline calibration."""
        if self._calibrated:
            return

        # Set dorsiflexion baseline at start of tracking
        if not self._baseline_set:
            self._baseline_dorsiflexion_l = angles.ankle_dorsiflexion_l
            self._baseline_dorsiflexion_r = angles.ankle_dorsiflexion_r
            self._baseline_set = True

        # Track peaks
        self._peak_trunk_flexion = max(self._peak_trunk_flexion, abs(angles.trunk_flexion))
        self._peak_hip_adduction = max(
            self._peak_hip_adduction,
            max(angles.hip_adduction_l, angles.hip_adduction_r),
        )
        self._peak_asymmetry = max(
            self._peak_asymmetry,
            abs(angles.hip_flexion_l - angles.hip_flexion_r),
            abs(angles.knee_flexion_l - angles.knee_flexion_r),
        )

        # Dorsiflexion drop (heel rise proxy)
        drop_l = self._baseline_dorsiflexion_l - angles.ankle_dorsiflexion_l
        drop_r = self._baseline_dorsiflexion_r - angles.ankle_dorsiflexion_r
        self._peak_dorsiflexion_drop = max(
            self._peak_dorsiflexion_drop, max(drop_l, drop_r)
        )

    def on_rep_complete_calibration(self, is_clean: bool) -> None:
        """Called after a rep completes to advance calibration."""
        if self._calibrated:
            return

        if is_clean:
            self._calibration_reps += 1

        if self._calibration_reps >= self._calibration_target:
            self._apply_baseline()

    def _apply_baseline(self) -> None:
        """Adjust rule thresholds based on observed baseline peaks."""
        self._calibrated = True
        faults_config = self.config.faults

        for rule in self.rules:
            if isinstance(rule, ForwardLeanRule):
                rule.mild_threshold = max(rule.mild_threshold, self._peak_trunk_flexion + 10.0)
                rule.moderate_threshold = max(rule.moderate_threshold, self._peak_trunk_flexion + 15.0)
                rule.severe_threshold = max(rule.severe_threshold, self._peak_trunk_flexion + 20.0)
                logger.info(
                    "[RULE ENGINE] Forward lean baseline: peak=%.1f° → thresholds %.1f/%.1f/%.1f",
                    self._peak_trunk_flexion, rule.mild_threshold, rule.moderate_threshold, rule.severe_threshold,
                )

            elif isinstance(rule, KneeValgusRule):
                rule.mild_threshold = max(faults_config.knee_valgus.mild, self._peak_hip_adduction + 5.0)
                rule.moderate_threshold = max(faults_config.knee_valgus.moderate, self._peak_hip_adduction + 10.0)
                rule.severe_threshold = max(faults_config.knee_valgus.severe, self._peak_hip_adduction + 15.0)
                logger.info(
                    "[RULE ENGINE] Knee valgus baseline: peak=%.1f° → thresholds %.1f/%.1f/%.1f",
                    self._peak_hip_adduction, rule.mild_threshold, rule.moderate_threshold, rule.severe_threshold,
                )

            elif isinstance(rule, SymmetryRule):
                rule.mild_threshold = max(faults_config.bilateral_asymmetry.mild, self._peak_asymmetry + 5.0)
                rule.moderate_threshold = max(faults_config.bilateral_asymmetry.moderate, self._peak_asymmetry + 10.0)
                rule.severe_threshold = max(faults_config.bilateral_asymmetry.severe, self._peak_asymmetry + 15.0)
                logger.info(
                    "[RULE ENGINE] Symmetry baseline: peak=%.1f° → thresholds %.1f/%.1f/%.1f",
                    self._peak_asymmetry, rule.mild_threshold, rule.moderate_threshold, rule.severe_threshold,
                )

            elif isinstance(rule, HeelRiseRule):
                rule.threshold_degrees = max(
                    faults_config.heel_rise.threshold_cm * 5,
                    self._peak_dorsiflexion_drop + 10.0,
                )
                logger.info(
                    "[RULE ENGINE] Heel rise baseline: peak_drop=%.1f° → threshold %.1f°",
                    self._peak_dorsiflexion_drop, rule.threshold_degrees,
                )

        logger.info("[RULE ENGINE] Baseline calibration complete")

    @property
    def calibrated(self) -> bool:
        """Whether baseline calibration is complete."""
        return self._calibrated

    def evaluate_rep_complete(
        self,
        max_depth_angle: float,
        angles: JointAngles,
        rep_number: int,
    ) -> List[FaultEvent]:
        """
        Evaluate rules that fire at rep completion.

        Currently only depth rule fires at rep end.

        Args:
            max_depth_angle: Maximum knee flexion achieved in rep
            angles: Current (end of rep) joint angles
            rep_number: Completed rep number

        Returns:
            List of rep-completion faults
        """
        faults: List[FaultEvent] = []

        # Find and evaluate depth rule
        for rule in self.rules:
            if isinstance(rule, DepthRule):
                fault = rule.evaluate_max_depth(
                    max_knee_flexion=max_depth_angle,
                    angles=angles,
                    rep_number=rep_number,
                )
                if fault is not None:
                    faults.append(fault)
                break

        return faults

    def get_rule(self, fault_type: FaultType) -> Optional[FaultRule]:
        """Get a specific rule by fault type."""
        for rule in self.rules:
            if rule.fault_type == fault_type:
                return rule
        return None

    @property
    def rule_count(self) -> int:
        """Number of active rules."""
        return len(self.rules)

    @property
    def history_length(self) -> int:
        """Current history length."""
        return len(self.history)
