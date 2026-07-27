"""Tests for the hypothesis engine: representative-rep selection, evidence-weighted
cause scoring, and explanation/correction consistency."""

from __future__ import annotations

import math

import pytest

from biomechanics.diagnosis.engine import HypothesisEngine
from biomechanics.diagnosis.graph.parameter_deltas import (
    dorsi_driven_targets,
    foot_angle_target_deg,
    stance_target_ratio,
)
from biomechanics.diagnosis.rep_scoring import score_set
from biomechanics.diagnosis.types import RepKinematicSummary, SetFeatures

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
ROM_LIMITED_DORSIFLEXION = {"dorsiflexion_drop": 15.0, "avg_depth": 120.0}

# Trunk pitch matching expected_trunk_lean_geometric(ANTHRO) = 30 + (0.93-1)*120
GOOD_TRUNK_PITCH = 21.6


def _make_rep(
    rep_number: int, hip_y_bottom: float = 40.0, **overrides
) -> RepKinematicSummary:
    values: dict = dict(
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
    values.update(overrides)
    return RepKinematicSummary(**values)


def _diagnose(reps: list[RepKinematicSummary], rom: dict = ROM):
    set_features = SetFeatures(
        user_id=1,
        set_id="set-1",
        rep_count=len(reps),
        per_rep_kinematics=reps,
        anthropometry=ANTHRO,
        rom=rom,
    )
    return HypothesisEngine().diagnose(set_features)


def _all_cause_ids(result) -> list[str]:
    hypotheses = (
        result.immediate_causes + result.session_causes + result.longterm_causes
    )
    return [h.cause_id for h in hypotheses]


class TestPickRepresentativeRep:
    """The worst-scoring rep must be found by rep_number, regardless of
    numbering convention (live path starts at 1, offline replay at 2,
    rolling windows at arbitrary offsets)."""

    def _pick(self, reps: list[RepKinematicSummary]) -> RepKinematicSummary:
        summary = score_set(reps, ANTHRO, ROM)
        return HypothesisEngine()._pick_representative_rep(reps, summary)

    def test_live_numbering_from_one(self):
        # hip_y_bottom=85 → barely descended → worst depth score
        reps = [_make_rep(1), _make_rep(2, hip_y_bottom=85.0), _make_rep(3)]
        assert self._pick(reps).rep_number == 2

    def test_offline_numbering_from_two(self):
        reps = [_make_rep(2), _make_rep(3, hip_y_bottom=85.0), _make_rep(4)]
        assert self._pick(reps).rep_number == 3

    def test_rolling_window_numbering(self):
        reps = [_make_rep(4), _make_rep(5, hip_y_bottom=85.0), _make_rep(6)]
        assert self._pick(reps).rep_number == 5

    def test_single_rep_short_circuit(self):
        reps = [_make_rep(7)]
        picked = HypothesisEngine()._pick_representative_rep(reps, None)
        assert picked.rep_number == 7


class TestEvidenceWeightedScoring:
    """A detected symptom must not distribute a full unit of probability mass
    among its candidate causes when all evidence is weak: cause scores are
    weighted by symptom severity and an unexplained-leak term absorbs mass."""

    def test_mild_symptom_with_weak_evidence_yields_no_hypotheses(self):
        # 2.6cm hip asymmetry: barely past the symptom threshold (severity
        # ~0.15) with weak evidence for every candidate cause. Must NOT be
        # coached as a confident weight-shift diagnosis.
        reps = [
            _make_rep(
                rep_number,
                hip_y_l_at_bottom=40.0,
                hip_y_r_at_bottom=42.6,
                knee_y_l_at_bottom=44.0,
                knee_y_r_at_bottom=44.0,
            )
            for rep_number in (1, 2, 3)
        ]
        result = _diagnose(reps)

        assert any(
            s.symptom_id == "asymmetric_depth" for s in result.detected_symptoms
        )
        assert _all_cause_ids(result) == []

    def test_severe_symptom_with_strong_evidence_is_diagnosed(self):
        # 5.5cm hip asymmetry: severe symptom with strong evidence for both
        # weight shift and unilateral hip restriction.
        reps = [
            _make_rep(
                rep_number,
                hip_y_l_at_bottom=40.0,
                hip_y_r_at_bottom=45.5,
                knee_y_l_at_bottom=44.0,
                knee_y_r_at_bottom=44.0,
            )
            for rep_number in (1, 2, 3)
        ]
        result = _diagnose(reps)

        cause_ids = _all_cause_ids(result)
        assert "weight_shift_cue" in cause_ids
        assert "unilateral_hip_mobility_limit" in cause_ids


class TestExplanationMatchesCorrection:
    """The spoken explanation and the geometric parameter delta must be
    derived from the same personalized target."""

    def _shallow_narrow_feet_reps(self) -> list[RepKinematicSummary]:
        # Limited dorsiflexion + nearly straight feet + shallow depth:
        # triggers depth_limit with narrow_foot_angle and narrow_stance
        # as candidate causes.
        return [
            _make_rep(
                rep_number,
                hip_y_bottom=45.0,
                knee_y_l_at_bottom=40.0,
                knee_y_r_at_bottom=40.0,
                foot_direction_angle_l=5.0,
                foot_direction_angle_r=5.0,
                ankle_df_l_max=14.0,
                ankle_df_r_max=14.0,
                depth_class_int=1,
            )
            for rep_number in (1, 2, 3)
        ]

    def test_foot_angle_explanation_matches_parameter_delta(self):
        result = _diagnose(
            self._shallow_narrow_feet_reps(), rom=ROM_LIMITED_DORSIFLEXION
        )
        hypothesis = next(
            h for h in result.immediate_causes if h.cause_id == "narrow_foot_angle"
        )

        target_angle = foot_angle_target_deg(ANTHRO, ROM_LIMITED_DORSIFLEXION)
        assert f"~{target_angle:.0f}°" in hypothesis.explanation

        delta_degrees = math.degrees(abs(hypothesis.parameter_delta["L_ankle.ry"]))
        assert delta_degrees == pytest.approx(target_angle - 5.0, abs=0.01)

    def test_stance_explanation_matches_parameter_delta(self):
        result = _diagnose(
            self._shallow_narrow_feet_reps(), rom=ROM_LIMITED_DORSIFLEXION
        )
        hypothesis = next(
            h for h in result.immediate_causes if h.cause_id == "narrow_stance"
        )

        target_ratio = stance_target_ratio(1.2, ANTHRO, ROM_LIMITED_DORSIFLEXION)
        assert f"~{target_ratio:.2f}" in hypothesis.explanation

        expected_per_side = (target_ratio - 1.2) * ANTHRO["shoulder_width"] / 2.0
        per_side = hypothesis.parameter_delta["__foot_target_delta"][5]
        assert per_side == pytest.approx(expected_per_side, abs=1e-6)


class TestNarrowStanceSurfacesUnderDepthLimit:
    """When depth_limit fires from hip-vs-knee height, a narrow stance must
    surface as an immediate cause even if the knee-flexion depth class and
    trunk pitch look fine — the two depth measures can disagree (regression
    from session 2026-07-22_11-39-49, where the toe cue fired six rounds
    running while the stance cue was structurally silenced)."""

    def _depth_limited_rep(
        self, rep_number: int, stance_width_ratio: float
    ) -> RepKinematicSummary:
        # Hip above knee fires depth_limit; depth_class_int=4 and neutral
        # trunk pitch mimic the contradictory live measurements.
        return _make_rep(
            rep_number,
            hip_y_bottom=45.0,
            knee_y_l_at_bottom=40.0,
            knee_y_r_at_bottom=40.0,
            stance_width_ratio=stance_width_ratio,
            foot_direction_angle_l=27.5,
            foot_direction_angle_r=27.5,
            depth_class_int=4,
        )

    def test_narrow_stance_is_diagnosed(self):
        reps = [self._depth_limited_rep(n, 0.77) for n in (1, 2, 3)]
        result = _diagnose(reps)
        assert "narrow_stance" in [h.cause_id for h in result.immediate_causes]

    def test_wide_stance_is_not_diagnosed(self):
        target_ratio, _ = dorsi_driven_targets(ROM["dorsiflexion_drop"], ANTHRO)
        reps = [
            self._depth_limited_rep(n, target_ratio + 0.1) for n in (1, 2, 3)
        ]
        result = _diagnose(reps)
        assert "narrow_stance" not in [
            h.cause_id for h in result.immediate_causes
        ]


class TestFootAngleAlwaysCued:
    """When a depth or trunk-lean fault fires and the feet are turned out less
    than the target (>=30 deg), widening the feet is force-cued even when the
    Bayesian competition would rank it below the hypothesis threshold."""

    def _immediate_ids(self, result) -> list[str]:
        return [h.cause_id for h in result.immediate_causes]

    def _shallow_feet_at(self, angle: float) -> list[RepKinematicSummary]:
        # Shallow depth (fires depth_limit), otherwise clean form.
        return [
            _make_rep(
                rep_number,
                hip_y_bottom=45.0,
                knee_y_l_at_bottom=40.0,
                knee_y_r_at_bottom=40.0,
                foot_direction_angle_l=angle,
                foot_direction_angle_r=angle,
                depth_class_int=1,
            )
            for rep_number in (1, 2, 3)
        ]

    def test_target_is_at_least_30_degrees(self):
        assert foot_angle_target_deg(ANTHRO, ROM) >= 30.0

    def test_barely_narrow_feet_are_force_cued(self):
        # 29 deg gives near-zero evidence, so without the override the cause
        # would never clear the 0.15 hypothesis threshold.
        result = _diagnose(self._shallow_feet_at(29.0))
        assert "narrow_foot_angle" in self._immediate_ids(result)

    def test_recommended_angle_is_at_least_30(self):
        result = _diagnose(self._shallow_feet_at(29.0))
        hypothesis = next(
            h for h in result.immediate_causes if h.cause_id == "narrow_foot_angle"
        )
        target_angle = foot_angle_target_deg(ANTHRO, ROM)
        assert target_angle >= 30.0
        assert f"~{target_angle:.0f}°" in hypothesis.explanation

    def test_adequately_turned_out_feet_are_not_cued(self):
        result = _diagnose(self._shallow_feet_at(32.0))
        assert "narrow_foot_angle" not in self._immediate_ids(result)

    def test_narrow_feet_without_linked_fault_are_not_cued(self):
        # Deep rep with knee valgus only: knee_not_tracking_toes fires, but it
        # is not a linked symptom, so foot angle stays silent despite 29 deg.
        reps = [
            _make_rep(
                rep_number,
                hip_y_bottom=40.0,
                knee_y_l_at_bottom=44.0,
                knee_y_r_at_bottom=44.0,
                knee_valgus_l=25.0,
                knee_valgus_r=25.0,
                foot_direction_angle_l=29.0,
                foot_direction_angle_r=29.0,
                depth_class_int=4,
            )
            for rep_number in (1, 2, 3)
        ]
        result = _diagnose(reps)
        assert "narrow_foot_angle" not in self._immediate_ids(result)
