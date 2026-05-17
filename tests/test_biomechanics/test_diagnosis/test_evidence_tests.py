"""Tests for evidence test functions — verifies outputs are in [0,1] and
respond correctly to extreme/normal inputs."""

import pytest

from biomechanics.diagnosis.graph import evidence_tests
from biomechanics.diagnosis.types import RepKinematicSummary


def _make_rep(**overrides) -> RepKinematicSummary:
    defaults = {
        "rep_number": 1,
        "trunk_pitch_at_bottom": 35.0,
        "knee_valgus_l": 3.0,
        "knee_valgus_r": 3.0,
        "ankle_df_l_max": 25.0,
        "ankle_df_r_max": 25.0,
        "hip_y_l_at_bottom": 40.0,
        "hip_y_r_at_bottom": 40.0,
        "knee_y_l_at_bottom": 42.0,
        "knee_y_r_at_bottom": 42.0,
        "stance_width_ratio": 1.0,
        "foot_direction_angle_l": 20.0,
        "foot_direction_angle_r": 20.0,
        "depth_class_int": 3,
    }
    defaults.update(overrides)
    return RepKinematicSummary(**defaults)


NORMAL_ANTHRO = {
    "femur_torso_ratio": 1.0,
    "femur_length_avg": 0.45,
    "tibia_length_avg": 0.43,
    "torso_length": 0.45,
    "hip_width": 0.30,
    "shoulder_width": 0.40,
}

NORMAL_ROM = {
    "dorsiflexion_drop": 35.0,
    "avg_depth": 120.0,
    "trunk_flexion": 60.0,
    "hip_adduction": 15.0,
    "asymmetry": 5.0,
}


class TestOutputRange:
    """All evidence functions must return float in [0, 1]."""

    @pytest.fixture
    def normal_rep(self):
        return _make_rep()

    @pytest.fixture
    def extreme_rep(self):
        return _make_rep(
            trunk_pitch_at_bottom=55.0,
            knee_valgus_l=15.0,
            knee_valgus_r=14.0,
            ankle_df_l_max=34.0,
            ankle_df_r_max=33.0,
            hip_y_l_at_bottom=45.0,
            hip_y_r_at_bottom=38.0,
            stance_width_ratio=0.6,
            foot_direction_angle_l=5.0,
            foot_direction_angle_r=5.0,
            depth_class_int=1,
        )

    @pytest.mark.parametrize(
        "fn_name",
        [
            "test_femur_torso_ratio",
            "test_narrow_stance",
            "test_narrow_foot_angle",
            "test_bracing_failure",
            "test_knee_track_cue",
            "test_weight_shift",
            "test_depth_unfamiliarity",
            "test_progressive_degradation",
            "test_limited_ankle_df",
            "test_limited_hip_flexion",
            "test_weak_hip_abductors",
            "test_foot_arch_collapse",
            "test_unilateral_hip",
        ],
    )
    def test_output_in_range_normal(self, fn_name, normal_rep):
        func = getattr(evidence_tests, fn_name)
        result = func(normal_rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert 0.0 <= result <= 1.0, f"{fn_name} returned {result}"

    @pytest.mark.parametrize(
        "fn_name",
        [
            "test_femur_torso_ratio",
            "test_narrow_stance",
            "test_narrow_foot_angle",
            "test_bracing_failure",
            "test_knee_track_cue",
            "test_weight_shift",
            "test_depth_unfamiliarity",
            "test_progressive_degradation",
            "test_limited_ankle_df",
            "test_limited_hip_flexion",
            "test_weak_hip_abductors",
            "test_foot_arch_collapse",
            "test_unilateral_hip",
        ],
    )
    def test_output_in_range_extreme(self, fn_name, extreme_rep):
        func = getattr(evidence_tests, fn_name)
        result = func(extreme_rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert 0.0 <= result <= 1.0, f"{fn_name} returned {result}"


class TestSpecificBehavior:
    def test_femur_torso_ratio_high_ratio_gives_high_evidence(self):
        rep = _make_rep()
        long_femur_anthro = {**NORMAL_ANTHRO, "femur_torso_ratio": 1.2}
        result = evidence_tests.test_femur_torso_ratio(
            rep, long_femur_anthro, NORMAL_ROM
        )
        assert result >= 0.8

    def test_femur_torso_ratio_normal_gives_zero(self):
        rep = _make_rep()
        result = evidence_tests.test_femur_torso_ratio(
            rep, NORMAL_ANTHRO, NORMAL_ROM
        )
        assert result == 0.0

    def test_narrow_stance_narrow_gives_high_evidence(self):
        rep = _make_rep(stance_width_ratio=0.55)
        result = evidence_tests.test_narrow_stance(rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert result >= 0.5

    def test_narrow_stance_wide_gives_zero(self):
        rep = _make_rep(stance_width_ratio=1.2)
        result = evidence_tests.test_narrow_stance(rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert result == 0.0

    def test_narrow_foot_angle_low_angle_gives_high_evidence(self):
        rep = _make_rep(foot_direction_angle_l=5.0, foot_direction_angle_r=5.0)
        result = evidence_tests.test_narrow_foot_angle(
            rep, NORMAL_ANTHRO, NORMAL_ROM
        )
        assert result >= 0.5

    def test_narrow_foot_angle_adequate_gives_zero(self):
        rep = _make_rep(
            foot_direction_angle_l=25.0, foot_direction_angle_r=25.0
        )
        result = evidence_tests.test_narrow_foot_angle(
            rep, NORMAL_ANTHRO, NORMAL_ROM
        )
        assert result == 0.0

    def test_limited_ankle_df_at_rom_ceiling(self):
        rep = _make_rep(ankle_df_l_max=34.0, ankle_df_r_max=33.0)
        rom = {**NORMAL_ROM, "dorsiflexion_drop": 35.0}
        result = evidence_tests.test_limited_ankle_df(rep, NORMAL_ANTHRO, rom)
        assert result >= 0.7

    def test_limited_ankle_df_well_below_ceiling(self):
        rep = _make_rep(ankle_df_l_max=20.0, ankle_df_r_max=20.0)
        rom = {**NORMAL_ROM, "dorsiflexion_drop": 35.0}
        result = evidence_tests.test_limited_ankle_df(rep, NORMAL_ANTHRO, rom)
        assert result == 0.0

    def test_unilateral_hip_large_asymmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=38.0)
        result = evidence_tests.test_unilateral_hip(rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert result >= 0.7

    def test_unilateral_hip_symmetric(self):
        rep = _make_rep(hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.5)
        result = evidence_tests.test_unilateral_hip(rep, NORMAL_ANTHRO, NORMAL_ROM)
        assert result == 0.0


class TestExpectedValueFunctions:
    def test_trunk_lean_increases_with_femur_ratio(self):
        lean_normal = evidence_tests.expected_trunk_lean_geometric(
            {"femur_torso_ratio": 1.0}
        )
        lean_long = evidence_tests.expected_trunk_lean_geometric(
            {"femur_torso_ratio": 1.2}
        )
        assert lean_long > lean_normal
        assert lean_normal == pytest.approx(30.0)

    def test_knee_valgus_baseline_returns_small_value(self):
        result = evidence_tests.expected_knee_valgus_baseline(NORMAL_ANTHRO)
        assert 0.0 <= result <= 5.0

    def test_hip_symmetry_expected_is_zero(self):
        assert evidence_tests.expected_hip_symmetry(NORMAL_ANTHRO) == 0.0

    def test_depth_zero_expected_is_zero(self):
        assert evidence_tests.expected_depth_zero(NORMAL_ANTHRO) == 0.0
