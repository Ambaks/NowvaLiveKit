"""Tests for set-level evidence tests in the diagnosis graph."""

from __future__ import annotations

import pytest

from biomechanics.diagnosis.graph.evidence_tests import (
    test_narrow_stance as narrow_stance_evidence,
    test_progressive_degradation as progressive_degradation_evidence,
)
from biomechanics.diagnosis.graph.parameter_deltas import dorsi_driven_targets
from biomechanics.diagnosis.types import (
    RepKinematicSummary,
    RepScore,
    SetScoreSummary,
)

ANTHRO = {"femur_torso_ratio": 0.93}
ROM = {"dorsiflexion_drop": 35.0, "avg_depth": 120.0}

EVIDENCE_TOLERANCE = 1e-6


def _make_rep(rep_number: int = 1, **overrides) -> RepKinematicSummary:
    values: dict = dict(
        rep_number=rep_number,
        trunk_pitch_at_bottom=21.6,
        knee_valgus_l=0.0,
        knee_valgus_r=0.0,
        ankle_df_l_max=25.0,
        ankle_df_r_max=25.0,
        hip_y_l_at_bottom=40.0,
        hip_y_r_at_bottom=40.0,
        knee_y_l_at_bottom=44.0,
        knee_y_r_at_bottom=44.0,
        stance_width_ratio=1.2,
        foot_direction_angle_l=20.0,
        foot_direction_angle_r=20.0,
        depth_class_int=4,
    )
    values.update(overrides)
    return RepKinematicSummary(**values)


def _make_summary(
    composite_scores: list[float], trend_slope: float
) -> SetScoreSummary:
    per_rep_scores = [
        RepScore(
            rep_number=index + 1,
            depth_score=score,
            trunk_control_score=score,
            knee_tracking_score=score,
            symmetry_score=score,
            composite_score=score,
        )
        for index, score in enumerate(composite_scores)
    ]
    best = max(per_rep_scores, key=lambda s: s.composite_score)
    worst = min(per_rep_scores, key=lambda s: s.composite_score)
    return SetScoreSummary(
        mean_score=sum(composite_scores) / len(composite_scores),
        best_rep_number=best.rep_number,
        worst_rep_number=worst.rep_number,
        trend_slope=trend_slope,
        per_rep_scores=per_rep_scores,
    )


class TestNarrowStance:
    """narrow_stance evidence must measure the stance-width gap against the
    anthropometry-driven target alone. Whether the stance is causing a
    problem is established by the implicating symptom, not re-derived here
    from depth class or trunk pitch — those can contradict the symptom's own
    depth measure and silently zero the evidence."""

    def _ideal_ratio(self, rom: dict = ROM) -> float:
        ideal, _ = dorsi_driven_targets(rom["dorsiflexion_drop"], ANTHRO)
        return ideal

    def test_stance_at_target_gives_zero(self):
        rep = _make_rep(stance_width_ratio=self._ideal_ratio())
        evidence = narrow_stance_evidence(rep, ANTHRO, ROM, None)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)

    def test_stance_above_target_gives_zero(self):
        rep = _make_rep(stance_width_ratio=self._ideal_ratio() + 0.2)
        evidence = narrow_stance_evidence(rep, ANTHRO, ROM, None)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)

    def test_slightly_narrow_gives_partial_evidence(self):
        rep = _make_rep(stance_width_ratio=self._ideal_ratio() - 0.25)
        evidence = narrow_stance_evidence(rep, ANTHRO, ROM, None)
        assert evidence == pytest.approx(0.5, abs=EVIDENCE_TOLERANCE)

    def test_very_narrow_saturates_at_one(self):
        rep = _make_rep(stance_width_ratio=self._ideal_ratio() - 0.6)
        evidence = narrow_stance_evidence(rep, ANTHRO, ROM, None)
        assert evidence == pytest.approx(1.0, abs=EVIDENCE_TOLERANCE)

    def test_deep_depth_class_does_not_gate_evidence(self):
        # Regression (session 2026-07-22_11-39-49): knee-flexion depth class
        # said "below parallel" while the depth_limit symptom fired from
        # hip-vs-knee height, so a 0.77 stance ratio produced zero evidence
        # and narrow_stance could never surface.
        rep = _make_rep(
            stance_width_ratio=0.77,
            depth_class_int=4,
            trunk_pitch_at_bottom=8.1,
        )
        evidence = narrow_stance_evidence(rep, ANTHRO, ROM, None)
        assert evidence == pytest.approx(1.0, abs=EVIDENCE_TOLERANCE)


class TestProgressiveDegradation:
    """weight_too_heavy evidence must come from the score trend across the
    set, not from a single rep's kinematics."""

    def test_steep_decline_gives_full_evidence(self):
        summary = _make_summary([0.9, 0.8, 0.7, 0.6, 0.5], trend_slope=-0.1)
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, summary)
        assert evidence == pytest.approx(1.0, abs=EVIDENCE_TOLERANCE)

    def test_gentle_decline_gives_partial_evidence(self):
        summary = _make_summary([0.9, 0.87, 0.84], trend_slope=-0.03)
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, summary)
        assert evidence == pytest.approx(0.5, abs=EVIDENCE_TOLERANCE)

    def test_flat_set_gives_zero(self):
        summary = _make_summary([0.8, 0.8, 0.8, 0.8], trend_slope=0.0)
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, summary)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)

    def test_improving_set_gives_zero(self):
        summary = _make_summary([0.6, 0.7, 0.8], trend_slope=0.1)
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, summary)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)

    def test_missing_summary_gives_zero(self):
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, None)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)

    def test_too_few_reps_gives_zero(self):
        summary = _make_summary([0.9, 0.7], trend_slope=-0.2)
        evidence = progressive_degradation_evidence(_make_rep(), ANTHRO, ROM, summary)
        assert evidence == pytest.approx(0.0, abs=EVIDENCE_TOLERANCE)
