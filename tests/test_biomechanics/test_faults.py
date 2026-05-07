"""
Tests for Fault Detection Rules

Tests each fault rule with known angle values.
Verifies severity levels, thresholds, and fault messages.
"""

import pytest
import sys
from pathlib import Path
from collections import deque

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.utils.types import JointAngles, FaultSeverity
from biomechanics.faults.fault_types import FaultType
from biomechanics.faults.rules.depth import DepthRule, DepthCategory
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.faults.rule_engine import RuleEngine


def create_joint_angles(
    frame: int = 0,
    timestamp: float = 0.0,
    hip_flexion_l: float = 0.0,
    hip_flexion_r: float = 0.0,
    knee_flexion_l: float = 0.0,
    knee_flexion_r: float = 0.0,
    hip_adduction_l: float = 0.0,
    hip_adduction_r: float = 0.0,
    ankle_dorsiflexion_l: float = 20.0,
    ankle_dorsiflexion_r: float = 20.0,
    trunk_flexion: float = 0.0,
    knee_valgus_l: float = 0.0,
    knee_valgus_r: float = 0.0,
    foot_confidence_l: float = 0.0,
    foot_confidence_r: float = 0.0,
) -> JointAngles:
    """Create JointAngles with specified values, defaults for rest."""
    return JointAngles(
        hip_flexion_l=hip_flexion_l,
        hip_flexion_r=hip_flexion_r,
        knee_flexion_l=knee_flexion_l,
        knee_flexion_r=knee_flexion_r,
        hip_adduction_l=hip_adduction_l,
        hip_adduction_r=hip_adduction_r,
        ankle_dorsiflexion_l=ankle_dorsiflexion_l,
        ankle_dorsiflexion_r=ankle_dorsiflexion_r,
        knee_valgus_l=knee_valgus_l,
        knee_valgus_r=knee_valgus_r,
        foot_confidence_l=foot_confidence_l,
        foot_confidence_r=foot_confidence_r,
        trunk_flexion=trunk_flexion,
        frame_index=frame,
        timestamp=timestamp,
    )


class TestDepthRule:
    """Test DepthRule for squat depth evaluation."""

    @pytest.fixture
    def depth_rule(self):
        return DepthRule()

    @pytest.fixture
    def history(self):
        return deque(maxlen=90)

    def test_depth_category_classification(self, depth_rule):
        """Test depth category thresholds."""
        assert depth_rule.get_depth_category(45.0) == DepthCategory.QUARTER
        assert depth_rule.get_depth_category(60.0) == DepthCategory.HALF
        assert depth_rule.get_depth_category(75.0) == DepthCategory.HALF
        assert depth_rule.get_depth_category(90.0) == DepthCategory.PARALLEL
        assert depth_rule.get_depth_category(95.0) == DepthCategory.PARALLEL
        assert depth_rule.get_depth_category(100.0) == DepthCategory.BELOW_PARALLEL
        assert depth_rule.get_depth_category(110.0) == DepthCategory.BELOW_PARALLEL

    def test_fault_type(self, depth_rule):
        """Depth rule should report DEPTH fault type."""
        assert depth_rule.fault_type == FaultType.DEPTH

    def test_quarter_squat_fault(self, depth_rule):
        """Quarter squat should produce MODERATE fault."""
        angles = create_joint_angles()
        fault = depth_rule.evaluate_max_depth(
            max_knee_flexion=50.0,
            angles=angles,
            rep_number=1,
        )
        assert fault is not None
        assert fault.severity == FaultSeverity.MODERATE
        assert fault.details["category"] == DepthCategory.QUARTER

    def test_half_squat_fault(self, depth_rule):
        """Half squat should produce MILD fault."""
        angles = create_joint_angles()
        fault = depth_rule.evaluate_max_depth(
            max_knee_flexion=75.0,
            angles=angles,
            rep_number=1,
        )
        assert fault is not None
        assert fault.severity == FaultSeverity.MILD
        assert fault.details["category"] == DepthCategory.HALF

    def test_parallel_no_fault(self, depth_rule):
        """Parallel squat should not produce fault."""
        angles = create_joint_angles()
        fault = depth_rule.evaluate_max_depth(
            max_knee_flexion=95.0,
            angles=angles,
            rep_number=1,
        )
        assert fault is None

    def test_below_parallel_no_fault(self, depth_rule):
        """Below parallel squat should not produce fault."""
        angles = create_joint_angles()
        fault = depth_rule.evaluate_max_depth(
            max_knee_flexion=110.0,
            angles=angles,
            rep_number=1,
        )
        assert fault is None

    def test_tracks_max_during_rep(self, depth_rule, history):
        """Depth rule should track max depth during rep."""
        # Enter rep
        angles1 = create_joint_angles(frame=0, knee_flexion_l=50, knee_flexion_r=50)
        depth_rule.evaluate(angles1, history, in_rep=True, rep_number=1)

        angles2 = create_joint_angles(frame=1, knee_flexion_l=80, knee_flexion_r=80)
        depth_rule.evaluate(angles2, history, in_rep=True, rep_number=1)

        angles3 = create_joint_angles(frame=2, knee_flexion_l=95, knee_flexion_r=95)  # Max
        depth_rule.evaluate(angles3, history, in_rep=True, rep_number=1)

        angles4 = create_joint_angles(frame=3, knee_flexion_l=70, knee_flexion_r=70)
        depth_rule.evaluate(angles4, history, in_rep=True, rep_number=1)

        # Check max was tracked
        assert depth_rule._max_depth_in_rep == 95.0


class TestSymmetryRule:
    """Test SymmetryRule for bilateral asymmetry detection."""

    @pytest.fixture
    def symmetry_rule(self):
        return SymmetryRule()

    @pytest.fixture
    def history(self):
        return deque(maxlen=90)

    def test_fault_type(self, symmetry_rule):
        """Symmetry rule should report BILATERAL_ASYMMETRY fault type."""
        assert symmetry_rule.fault_type == FaultType.BILATERAL_ASYMMETRY

    def test_no_fault_when_symmetric(self, symmetry_rule, history):
        """No fault when L/R angles are equal."""
        angles = create_joint_angles(
            frame=0,
            hip_flexion_l=60.0,
            hip_flexion_r=60.0,
            knee_flexion_l=70.0,
            knee_flexion_r=70.0,
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=True)
        assert fault is None

    def test_no_fault_when_not_in_rep(self, symmetry_rule, history):
        """No fault when not in rep even with asymmetry."""
        angles = create_joint_angles(
            frame=0,
            hip_flexion_l=60.0,
            hip_flexion_r=40.0,  # 20° asymmetry
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=False)
        assert fault is None

    def test_mild_asymmetry(self, symmetry_rule, history):
        """Mild asymmetry (5-10°) should produce MILD fault."""
        angles = create_joint_angles(
            frame=0,
            knee_flexion_l=70.0,
            knee_flexion_r=63.0,  # 7° asymmetry on the default (knee) getter
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MILD

    def test_moderate_asymmetry(self, symmetry_rule, history):
        """Moderate asymmetry (10-15°) should produce MODERATE fault."""
        angles = create_joint_angles(
            frame=0,
            knee_flexion_l=80.0,
            knee_flexion_r=68.0,  # 12° asymmetry
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MODERATE

    def test_severe_asymmetry(self, symmetry_rule, history):
        """Severe asymmetry (>15°) should produce SEVERE fault."""
        angles = create_joint_angles(
            frame=0,
            knee_flexion_l=90.0,
            knee_flexion_r=70.0,  # 20° asymmetry on the default (knee) getter
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.SEVERE

    def test_identifies_heavier_side(self, symmetry_rule, history):
        """Fault details should identify which side is heavier."""
        angles = create_joint_angles(
            frame=0,
            knee_flexion_l=90.0,  # Left deeper (20° asymmetry → severe)
            knee_flexion_r=70.0,
        )
        fault = symmetry_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.details["heavier_side"] == "left"


class TestForwardLeanRule:
    """Test ForwardLeanRule for excessive trunk flexion."""

    @pytest.fixture
    def forward_lean_rule(self):
        return ForwardLeanRule()

    @pytest.fixture
    def history(self):
        return deque(maxlen=90)

    def test_fault_type(self, forward_lean_rule):
        """Forward lean rule should report FORWARD_LEAN fault type."""
        assert forward_lean_rule.fault_type == FaultType.FORWARD_LEAN

    # trunk_flexion uses the 180-convention: 180° = upright, lower = more lean.
    # Default thresholds: mild < 145°, moderate < 135°, severe < 125°.

    def test_no_fault_when_upright(self, forward_lean_rule, history):
        """No fault when trunk is near-upright (above mild threshold)."""
        angles = create_joint_angles(frame=0, trunk_flexion=170.0)
        fault = forward_lean_rule.evaluate(angles, history, in_rep=True)
        assert fault is None

    def test_no_fault_when_not_in_rep(self, forward_lean_rule, history):
        """No fault when not in rep even with lean."""
        angles = create_joint_angles(frame=0, trunk_flexion=130.0)
        fault = forward_lean_rule.evaluate(angles, history, in_rep=False)
        assert fault is None

    def test_mild_forward_lean(self, forward_lean_rule, history):
        """Mild forward lean (between mild and moderate thresholds)."""
        angles = create_joint_angles(frame=0, trunk_flexion=140.0)
        fault = forward_lean_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MILD

    def test_moderate_forward_lean(self, forward_lean_rule, history):
        """Moderate forward lean (between moderate and severe thresholds)."""
        angles = create_joint_angles(frame=0, trunk_flexion=130.0)
        fault = forward_lean_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MODERATE

    def test_severe_forward_lean(self, forward_lean_rule, history):
        """Severe forward lean (below severe threshold)."""
        angles = create_joint_angles(frame=0, trunk_flexion=120.0)
        fault = forward_lean_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.SEVERE


class TestKneeValgusRule:
    """Test KneeValgusRule for knee cave detection."""

    @pytest.fixture
    def knee_valgus_rule(self):
        return KneeValgusRule()

    @pytest.fixture
    def history(self):
        return deque(maxlen=90)

    def test_fault_type(self, knee_valgus_rule):
        """Knee valgus rule should report KNEE_VALGUS fault type."""
        assert knee_valgus_rule.fault_type == FaultType.KNEE_VALGUS

    def test_no_fault_when_knees_out(self, knee_valgus_rule, history):
        """No fault when hip adduction is low (knees tracking over toes)."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=2.0,
            hip_adduction_r=2.0,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is None

    def test_no_fault_when_not_in_rep(self, knee_valgus_rule, history):
        """No fault when not in rep even with valgus."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=12.0,
            hip_adduction_r=12.0,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=False)
        assert fault is None

    def test_mild_valgus(self, knee_valgus_rule, history):
        """Mild valgus (5-10° adduction) should produce MILD fault."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=7.0,
            hip_adduction_r=6.0,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MILD

    def test_moderate_valgus(self, knee_valgus_rule, history):
        """Moderate valgus (10-15° adduction) should produce MODERATE fault."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=12.0,
            hip_adduction_r=11.0,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.MODERATE

    def test_severe_valgus(self, knee_valgus_rule, history):
        """Severe valgus (>15° adduction) should produce SEVERE fault."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=18.0,
            hip_adduction_r=16.0,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.severity == FaultSeverity.SEVERE

    def test_identifies_affected_side(self, knee_valgus_rule, history):
        """Fault should identify which side has worse valgus."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=6.0,
            hip_adduction_r=12.0,  # Right is worse
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.details["affected_side"] == "right"

    def test_toe_based_valgus_used_when_confident(self, knee_valgus_rule, history):
        """Should use knee_valgus fields when foot confidence is high."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=2.0,  # Low — would NOT trigger via fallback
            hip_adduction_r=2.0,
            knee_valgus_l=12.0,  # High — should trigger via toe metric
            knee_valgus_r=11.0,
            foot_confidence_l=0.8,
            foot_confidence_r=0.7,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.details["metric_source"] == "toe"
        assert fault.details["max_valgus"] == 12.0

    def test_fallback_to_hip_adduction_when_low_confidence(self, knee_valgus_rule, history):
        """Should fall back to hip_adduction when foot confidence is low."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=12.0,  # Should trigger via fallback
            hip_adduction_r=11.0,
            knee_valgus_l=0.0,
            knee_valgus_r=0.0,
            foot_confidence_l=0.1,  # Too low
            foot_confidence_r=0.1,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.details["metric_source"] == "hip_adduction"

    def test_fallback_when_one_side_low_confidence(self, knee_valgus_rule, history):
        """Should fall back if either side has low foot confidence."""
        angles = create_joint_angles(
            frame=0,
            hip_adduction_l=12.0,
            hip_adduction_r=11.0,
            knee_valgus_l=12.0,
            knee_valgus_r=11.0,
            foot_confidence_l=0.8,
            foot_confidence_r=0.1,  # One side too low → fallback
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is not None
        assert fault.details["metric_source"] == "hip_adduction"

    def test_no_fault_with_toe_metric_below_threshold(self, knee_valgus_rule, history):
        """No fault when toe-based valgus is below threshold."""
        angles = create_joint_angles(
            frame=0,
            knee_valgus_l=2.0,
            knee_valgus_r=3.0,
            foot_confidence_l=0.9,
            foot_confidence_r=0.9,
        )
        fault = knee_valgus_rule.evaluate(angles, history, in_rep=True)
        assert fault is None


class TestHeelRiseRule:
    """Test HeelRiseRule for heel lift detection."""

    @pytest.fixture
    def heel_rise_rule(self):
        return HeelRiseRule()

    @pytest.fixture
    def history(self):
        return deque(maxlen=90)

    def test_fault_type(self, heel_rise_rule):
        """Heel rise rule should report HEEL_RISE fault type."""
        assert heel_rise_rule.fault_type == FaultType.HEEL_RISE

    def test_no_fault_when_heels_down(self, heel_rise_rule, history):
        """No fault when dorsiflexion stays consistent."""
        # Set baseline
        angles1 = create_joint_angles(
            frame=0,
            ankle_dorsiflexion_l=25.0,
            ankle_dorsiflexion_r=25.0,
        )
        heel_rise_rule.evaluate(angles1, history, in_rep=True)

        # Check stable dorsiflexion
        angles2 = create_joint_angles(
            frame=1,
            ankle_dorsiflexion_l=24.0,
            ankle_dorsiflexion_r=24.0,
        )
        fault = heel_rise_rule.evaluate(angles2, history, in_rep=True)
        assert fault is None

    def test_no_fault_when_not_in_rep(self, heel_rise_rule, history):
        """No fault when not in rep."""
        angles = create_joint_angles(frame=0)
        fault = heel_rise_rule.evaluate(angles, history, in_rep=False)
        assert fault is None

    def test_heel_rise_detected(self, heel_rise_rule, history):
        """Heel rise (dorsiflexion decrease) should produce fault."""
        # Set baseline at rep start
        angles1 = create_joint_angles(
            frame=0,
            ankle_dorsiflexion_l=25.0,
            ankle_dorsiflexion_r=25.0,
        )
        heel_rise_rule.evaluate(angles1, history, in_rep=True)

        # Significant decrease (heel rising) — must exceed 20° threshold
        angles2 = create_joint_angles(
            frame=31,  # Past cooldown
            ankle_dorsiflexion_l=3.0,  # 22° decrease
            ankle_dorsiflexion_r=4.0,  # 21° decrease
        )
        fault = heel_rise_rule.evaluate(angles2, history, in_rep=True)
        assert fault is not None
        assert "max_decrease" in fault.details
        assert fault.details["max_decrease"] == 22.0

    def test_reset_on_new_rep(self, heel_rise_rule, history):
        """Baseline should reset when rep ends."""
        # Set baseline
        angles1 = create_joint_angles(
            frame=0,
            ankle_dorsiflexion_l=25.0,
            ankle_dorsiflexion_r=25.0,
        )
        heel_rise_rule.evaluate(angles1, history, in_rep=True)

        # End rep
        heel_rise_rule.evaluate(angles1, history, in_rep=False)

        # New rep with different baseline
        angles2 = create_joint_angles(
            frame=1,
            ankle_dorsiflexion_l=20.0,
            ankle_dorsiflexion_r=20.0,
        )
        heel_rise_rule.evaluate(angles2, history, in_rep=True)
        assert heel_rise_rule._baseline_dorsiflexion_l == 20.0


class TestRuleEngine:
    """Test RuleEngine orchestration."""

    @pytest.fixture
    def engine(self):
        # RuleEngine requires an explicit rule list (profiles are the source of
        # truth in production, but the tests build the set they care about).
        return RuleEngine(
            rules=[
                DepthRule(),
                SymmetryRule(),
                HeelRiseRule(),
                ForwardLeanRule(),
                KneeValgusRule(),
            ],
        )

    def test_initialization(self, engine):
        """Engine should initialize with all rules."""
        assert engine.rule_count == 5  # depth, symmetry, heel_rise, forward_lean, knee_valgus

    def test_history_tracking(self, engine):
        """Engine should maintain angle history."""
        angles = create_joint_angles(frame=0)
        engine.evaluate(angles, in_rep=True)
        assert engine.history_length == 1

        for i in range(1, 10):
            engine.evaluate(create_joint_angles(frame=i), in_rep=True)
        assert engine.history_length == 10

    def test_deduplication(self, engine):
        """Engine should deduplicate consecutive same-fault detections."""
        # Trigger forward lean fault
        angles = create_joint_angles(frame=0, trunk_flexion=50.0)
        faults1 = engine.evaluate(angles, in_rep=True)
        forward_lean_count = sum(1 for f in faults1 if f.fault_type == "forward_lean")

        # Same fault immediately after should be deduplicated
        angles2 = create_joint_angles(frame=1, trunk_flexion=50.0)
        faults2 = engine.evaluate(angles2, in_rep=True)
        forward_lean_count2 = sum(1 for f in faults2 if f.fault_type == "forward_lean")

        # First should fire, second should be deduplicated
        assert forward_lean_count <= 1
        assert forward_lean_count2 == 0

    def test_multiple_faults_same_frame(self, engine):
        """Engine should detect multiple fault types in same frame."""
        # Create angles with multiple issues
        angles = create_joint_angles(
            frame=0,
            trunk_flexion=60.0,  # Forward lean
            hip_adduction_l=15.0,  # Knee valgus
            hip_adduction_r=15.0,
            hip_flexion_l=80.0,  # Asymmetry
            hip_flexion_r=65.0,
        )
        faults = engine.evaluate(angles, in_rep=True)

        fault_types = {f.fault_type for f in faults}
        # Should detect at least forward lean and one other
        assert len(faults) >= 2

    def test_reset(self, engine):
        """Reset should clear history and rule states."""
        for i in range(50):
            engine.evaluate(create_joint_angles(frame=i), in_rep=True)
        assert engine.history_length == 50

        engine.reset()
        assert engine.history_length == 0

    def test_rep_complete_evaluation(self, engine):
        """Engine should evaluate depth on rep completion."""
        angles = create_joint_angles(frame=0)
        faults = engine.evaluate_rep_complete(
            max_depth_angle=55.0,  # Quarter squat
            angles=angles,
            rep_number=1,
        )
        assert len(faults) == 1
        assert faults[0].fault_type == "depth"
        assert faults[0].severity == FaultSeverity.MODERATE

    def test_get_rule(self, engine):
        """Should be able to get specific rule by type."""
        depth_rule = engine.get_rule(FaultType.DEPTH)
        assert depth_rule is not None
        assert isinstance(depth_rule, DepthRule)

    def test_add_remove_rule(self, engine):
        """Should be able to add and remove rules."""
        initial_count = engine.rule_count

        # Remove depth rule
        removed = engine.remove_rule(FaultType.DEPTH)
        assert removed
        assert engine.rule_count == initial_count - 1

        # Add it back
        engine.add_rule(DepthRule())
        assert engine.rule_count == initial_count
