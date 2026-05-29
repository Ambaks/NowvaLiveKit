"""Tests for per-rep quality scoring."""

import pytest

from biomechanics.diagnosis.rep_scoring import (
    score_ankle_utilization,
    score_depth,
    score_knee_tracking,
    score_rep,
    score_set,
    score_symmetry,
    score_trunk_control,
)
from biomechanics.diagnosis.types import RepKinematicSummary


def _make_rep(**overrides) -> RepKinematicSummary:
    defaults = dict(
        rep_number=1,
        trunk_pitch_at_bottom=35.0,
        knee_valgus_l=0.0,
        knee_valgus_r=0.0,
        ankle_df_l_max=20.0,
        ankle_df_r_max=20.0,
        hip_y_l_at_bottom=40.0,
        hip_y_r_at_bottom=40.0,
        knee_y_l_at_bottom=45.0,
        knee_y_r_at_bottom=45.0,
        stance_width_ratio=1.0,
        foot_direction_angle_l=20.0,
        foot_direction_angle_r=20.0,
        depth_class_int=4,
    )
    defaults.update(overrides)
    return RepKinematicSummary(**defaults)


def _default_anthro() -> dict:
    return {
        "femur_torso_ratio": 1.0,
        "hip_width": 0.30,
        "shoulder_width": 0.40,
    }


def _default_rom() -> dict:
    return {
        "dorsiflexion_drop": 35.0,
        "avg_depth": 120.0,
    }


class TestDepthScore:
    def test_below_parallel_with_hip_below_knee(self):
        rep = _make_rep(depth_class_int=4, hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.0,
                        knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0)
        assert score_depth(rep, _default_anthro(), _default_rom()) == 1.0

    def test_parallel_no_bonus(self):
        rep = _make_rep(depth_class_int=3, hip_y_l_at_bottom=50.0, hip_y_r_at_bottom=50.0,
                        knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0)
        assert score_depth(rep, _default_anthro(), _default_rom()) == 0.85

    def test_parallel_with_bonus(self):
        rep = _make_rep(depth_class_int=3, hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.0,
                        knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0)
        assert score_depth(rep, _default_anthro(), _default_rom()) == 1.0

    def test_quarter_squat(self):
        rep = _make_rep(depth_class_int=0, hip_y_l_at_bottom=60.0, hip_y_r_at_bottom=60.0,
                        knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0)
        assert score_depth(rep, _default_anthro(), _default_rom()) == 0.1

    def test_half_squat(self):
        rep = _make_rep(depth_class_int=1, hip_y_l_at_bottom=55.0, hip_y_r_at_bottom=55.0,
                        knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0)
        assert score_depth(rep, _default_anthro(), _default_rom()) == 0.25


class TestTrunkControlScore:
    def test_perfect_lean(self):
        expected_lean = 30.0  # femur_torso_ratio=1.0 → 30 + (1.0-1.0)*120 = 30
        rep = _make_rep(trunk_pitch_at_bottom=30.0)
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 1.0

    def test_within_tolerance(self):
        rep = _make_rep(trunk_pitch_at_bottom=33.0)
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 1.0

    def test_moderate_deviation(self):
        rep = _make_rep(trunk_pitch_at_bottom=43.0)  # 13° off → (13-3)/20 = 0.5 → 1-0.5 = 0.5
        score = score_trunk_control(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_extreme_deviation(self):
        rep = _make_rep(trunk_pitch_at_bottom=60.0)  # 30° off → clamped to 0
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 0.0


class TestKneeTrackingScore:
    def test_perfect_alignment(self):
        rep = _make_rep(knee_valgus_l=0.0, knee_valgus_r=0.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 1.0

    def test_within_perfect_zone(self):
        rep = _make_rep(knee_valgus_l=3.5, knee_valgus_r=-2.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 1.0

    def test_at_zone_boundary(self):
        rep = _make_rep(knee_valgus_l=4.0, knee_valgus_r=0.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 1.0

    def test_moderate_valgus(self):
        rep = _make_rep(knee_valgus_l=10.0, knee_valgus_r=2.0)  # worst=10, (10-4)/12=0.5
        score = score_knee_tracking(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_negative_valgus_same_as_positive(self):
        rep_positive = _make_rep(knee_valgus_l=8.0, knee_valgus_r=0.0)
        rep_negative = _make_rep(knee_valgus_l=-8.0, knee_valgus_r=0.0)
        score_pos = score_knee_tracking(rep_positive, _default_anthro(), _default_rom())
        score_neg = score_knee_tracking(rep_negative, _default_anthro(), _default_rom())
        assert score_pos == score_neg

    def test_extreme_valgus(self):
        rep = _make_rep(knee_valgus_l=16.0, knee_valgus_r=16.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 0.0


class TestSymmetryScore:
    def test_perfect_symmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.0)
        assert score_symmetry(rep, _default_anthro(), _default_rom()) == 1.0

    def test_within_tolerance(self):
        rep = _make_rep(hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.8)
        assert score_symmetry(rep, _default_anthro(), _default_rom()) == 1.0

    def test_moderate_asymmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=43.5)  # 3.5cm → (3.5-1)/5=0.5
        score = score_symmetry(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_extreme_asymmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=46.0)  # 6cm → 0
        assert score_symmetry(rep, _default_anthro(), _default_rom()) == 0.0


class TestAnkleUtilizationScore:
    def test_ideal_utilization(self):
        rom = {"dorsiflexion_drop": 35.0}
        rep = _make_rep(ankle_df_l_max=22.0, ankle_df_r_max=22.0)  # 62.9% → in [50, 85]
        assert score_ankle_utilization(rep, _default_anthro(), rom) == 1.0

    def test_low_utilization(self):
        rom = {"dorsiflexion_drop": 40.0}
        rep = _make_rep(ankle_df_l_max=5.0, ankle_df_r_max=5.0)  # 12.5% → 0.125/0.5=0.25
        score = score_ankle_utilization(rep, _default_anthro(), rom)
        assert score == pytest.approx(0.25, abs=0.01)

    def test_maxed_out(self):
        rom = {"dorsiflexion_drop": 35.0}
        rep = _make_rep(ankle_df_l_max=35.0, ankle_df_r_max=35.0)  # 100% → 0
        assert score_ankle_utilization(rep, _default_anthro(), rom) == 0.0

    def test_zero_capacity_guarded(self):
        rom = {"dorsiflexion_drop": 0.0}
        rep = _make_rep(ankle_df_l_max=10.0, ankle_df_r_max=10.0)
        score = score_ankle_utilization(rep, _default_anthro(), rom)
        assert 0.0 <= score <= 1.0


class TestCompositeScore:
    def test_perfect_rep(self):
        rep = _make_rep(
            trunk_pitch_at_bottom=30.0,
            knee_valgus_l=0.0, knee_valgus_r=0.0,
            hip_y_l_at_bottom=40.0, hip_y_r_at_bottom=40.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
            depth_class_int=4,
            ankle_df_l_max=22.0, ankle_df_r_max=22.0,
        )
        result = score_rep(rep, _default_anthro(), _default_rom())
        assert result.composite_score >= 0.95

    def test_all_scores_bounded(self):
        rep = _make_rep()
        result = score_rep(rep, _default_anthro(), _default_rom())
        assert 0.0 <= result.depth_score <= 1.0
        assert 0.0 <= result.trunk_control_score <= 1.0
        assert 0.0 <= result.knee_tracking_score <= 1.0
        assert 0.0 <= result.symmetry_score <= 1.0
        assert 0.0 <= result.ankle_utilization_score <= 1.0
        assert 0.0 <= result.composite_score <= 1.0

    def test_weights_sum_to_one(self):
        from biomechanics.diagnosis.rep_scoring import (
            WEIGHT_ANKLES,
            WEIGHT_DEPTH,
            WEIGHT_KNEES,
            WEIGHT_SYMMETRY,
            WEIGHT_TRUNK,
        )
        total = WEIGHT_DEPTH + WEIGHT_TRUNK + WEIGHT_KNEES + WEIGHT_SYMMETRY + WEIGHT_ANKLES
        assert total == pytest.approx(1.0)


class TestSetScoreSummary:
    def test_best_and_worst_identification(self):
        good_rep = _make_rep(rep_number=2, depth_class_int=4, trunk_pitch_at_bottom=30.0,
                             knee_valgus_l=0.0, knee_valgus_r=0.0)
        bad_rep = _make_rep(rep_number=3, depth_class_int=0, trunk_pitch_at_bottom=55.0,
                            knee_valgus_l=14.0, knee_valgus_r=12.0,
                            hip_y_l_at_bottom=60.0, hip_y_r_at_bottom=60.0)
        result = score_set([good_rep, bad_rep], _default_anthro(), _default_rom())
        assert result.best_rep_number == 2
        assert result.worst_rep_number == 3

    def test_single_rep_slope_zero(self):
        rep = _make_rep(rep_number=2)
        result = score_set([rep], _default_anthro(), _default_rom())
        assert result.trend_slope == 0.0

    def test_degrading_trend_negative_slope(self):
        reps = [
            _make_rep(rep_number=2, depth_class_int=4, trunk_pitch_at_bottom=30.0),
            _make_rep(rep_number=3, depth_class_int=3, trunk_pitch_at_bottom=35.0),
            _make_rep(rep_number=4, depth_class_int=1, trunk_pitch_at_bottom=50.0,
                      knee_valgus_l=12.0),
        ]
        result = score_set(reps, _default_anthro(), _default_rom())
        assert result.trend_slope < 0

    def test_mean_score_computed(self):
        rep_a = _make_rep(rep_number=2)
        rep_b = _make_rep(rep_number=3)
        result = score_set([rep_a, rep_b], _default_anthro(), _default_rom())
        score_a = result.per_rep_scores[0].composite_score
        score_b = result.per_rep_scores[1].composite_score
        expected_mean = (score_a + score_b) / 2.0
        assert result.mean_score == pytest.approx(expected_mean, abs=0.01)
