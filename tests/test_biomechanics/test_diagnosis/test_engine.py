"""Tests for the hypothesis engine's representative-rep selection."""

from __future__ import annotations

from biomechanics.diagnosis.engine import HypothesisEngine
from biomechanics.diagnosis.types import RepKinematicSummary

ANTHRO = {
    "femur_torso_ratio": 0.93,
    "hip_width": 0.30,
    "shoulder_width": 0.40,
    "femur_length_avg": 0.42,
    "tibia_length_avg": 0.43,
    "torso_length": 0.45,
    "foot_length": 0.26,
}

ROM = {"dorsiflexion_drop": 35.0, "avg_depth": 120.0}

# Trunk pitch matching expected_trunk_lean_geometric(ANTHRO) = 30 + (0.93-1)*120
GOOD_TRUNK_PITCH = 21.6


def _make_rep(rep_number: int, hip_y_bottom: float = 40.0) -> RepKinematicSummary:
    return RepKinematicSummary(
        rep_number=rep_number,
        trunk_pitch_at_bottom=GOOD_TRUNK_PITCH,
        knee_valgus_l=0.0,
        knee_valgus_r=0.0,
        ankle_df_l_max=25.0,
        ankle_df_r_max=25.0,
        hip_y_l_at_bottom=hip_y_bottom,
        hip_y_r_at_bottom=hip_y_bottom,
        knee_y_l_at_bottom=38.0,
        knee_y_r_at_bottom=38.0,
        stance_width_ratio=1.2,
        foot_direction_angle_l=20.0,
        foot_direction_angle_r=20.0,
        depth_class_int=4,
        hip_y_l_at_top=90.0,
        hip_y_r_at_top=90.0,
        knee_y_l_at_top=45.0,
        knee_y_r_at_top=45.0,
    )


class TestPickRepresentativeRep:
    """The worst-scoring rep must be found by rep_number, regardless of
    numbering convention (live path starts at 1, offline replay at 2,
    rolling windows at arbitrary offsets)."""

    def test_live_numbering_from_one(self):
        # hip_y_bottom=85 → barely descended → worst depth score
        reps = [_make_rep(1), _make_rep(2, hip_y_bottom=85.0), _make_rep(3)]
        picked = HypothesisEngine()._pick_representative_rep(reps, ANTHRO, ROM)
        assert picked.rep_number == 2

    def test_offline_numbering_from_two(self):
        reps = [_make_rep(2), _make_rep(3, hip_y_bottom=85.0), _make_rep(4)]
        picked = HypothesisEngine()._pick_representative_rep(reps, ANTHRO, ROM)
        assert picked.rep_number == 3

    def test_rolling_window_numbering(self):
        reps = [_make_rep(4), _make_rep(5, hip_y_bottom=85.0), _make_rep(6)]
        picked = HypothesisEngine()._pick_representative_rep(reps, ANTHRO, ROM)
        assert picked.rep_number == 5

    def test_single_rep_short_circuit(self):
        reps = [_make_rep(7)]
        picked = HypothesisEngine()._pick_representative_rep(reps, ANTHRO, ROM)
        assert picked.rep_number == 7
