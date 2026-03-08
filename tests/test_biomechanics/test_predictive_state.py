"""Tests for predictive fault pre-cueing state estimator."""

import pytest

from biomechanics.utils.predictive_state import PredictiveStateEstimator
from biomechanics.utils.types import JointAngles
from biomechanics.utils.derivatives import AngleDerivatives


def _make_angles(**kwargs) -> JointAngles:
    """Helper to create JointAngles with defaults overridden."""
    return JointAngles(**kwargs)


def _make_derivatives(**kwargs) -> AngleDerivatives:
    """Helper to create AngleDerivatives with defaults overridden."""
    return AngleDerivatives(**kwargs)


class TestPredictiveStateEstimator:

    def test_zero_velocity_unchanged(self):
        """Zero velocities should produce identical angles."""
        estimator = PredictiveStateEstimator(horizon_seconds=0.2)
        angles = _make_angles(
            knee_flexion_l=45.0, knee_flexion_r=44.0,
            hip_flexion_l=30.0, hip_flexion_r=31.0,
            trunk_flexion=10.0,
        )
        derivatives = _make_derivatives()  # All zeros

        predicted = estimator.predict(angles, derivatives)

        assert predicted.knee_flexion_l == pytest.approx(45.0)
        assert predicted.knee_flexion_r == pytest.approx(44.0)
        assert predicted.hip_flexion_l == pytest.approx(30.0)
        assert predicted.hip_flexion_r == pytest.approx(31.0)
        assert predicted.trunk_flexion == pytest.approx(10.0)

    def test_positive_velocity_extrapolation(self):
        """Positive knee velocity should increase predicted knee angle."""
        estimator = PredictiveStateEstimator(
            horizon_seconds=0.2, max_extrapolation_deg=25.0
        )
        angles = _make_angles(knee_flexion_l=50.0)
        derivatives = _make_derivatives(knee_velocity_l=100.0)  # 100 deg/s

        predicted = estimator.predict(angles, derivatives)

        # 50 + 100 * 0.2 = 70 (within 25 deg clamp)
        assert predicted.knee_flexion_l == pytest.approx(70.0)

    def test_negative_velocity_extrapolation(self):
        """Negative hip velocity should decrease predicted hip angle."""
        estimator = PredictiveStateEstimator(horizon_seconds=0.2)
        angles = _make_angles(hip_flexion_r=40.0)
        derivatives = _make_derivatives(hip_velocity_r=-50.0)  # -50 deg/s

        predicted = estimator.predict(angles, derivatives)

        # 40 + (-50) * 0.2 = 30
        assert predicted.hip_flexion_r == pytest.approx(30.0)

    def test_max_extrapolation_clamp(self):
        """Large velocity that would exceed max_extrapolation_deg gets clamped."""
        estimator = PredictiveStateEstimator(
            horizon_seconds=0.2, max_extrapolation_deg=15.0
        )
        angles = _make_angles(knee_flexion_l=50.0)
        derivatives = _make_derivatives(knee_velocity_l=200.0)  # 200*0.2 = 40 > 15

        predicted = estimator.predict(angles, derivatives)

        # Clamped: 50 + 15 = 65
        assert predicted.knee_flexion_l == pytest.approx(65.0)

        # Also test negative clamping
        angles_neg = _make_angles(knee_flexion_r=80.0)
        derivatives_neg = _make_derivatives(knee_velocity_r=-200.0)

        predicted_neg = estimator.predict(angles_neg, derivatives_neg)

        # Clamped: 80 + (-15) = 65
        assert predicted_neg.knee_flexion_r == pytest.approx(65.0)

    def test_untracked_angles_copied(self):
        """Angles without velocity tracking are copied unchanged."""
        estimator = PredictiveStateEstimator(horizon_seconds=0.2)
        angles = _make_angles(
            ankle_dorsiflexion_l=12.0,
            ankle_dorsiflexion_r=11.0,
            trunk_flexion=15.0,
            trunk_lateral_flexion=3.0,
            trunk_rotation=2.0,
            pelvis_tilt=8.0,
            pelvis_list=1.0,
            pelvis_rotation=0.5,
            hip_adduction_l=5.0,
            hip_adduction_r=4.0,
            hip_rotation_l=3.0,
            hip_rotation_r=2.0,
        )
        # Give some non-zero velocities to tracked angles
        derivatives = _make_derivatives(knee_velocity_l=100.0, hip_velocity_r=50.0)

        predicted = estimator.predict(angles, derivatives)

        # All untracked angles should be identical to input
        assert predicted.ankle_dorsiflexion_l == pytest.approx(12.0)
        assert predicted.ankle_dorsiflexion_r == pytest.approx(11.0)
        assert predicted.trunk_flexion == pytest.approx(15.0)
        assert predicted.trunk_lateral_flexion == pytest.approx(3.0)
        assert predicted.trunk_rotation == pytest.approx(2.0)
        assert predicted.pelvis_tilt == pytest.approx(8.0)
        assert predicted.pelvis_list == pytest.approx(1.0)
        assert predicted.pelvis_rotation == pytest.approx(0.5)
        assert predicted.hip_adduction_l == pytest.approx(5.0)
        assert predicted.hip_adduction_r == pytest.approx(4.0)
        assert predicted.hip_rotation_l == pytest.approx(3.0)
        assert predicted.hip_rotation_r == pytest.approx(2.0)

    def test_metadata_preserved(self):
        """timestamp and frame_index should match input angles."""
        estimator = PredictiveStateEstimator()
        angles = _make_angles(timestamp=1.234, frame_index=42)
        derivatives = _make_derivatives(knee_velocity_l=50.0)

        predicted = estimator.predict(angles, derivatives)

        assert predicted.timestamp == pytest.approx(1.234)
        assert predicted.frame_index == 42
