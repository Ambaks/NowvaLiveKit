"""
Fault Detection Rule Engine

Orchestrates all fault detection rules, maintains angle history,
and deduplicates consecutive same-fault frames.
"""

from collections import deque
from typing import List, Optional, Dict, Type

from biomechanics.utils.types import JointAngles, FaultEvent
from biomechanics.faults.fault_types import FaultRule, FaultType
from biomechanics.faults.rules.depth import DepthRule
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.config import BiomechanicsConfig, get_config


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
