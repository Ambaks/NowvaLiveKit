"""Tests for body proportion computation and fault threshold scaling."""

import numpy as np
import pytest

from biomechanics.utils.bone_constraints import (
    BoneLengthConstraints,
    BodyProportions,
    REFERENCE_HIP_TO_FEMUR_RATIO,
    REFERENCE_TIBIA_LENGTH_M,
    REFERENCE_FEMUR_TO_TORSO,
)
from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK
from biomechanics.faults.rule_engine import RuleEngine
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.fault_types import FaultType
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver


def _make_skeleton(
    positions: np.ndarray,
    confidences: np.ndarray | None = None,
    timestamp: float = 0.0,
    frame_index: int = 0,
) -> Skeleton3D:
    if confidences is None:
        confidences = np.ones(len(positions))
    return Skeleton3D.from_numpy(
        positions, confidences=confidences,
        timestamp=timestamp, frame_index=frame_index,
    )


def _standing_skeleton() -> np.ndarray:
    points = np.zeros((19, 3))
    points[CK.NOSE] = [0.0, 1.70, 0.0]
    points[CK.LEFT_EYE] = [0.03, 1.72, -0.02]
    points[CK.RIGHT_EYE] = [-0.03, 1.72, -0.02]
    points[CK.LEFT_EAR] = [0.07, 1.70, 0.0]
    points[CK.RIGHT_EAR] = [-0.07, 1.70, 0.0]
    points[CK.LEFT_SHOULDER] = [0.20, 1.50, 0.0]
    points[CK.RIGHT_SHOULDER] = [-0.20, 1.50, 0.0]
    points[CK.LEFT_HIP] = [0.10, 1.00, 0.0]
    points[CK.RIGHT_HIP] = [-0.10, 1.00, 0.0]
    points[CK.LEFT_ELBOW] = [0.25, 1.25, 0.0]
    points[CK.LEFT_WRIST] = [0.25, 1.00, 0.0]
    points[CK.RIGHT_ELBOW] = [-0.25, 1.25, 0.0]
    points[CK.RIGHT_WRIST] = [-0.25, 1.00, 0.0]
    points[CK.LEFT_KNEE] = [0.10, 0.55, 0.0]
    points[CK.LEFT_ANKLE] = [0.10, 0.10, 0.0]
    points[CK.RIGHT_KNEE] = [-0.10, 0.55, 0.0]
    points[CK.RIGHT_ANKLE] = [-0.10, 0.10, 0.0]
    points[CK.LEFT_FOOT_INDEX] = [0.10, 0.05, 0.10]
    points[CK.RIGHT_FOOT_INDEX] = [-0.10, 0.05, 0.10]
    return points


class TestBodyProportions:

    def test_proportions_computed_after_calibration(self):
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()

        assert bc.body_proportions is None

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        assert bc.is_calibrated
        assert bc.body_proportions is not None

    def test_correct_ratio_computation(self):
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()

        # hip_width = dist(LEFT_HIP, RIGHT_HIP) = dist([0.10, 1.0, 0], [-0.10, 1.0, 0]) = 0.20
        # femur_l = dist(LEFT_HIP, LEFT_KNEE) = dist([0.10, 1.0, 0], [0.10, 0.55, 0]) = 0.45
        # femur_r = dist(RIGHT_HIP, RIGHT_KNEE) = 0.45
        # tibia_l = dist(LEFT_KNEE, LEFT_ANKLE) = dist([0.10, 0.55, 0], [0.10, 0.10, 0]) = 0.45
        # tibia_r = 0.45

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        assert p.hip_width == pytest.approx(0.20, abs=1e-3)
        assert p.femur_length_avg == pytest.approx(0.45, abs=1e-3)
        assert p.tibia_length_avg == pytest.approx(0.45, abs=1e-3)
        assert p.hip_to_femur_ratio == pytest.approx(0.20 / 0.45, abs=1e-3)
        assert p.tibia_to_reference_ratio == pytest.approx(0.45 / 0.45, abs=1e-3)

    def test_wide_hips_increase_valgus_scale(self):
        """Wider-than-average hips should produce valgus_scale > 1."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Widen hips: move from ±0.10 to ±0.25 (hip_width = 0.50)
        pts[CK.LEFT_HIP] = [0.25, 1.00, 0.0]
        pts[CK.RIGHT_HIP] = [-0.25, 1.00, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        # hip_to_femur = 0.50 / femur_avg, which is > reference 0.556
        assert p.valgus_scale > 1.0

    def test_narrow_hips_decrease_valgus_scale(self):
        """Narrower-than-average hips should produce valgus_scale < 1."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Very narrow hips: ±0.04 (hip_width = 0.08)
        pts[CK.LEFT_HIP] = [0.04, 1.00, 0.0]
        pts[CK.RIGHT_HIP] = [-0.04, 1.00, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        assert p.valgus_scale < 1.0

    def test_valgus_scale_clamped(self):
        """Extreme proportions should be clamped to [0.7, 1.3]."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Extremely wide hips
        pts[CK.LEFT_HIP] = [0.50, 1.00, 0.0]
        pts[CK.RIGHT_HIP] = [-0.50, 1.00, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        assert bc.body_proportions.valgus_scale == pytest.approx(1.3)


class TestStandingGateBlocksCalibration:
    # The gate is advanced by the caller once per frame, exactly as the
    # pipeline does. enforce() only reads is_ready — it must never advance
    # the gate itself, or the required consecutive-frame count is reached in
    # a fraction of the frames it asks for.

    def test_gate_blocks_calibration(self):
        """Calibration frames should not count until gate passes."""
        gate = StandingPoseGate(required_consecutive_frames=3)
        bc = BoneLengthConstraints(calibration_frames=5, standing_gate=gate)

        bad_pts = _standing_skeleton()
        bad_pts[CK.LEFT_KNEE] = [0.35, 0.60, 0.0]  # bent knee (frontal plane)

        # 10 frames with bad pose — gate doesn't pass, calibration doesn't advance
        for i in range(10):
            skeleton = _make_skeleton(bad_pts, frame_index=i)
            gate.check(skeleton)
            bc.enforce(skeleton)

        assert not gate.is_ready
        assert not bc.is_calibrated

    def test_calibration_proceeds_after_gate(self):
        """After the gate passes, calibration proceeds normally."""
        gate = StandingPoseGate(required_consecutive_frames=2)
        bc = BoneLengthConstraints(calibration_frames=5, standing_gate=gate)
        good_pts = _standing_skeleton()

        # 2 frames to pass gate + 5 frames for calibration = 7 total
        for i in range(7):
            skeleton = _make_skeleton(good_pts, frame_index=i)
            gate.check(skeleton)
            bc.enforce(skeleton)

        assert gate.is_ready
        assert bc.is_calibrated
        assert bc.body_proportions is not None

    def test_enforce_does_not_advance_gate(self):
        """enforce() must not advance the gate — the pipeline owns that."""
        gate = StandingPoseGate(required_consecutive_frames=5)
        bc = BoneLengthConstraints(calibration_frames=5, standing_gate=gate)
        good_pts = _standing_skeleton()

        for i in range(4):
            skeleton = _make_skeleton(good_pts, frame_index=i)
            gate.check(skeleton)
            # Two enforce() calls per frame, as the pipeline does.
            bc.enforce(skeleton)
            bc.enforce(skeleton)

        assert gate.progress == (4, 5)
        assert not gate.is_ready


def _make_engine_with_squat_rules() -> RuleEngine:
    """Build an engine with the squat-profile rule set (config-driven defaults).

    The proportion-scaling assertions below depend on those config defaults,
    not on the bare-class defaults — the profile is what production uses.
    """
    from biomechanics.config import BiomechanicsConfig
    from biomechanics.profiles.squat import SquatProfile

    profile = SquatProfile()
    rules = profile.create_fault_rules(BiomechanicsConfig())
    return RuleEngine(rules=rules)


class TestRuleEngineProportionScaling:

    def test_valgus_thresholds_scaled(self):
        engine = _make_engine_with_squat_rules()

        proportions = BodyProportions(
            hip_width=0.30,
            femur_length_avg=0.45,
            tibia_length_avg=0.45,
            torso_length_avg=0.50,
            hip_to_femur_ratio=0.667,
            tibia_to_reference_ratio=1.0,
            valgus_scale=1.2,
            forward_lean_scale=1.0,
            pelvis_tilt_coupling=0.4,
        )

        engine.apply_body_proportion_scaling(proportions)

        valgus_rule = engine.get_rule(
            __import__("biomechanics.faults.fault_types", fromlist=["FaultType"]).FaultType.KNEE_VALGUS
        )
        # Single-camera (default) uses 2D FPPA thresholds: 6/10/16
        assert valgus_rule.mild_threshold == pytest.approx(6.0 * 1.2, abs=0.1)
        assert valgus_rule.moderate_threshold == pytest.approx(10.0 * 1.2, abs=0.1)
        assert valgus_rule.severe_threshold == pytest.approx(16.0 * 1.2, abs=0.1)

    def test_forward_lean_thresholds_scaled(self):
        engine = _make_engine_with_squat_rules()

        proportions = BodyProportions(
            hip_width=0.20,
            femur_length_avg=0.55,
            tibia_length_avg=0.45,
            torso_length_avg=0.50,
            hip_to_femur_ratio=0.364,
            tibia_to_reference_ratio=1.0,
            valgus_scale=1.0,
            forward_lean_scale=1.2,
            pelvis_tilt_coupling=0.4,
        )

        engine.apply_body_proportion_scaling(proportions)

        fwd_rule = engine.get_rule(FaultType.FORWARD_LEAN)
        # 180-convention defaults from FaultsConfig.forward_lean (mild=135,
        # moderate=125, severe=115) scaled by forward_lean_scale=1.2.
        assert fwd_rule.mild_threshold == pytest.approx(135.0 * 1.2, abs=0.1)
        assert fwd_rule.moderate_threshold == pytest.approx(125.0 * 1.2, abs=0.1)
        assert fwd_rule.severe_threshold == pytest.approx(115.0 * 1.2, abs=0.1)


class TestForwardLeanProportions:

    def test_long_femurs_increase_forward_lean_scale(self):
        """Long femurs relative to torso should produce forward_lean_scale > 1."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Lengthen femurs: move knees down → femur = 0.60m (torso stays ~0.54m)
        pts[CK.LEFT_KNEE] = [0.10, 0.40, 0.0]
        pts[CK.RIGHT_KNEE] = [-0.10, 0.40, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        # femur_to_torso = 0.60 / ~0.54 ≈ 1.11 > reference 0.90
        assert p.forward_lean_scale > 1.0

    def test_short_femurs_decrease_forward_lean_scale(self):
        """Short femurs relative to torso should produce forward_lean_scale < 1."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Shorten femurs: move knees up → femur = 0.30m
        pts[CK.LEFT_KNEE] = [0.10, 0.70, 0.0]
        pts[CK.RIGHT_KNEE] = [-0.10, 0.70, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        # femur_to_torso = 0.30 / ~0.54 ≈ 0.56 < reference 0.90
        assert p.forward_lean_scale < 1.0

    def test_forward_lean_scale_clamped(self):
        """Extreme proportions should be clamped to [0.8, 1.3]."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Extremely long femurs
        pts[CK.LEFT_KNEE] = [0.10, 0.0, 0.0]
        pts[CK.RIGHT_KNEE] = [-0.10, 0.0, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        assert bc.body_proportions.forward_lean_scale == pytest.approx(1.3)

    def test_pelvis_tilt_coupling_computed(self):
        """Pelvis tilt coupling should be in reasonable range."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        p = bc.body_proportions
        assert 0.30 <= p.pelvis_tilt_coupling <= 0.55


class TestIKSolverProportions:

    def test_pelvis_tilt_uses_default_coupling(self):
        """IK solver should use 0.4 coupling by default."""
        solver = AnalyticalIKSolver()
        assert solver._pelvis_tilt_coupling == pytest.approx(0.4)

    def test_pelvis_tilt_uses_custom_coupling(self):
        """IK solver should use custom coupling after set_body_proportions."""
        solver = AnalyticalIKSolver()

        proportions = BodyProportions(
            hip_width=0.30,
            femur_length_avg=0.45,
            tibia_length_avg=0.45,
            torso_length_avg=0.50,
            hip_to_femur_ratio=0.667,
            tibia_to_reference_ratio=1.0,
            valgus_scale=1.0,
            forward_lean_scale=1.0,
            pelvis_tilt_coupling=0.48,
        )

        solver.set_body_proportions(proportions)
        assert solver._pelvis_tilt_coupling == pytest.approx(0.48)


class TestForwardLeanRuleEnabled:

    def test_forward_lean_rule_in_engine(self):
        """ForwardLeanRule should be active in the squat-profile rule set."""
        engine = _make_engine_with_squat_rules()
        fwd_rule = engine.get_rule(FaultType.FORWARD_LEAN)
        assert fwd_rule is not None
        # Squat profile registers depth, symmetry, bar-tilt asymmetry,
        # forward lean, knee valgus = 5 rules.
        assert engine.rule_count == 5
