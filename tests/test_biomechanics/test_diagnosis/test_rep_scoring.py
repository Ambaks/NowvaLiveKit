"""Tests for per-rep quality scoring."""

import pytest

from biomechanics.diagnosis.rep_scoring import (
    LOADED_WINDOW_RATIO,
    score_depth,
    score_knee_tracking,
    score_rep,
    score_set,
    score_symmetry,
    score_tempo,
    score_trunk_control,
)
from biomechanics.diagnosis.types import (
    RepKinematicSummary,
    RepTrajectory,
    RepTrajectorySample,
)

# Femur length used across the fixtures, in the units each layer expects.
FEMUR_M = 0.40
FEMUR_CM = FEMUR_M * 100.0


def _make_rep(**overrides) -> RepKinematicSummary:
    defaults = dict(
        rep_number=1,
        trunk_pitch_at_bottom=35.0,
        knee_valgus_l=0.0,
        knee_valgus_r=0.0,
        ankle_df_l_max=20.0,
        ankle_df_r_max=20.0,
        hip_y_l_at_bottom=45.0,
        hip_y_r_at_bottom=45.0,
        knee_y_l_at_bottom=45.0,
        knee_y_r_at_bottom=45.0,
        stance_width_ratio=1.0,
        foot_direction_angle_l=20.0,
        foot_direction_angle_r=20.0,
        depth_class_int=4,
        descent_time_s=2.0,
        ascent_time_s=1.0,
    )
    defaults.update(overrides)
    return RepKinematicSummary(**defaults)


def _make_sample(**overrides) -> RepTrajectorySample:
    defaults = dict(
        trunk_pitch=30.0,
        knee_valgus_l=0.0,
        knee_valgus_r=0.0,
        hip_y_l=45.0,
        hip_y_r=45.0,
        knee_y_l=45.0,
        knee_y_r=45.0,
    )
    defaults.update(overrides)
    return RepTrajectorySample(**defaults)


def _descent_trajectory(
    bottom_offset_cm: float = 0.0, **bottom_overrides
) -> RepTrajectory:
    """A rep descending from standing to a bottom `bottom_offset_cm` above the knee.

    Only the bottom frames carry the fault overrides, so tests exercise the
    loaded-window filter rather than assuming the whole rep is scored.
    """
    standing = [
        _make_sample(hip_y_l=45.0 + FEMUR_CM, hip_y_r=45.0 + FEMUR_CM, trunk_pitch=0.0)
        for _ in range(10)
    ]
    bottom = [
        _make_sample(
            hip_y_l=45.0 + bottom_offset_cm,
            hip_y_r=45.0 + bottom_offset_cm,
            **bottom_overrides,
        )
        for _ in range(10)
    ]
    return RepTrajectory(samples=standing + bottom)


def _default_anthro() -> dict:
    return {
        "femur_torso_ratio": 1.0,
        "hip_width": 0.30,
        "shoulder_width": 0.40,
        "femur_length_avg": FEMUR_M,
    }


def _default_rom() -> dict:
    return {
        "peak_dorsiflexion": 35.0,
        "avg_depth": 120.0,
    }


class TestDepthScore:
    def test_parallel_scores_one(self):
        # hip joint centre level with knee joint centre → parallel → 1.0
        rep = _make_rep(
            hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=45.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        assert score_depth(rep, _default_anthro(), _default_rom()) == 1.0

    def test_hip_below_knee_still_capped(self):
        rep = _make_rep(
            hip_y_l_at_bottom=35.0, hip_y_r_at_bottom=35.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        assert score_depth(rep, _default_anthro(), _default_rom()) == 1.0

    def test_half_femur_above_parallel(self):
        # hip 20cm above knee on a 40cm femur → ratio 0.5 → score 0.5
        rep = _make_rep(
            hip_y_l_at_bottom=65.0, hip_y_r_at_bottom=65.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        score = score_depth(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_standing_scores_zero(self):
        # hip a full femur above the knee → thigh vertical → 0.0
        rep = _make_rep(
            hip_y_l_at_bottom=45.0 + FEMUR_CM, hip_y_r_at_bottom=45.0 + FEMUR_CM,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        assert score_depth(rep, _default_anthro(), _default_rom()) == 0.0

    def test_missing_standing_frame_does_not_zero_depth(self):
        # The at_top fields are unused now, so a rep with no standing frame
        # still scores on its own merits rather than being capped.
        rep = _make_rep(
            hip_y_l_at_top=0.0, hip_y_r_at_top=0.0,
            knee_y_l_at_top=0.0, knee_y_r_at_top=0.0,
        )
        assert score_depth(rep, _default_anthro(), _default_rom()) == 1.0

    def test_translation_invariant(self):
        # Shifting every keypoint by a constant must not change the score.
        rep = _make_rep(
            hip_y_l_at_bottom=55.0, hip_y_r_at_bottom=55.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        shifted = _make_rep(
            hip_y_l_at_bottom=-45.0, hip_y_r_at_bottom=-45.0,
            knee_y_l_at_bottom=-55.0, knee_y_r_at_bottom=-55.0,
        )
        assert score_depth(rep, _default_anthro(), _default_rom()) == pytest.approx(
            score_depth(shifted, _default_anthro(), _default_rom())
        )

    def test_trajectory_uses_deepest_frames(self):
        trajectory = _descent_trajectory(bottom_offset_cm=0.0)
        rep = _make_rep(
            hip_y_l_at_bottom=45.0 + FEMUR_CM, hip_y_r_at_bottom=45.0 + FEMUR_CM,
        )
        # The summary alone says "standing"; the trajectory says "parallel".
        assert score_depth(rep, _default_anthro(), _default_rom()) == 0.0
        assert score_depth(
            rep, _default_anthro(), _default_rom(), trajectory
        ) == pytest.approx(1.0, abs=0.02)

    def test_single_deep_frame_does_not_fake_depth(self):
        # 19 quarter-squat frames plus one spike to parallel should not score
        # as a parallel rep.
        shallow = [_make_sample(hip_y_l=75.0, hip_y_r=75.0) for _ in range(19)]
        spike = [_make_sample(hip_y_l=45.0, hip_y_r=45.0)]
        trajectory = RepTrajectory(samples=shallow + spike)
        score = score_depth(_make_rep(), _default_anthro(), _default_rom(), trajectory)
        assert score < 0.4


class TestTrunkControlScore:
    def test_perfect_lean(self):
        # femur_torso_ratio=1.0 → expected lean 30°
        rep = _make_rep(trunk_pitch_at_bottom=30.0)
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 1.0

    def test_within_tolerance(self):
        rep = _make_rep(trunk_pitch_at_bottom=33.0)
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 1.0

    def test_moderate_deviation(self):
        rep = _make_rep(trunk_pitch_at_bottom=43.0)  # 13° off → 1-(13-3)/20 = 0.5
        score = score_trunk_control(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_extreme_deviation(self):
        rep = _make_rep(trunk_pitch_at_bottom=60.0)
        assert score_trunk_control(rep, _default_anthro(), _default_rom()) == 0.0

    def test_upright_standing_frames_are_excluded(self):
        # The standing frames sit at 0° pitch, 30° from the expectation. If they
        # were scored, a clean rep would read as a severe fault.
        trajectory = _descent_trajectory(trunk_pitch=30.0)
        score = score_trunk_control(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        assert score == 1.0

    def test_lean_during_bottom_is_caught(self):
        trajectory = _descent_trajectory(trunk_pitch=43.0)
        score = score_trunk_control(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        assert score == pytest.approx(0.5, abs=0.01)


class TestKneeTrackingScore:
    def test_perfect_alignment(self):
        rep = _make_rep(knee_valgus_l=0.0, knee_valgus_r=0.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 1.0

    def test_both_within_zone(self):
        rep = _make_rep(knee_valgus_l=3.5, knee_valgus_r=-2.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 1.0

    def test_one_bad_other_perfect(self):
        rep = _make_rep(knee_valgus_l=10.0, knee_valgus_r=0.0)
        score = score_knee_tracking(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.75, abs=0.01)

    def test_negative_valgus_same_as_positive(self):
        rep_positive = _make_rep(knee_valgus_l=8.0, knee_valgus_r=0.0)
        rep_negative = _make_rep(knee_valgus_l=-8.0, knee_valgus_r=0.0)
        assert score_knee_tracking(
            rep_positive, _default_anthro(), _default_rom()
        ) == score_knee_tracking(rep_negative, _default_anthro(), _default_rom())

    def test_both_extreme(self):
        rep = _make_rep(knee_valgus_l=16.0, knee_valgus_r=16.0)
        assert score_knee_tracking(rep, _default_anthro(), _default_rom()) == 0.0

    def test_sustained_valgus_in_the_hole_is_caught(self):
        trajectory = _descent_trajectory(knee_valgus_l=10.0, knee_valgus_r=10.0)
        score = score_knee_tracking(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        assert score == pytest.approx(0.5, abs=0.01)

    def test_single_spiked_frame_is_rejected(self):
        # One mistracked frame out of twenty must not sink the rep.
        clean = [_make_sample() for _ in range(19)]
        spike = [_make_sample(knee_valgus_l=40.0, knee_valgus_r=40.0)]
        trajectory = RepTrajectory(samples=clean + spike)
        score = score_knee_tracking(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        assert score == 1.0


class TestSymmetryScore:
    def test_perfect_symmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=45.0)
        assert score_symmetry(rep, _default_anthro(), _default_rom()) == 1.0

    def test_moderate_asymmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=48.5)
        score = score_symmetry(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_extreme_asymmetry(self):
        rep = _make_rep(hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=51.0)
        assert score_symmetry(rep, _default_anthro(), _default_rom()) == 0.0

    def test_sustained_hip_drop_is_caught(self):
        samples = [
            _make_sample(hip_y_l=45.0, hip_y_r=48.5) for _ in range(10)
        ]
        trajectory = RepTrajectory(samples=samples)
        score = score_symmetry(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        assert score == pytest.approx(0.5, abs=0.01)


class TestTempoScore:
    def test_ideal_tempo(self):
        rep = _make_rep(descent_time_s=2.0, ascent_time_s=1.0)
        assert score_tempo(rep, _default_anthro(), _default_rom()) == 1.0

    def test_dive_bombed_descent(self):
        # 0.25s descent → 0.75s under the 1.0s floor → eccentric 0.5, and the
        # clean ascent must not average that away.
        rep = _make_rep(descent_time_s=0.25, ascent_time_s=1.0)
        score = score_tempo(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_hard_but_not_grinding_ascent_is_clean(self):
        # A tough rep that takes 2.75s to stand up is still inside the window.
        rep = _make_rep(descent_time_s=2.0, ascent_time_s=2.75)
        assert score_tempo(rep, _default_anthro(), _default_rom()) == 1.0

    def test_grinding_ascent(self):
        # 3.75s ascent → 0.75s over the 3.0s ceiling → 0.5
        rep = _make_rep(descent_time_s=2.0, ascent_time_s=3.75)
        score = score_tempo(rep, _default_anthro(), _default_rom())
        assert score == pytest.approx(0.5, abs=0.01)

    def test_too_slow_descent_penalised(self):
        rep = _make_rep(descent_time_s=6.0, ascent_time_s=1.0)
        assert score_tempo(rep, _default_anthro(), _default_rom()) == 0.0

    def test_weakest_phase_decides(self):
        rep = _make_rep(descent_time_s=0.1, ascent_time_s=8.0)
        assert score_tempo(rep, _default_anthro(), _default_rom()) == 0.0

    def test_untimed_rep_is_not_penalised(self):
        rep = _make_rep(descent_time_s=0.0, ascent_time_s=0.0)
        assert score_tempo(rep, _default_anthro(), _default_rom()) == 1.0


class TestLoadedWindow:
    def test_window_covers_the_bottom_only(self):
        # A frame a full femur above the deepest point is outside the window;
        # one within LOADED_WINDOW_RATIO femurs is inside.
        inside_offset = (LOADED_WINDOW_RATIO * FEMUR_CM) - 1.0
        samples = [
            _make_sample(hip_y_l=45.0, hip_y_r=45.0),
            _make_sample(
                hip_y_l=45.0 + inside_offset, hip_y_r=45.0 + inside_offset,
                knee_valgus_l=10.0, knee_valgus_r=10.0,
            ),
            _make_sample(
                hip_y_l=45.0 + FEMUR_CM, hip_y_r=45.0 + FEMUR_CM,
                knee_valgus_l=40.0, knee_valgus_r=40.0,
            ),
        ]
        trajectory = RepTrajectory(samples=samples)
        score = score_knee_tracking(
            _make_rep(), _default_anthro(), _default_rom(), trajectory
        )
        # The 40° standing frame is excluded; the 10° loaded frame is not.
        assert 0.0 < score < 1.0


class TestCompositeScore:
    def test_perfect_rep(self):
        rep = _make_rep(
            trunk_pitch_at_bottom=30.0,
            knee_valgus_l=0.0, knee_valgus_r=0.0,
            hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=45.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
            descent_time_s=2.0, ascent_time_s=1.0,
        )
        result = score_rep(rep, _default_anthro(), _default_rom())
        assert result.composite_score == pytest.approx(1.0, abs=0.01)

    def test_all_scores_bounded(self):
        rep = _make_rep()
        result = score_rep(rep, _default_anthro(), _default_rom())
        assert 0.0 <= result.depth_score <= 1.0
        assert 0.0 <= result.trunk_control_score <= 1.0
        assert 0.0 <= result.knee_tracking_score <= 1.0
        assert 0.0 <= result.symmetry_score <= 1.0
        assert 0.0 <= result.tempo_score <= 1.0
        assert 0.0 <= result.composite_score <= 1.0

    def test_weights_sum_to_one(self):
        from biomechanics.diagnosis.rep_scoring import (
            WEIGHT_DEPTH,
            WEIGHT_KNEES,
            WEIGHT_SYMMETRY,
            WEIGHT_TEMPO,
            WEIGHT_TRUNK,
        )
        total = (
            WEIGHT_DEPTH + WEIGHT_TRUNK + WEIGHT_KNEES + WEIGHT_SYMMETRY + WEIGHT_TEMPO
        )
        assert total == pytest.approx(1.0)

    def test_tempo_moves_the_composite(self):
        good = _make_rep(descent_time_s=2.0, ascent_time_s=1.0)
        rushed = _make_rep(descent_time_s=0.2, ascent_time_s=0.2)
        good_score = score_rep(good, _default_anthro(), _default_rom())
        rushed_score = score_rep(rushed, _default_anthro(), _default_rom())
        assert rushed_score.composite_score < good_score.composite_score


class TestSetScoreSummary:
    def test_best_and_worst_identification(self):
        good_rep = _make_rep(
            rep_number=2, trunk_pitch_at_bottom=30.0,
            knee_valgus_l=0.0, knee_valgus_r=0.0,
            hip_y_l_at_bottom=45.0, hip_y_r_at_bottom=45.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        bad_rep = _make_rep(
            rep_number=3, trunk_pitch_at_bottom=55.0,
            knee_valgus_l=14.0, knee_valgus_r=12.0,
            hip_y_l_at_bottom=70.0, hip_y_r_at_bottom=70.0,
            knee_y_l_at_bottom=45.0, knee_y_r_at_bottom=45.0,
        )
        result = score_set([good_rep, bad_rep], _default_anthro(), _default_rom())
        assert result.best_rep_number == 2
        assert result.worst_rep_number == 3

    def test_single_rep_slope_zero(self):
        rep = _make_rep(rep_number=2)
        result = score_set([rep], _default_anthro(), _default_rom())
        assert result.trend_slope == 0.0

    def test_degrading_trend_negative_slope(self):
        reps = [
            _make_rep(rep_number=2, trunk_pitch_at_bottom=30.0),
            _make_rep(rep_number=3, trunk_pitch_at_bottom=35.0,
                      hip_y_l_at_bottom=55.0, hip_y_r_at_bottom=55.0),
            _make_rep(rep_number=4, trunk_pitch_at_bottom=50.0,
                      hip_y_l_at_bottom=70.0, hip_y_r_at_bottom=70.0,
                      knee_valgus_l=12.0),
        ]
        result = score_set(reps, _default_anthro(), _default_rom())
        assert result.trend_slope < 0

    def test_mean_score_computed(self):
        result = score_set(
            [_make_rep(rep_number=2), _make_rep(rep_number=3)],
            _default_anthro(),
            _default_rom(),
        )
        score_a = result.per_rep_scores[0].composite_score
        score_b = result.per_rep_scores[1].composite_score
        assert result.mean_score == pytest.approx((score_a + score_b) / 2.0, abs=0.01)

    def test_trajectories_are_matched_per_rep(self):
        reps = [_make_rep(rep_number=1), _make_rep(rep_number=2)]
        trajectories = [
            _descent_trajectory(knee_valgus_l=14.0, knee_valgus_r=14.0),
            _descent_trajectory(),
        ]
        result = score_set(reps, _default_anthro(), _default_rom(), trajectories)
        assert result.worst_rep_number == 1
        assert result.best_rep_number == 2

    def test_missing_trajectories_fall_back_to_summary(self):
        reps = [_make_rep(rep_number=1), _make_rep(rep_number=2)]
        with_none = score_set(reps, _default_anthro(), _default_rom(), [None, None])
        without = score_set(reps, _default_anthro(), _default_rom())
        assert with_none.mean_score == without.mean_score
