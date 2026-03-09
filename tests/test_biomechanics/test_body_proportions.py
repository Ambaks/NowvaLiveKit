"""Tests for body proportion computation and fault threshold scaling."""

import numpy as np
import pytest

from biomechanics.utils.bone_constraints import (
    BoneLengthConstraints,
    BodyProportions,
    REFERENCE_HIP_TO_FEMUR_RATIO,
    REFERENCE_TIBIA_LENGTH_M,
)
from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK
from biomechanics.faults.rule_engine import RuleEngine
from biomechanics.faults.rules.knee_valgus import KneeValgusRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule


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
    points = np.zeros((17, 3))
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

    def test_long_tibia_increases_heel_rise_scale(self):
        """Longer tibia should produce heel_rise_scale > 1."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Extend tibias: knee at 0.60, ankle at 0.0 → tibia = 0.60m
        pts[CK.LEFT_KNEE] = [0.10, 0.60, 0.0]
        pts[CK.LEFT_ANKLE] = [0.10, 0.0, 0.0]
        pts[CK.RIGHT_KNEE] = [-0.10, 0.60, 0.0]
        pts[CK.RIGHT_ANKLE] = [-0.10, 0.0, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        assert bc.body_proportions.heel_rise_scale > 1.0

    def test_heel_rise_scale_clamped(self):
        """Extreme tibia should be clamped to [0.8, 1.2]."""
        bc = BoneLengthConstraints(calibration_frames=5)
        pts = _standing_skeleton()
        # Extremely long tibias
        pts[CK.LEFT_KNEE] = [0.10, 1.00, 0.0]
        pts[CK.LEFT_ANKLE] = [0.10, 0.0, 0.0]
        pts[CK.RIGHT_KNEE] = [-0.10, 1.00, 0.0]
        pts[CK.RIGHT_ANKLE] = [-0.10, 0.0, 0.0]

        for i in range(5):
            bc.enforce(_make_skeleton(pts, frame_index=i))

        assert bc.body_proportions.heel_rise_scale == pytest.approx(1.2)


class TestStandingGateBlocksCalibration:

    def test_gate_blocks_calibration(self):
        """Calibration frames should not count until gate passes."""
        gate = StandingPoseGate(required_consecutive_frames=3)
        bc = BoneLengthConstraints(calibration_frames=5, standing_gate=gate)

        bad_pts = _standing_skeleton()
        bad_pts[CK.LEFT_KNEE] = [0.10, 0.70, 0.30]  # bent knee

        # 10 frames with bad pose — gate doesn't pass, calibration doesn't advance
        for i in range(10):
            bc.enforce(_make_skeleton(bad_pts, frame_index=i))

        assert not gate.is_ready
        assert not bc.is_calibrated

    def test_calibration_proceeds_after_gate(self):
        """After the gate passes, calibration proceeds normally."""
        gate = StandingPoseGate(required_consecutive_frames=2)
        bc = BoneLengthConstraints(calibration_frames=5, standing_gate=gate)
        good_pts = _standing_skeleton()

        # 2 frames to pass gate + 5 frames for calibration = 7 total
        for i in range(7):
            bc.enforce(_make_skeleton(good_pts, frame_index=i))

        assert gate.is_ready
        assert bc.is_calibrated
        assert bc.body_proportions is not None


class TestRuleEngineProportionScaling:

    def test_valgus_thresholds_scaled(self):
        engine = RuleEngine()

        proportions = BodyProportions(
            hip_width=0.30,
            femur_length_avg=0.45,
            tibia_length_avg=0.45,
            torso_length_avg=0.50,
            hip_to_femur_ratio=0.667,
            tibia_to_reference_ratio=1.0,
            valgus_scale=1.2,
            heel_rise_scale=1.0,
        )

        engine.apply_body_proportion_scaling(proportions)

        valgus_rule = engine.get_rule(
            __import__("biomechanics.faults.fault_types", fromlist=["FaultType"]).FaultType.KNEE_VALGUS
        )
        assert valgus_rule.mild_threshold == pytest.approx(8.0 * 1.2, abs=0.1)
        assert valgus_rule.moderate_threshold == pytest.approx(13.0 * 1.2, abs=0.1)
        assert valgus_rule.severe_threshold == pytest.approx(18.0 * 1.2, abs=0.1)

    def test_heel_rise_threshold_scaled(self):
        engine = RuleEngine()

        proportions = BodyProportions(
            hip_width=0.20,
            femur_length_avg=0.45,
            tibia_length_avg=0.54,
            torso_length_avg=0.50,
            hip_to_femur_ratio=0.444,
            tibia_to_reference_ratio=1.2,
            valgus_scale=1.0,
            heel_rise_scale=1.2,
        )

        engine.apply_body_proportion_scaling(proportions)

        heel_rule = engine.get_rule(
            __import__("biomechanics.faults.fault_types", fromlist=["FaultType"]).FaultType.HEEL_RISE
        )
        # Default threshold = 3.0 * 5 = 15.0, scaled by 1.2 = 18.0
        assert heel_rule.threshold_degrees == pytest.approx(15.0 * 1.2, abs=0.1)
