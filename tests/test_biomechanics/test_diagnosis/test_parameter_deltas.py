"""Tests that geometric corrections reach the shared anthropometry-driven targets."""

from __future__ import annotations

import math

import pytest

from biomechanics.diagnosis.graph.parameter_deltas import (
    delta_widen_foot_angle,
    delta_widen_stance,
    foot_angle_target_deg,
    stance_target_ratio,
)
from biomechanics.diagnosis.types import RepKinematicSummary

ANTHRO = {"femur_torso_ratio": 0.93, "shoulder_width": 0.40, "hip_width": 0.30}
ROM = {"peak_dorsiflexion": 35.0, "avg_depth": 120.0}

DELTA_TOLERANCE = 1e-6


def _make_rep(**overrides) -> RepKinematicSummary:
    values: dict = dict(
        rep_number=1,
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
        foot_direction_angle_l=5.0,
        foot_direction_angle_r=5.0,
        depth_class_int=2,
    )
    values.update(overrides)
    return RepKinematicSummary(**values)


class TestSharedTargets:
    def test_widen_stance_delta_reaches_shared_target(self):
        rep = _make_rep()
        delta = delta_widen_stance(rep, ANTHRO, ROM)

        target_ratio = stance_target_ratio(rep.stance_width_ratio, ANTHRO, ROM)
        expected_per_side = (
            (target_ratio - rep.stance_width_ratio) * ANTHRO["shoulder_width"] / 2.0
        )
        foot_target = delta["__foot_target_delta"]
        assert foot_target[5] == pytest.approx(expected_per_side, abs=DELTA_TOLERANCE)
        assert foot_target[2] == pytest.approx(-expected_per_side, abs=DELTA_TOLERANCE)

    def test_widen_foot_angle_delta_reaches_shared_target(self):
        rep = _make_rep()
        delta = delta_widen_foot_angle(rep, ANTHRO, ROM)

        target_angle = foot_angle_target_deg(ANTHRO, ROM)
        avg_current = 5.0
        delta_degrees = math.degrees(delta["L_ankle.ry"])
        assert delta_degrees == pytest.approx(
            target_angle - avg_current, abs=DELTA_TOLERANCE
        )

    def test_stance_target_is_independent_of_current_stance(self):
        """The target used to be max(dorsi_target, current + 0.15), which
        recommended widening by >=0.15 shoulder-widths regardless of
        measurement — including for athletes already wider than their own
        target, where the evidence test that justified the cue returns zero."""
        narrow = stance_target_ratio(0.9, ANTHRO, ROM)
        wide = stance_target_ratio(2.4, ANTHRO, ROM)
        assert narrow == pytest.approx(wide)

    def test_already_wide_stance_gets_no_widening(self):
        rep = _make_rep(stance_width_ratio=2.4)
        delta = delta_widen_stance(rep, ANTHRO, ROM)
        assert delta["__foot_target_delta"] == [0.0] * 6

    def test_stance_target_is_capped(self):
        assert stance_target_ratio(0.9, ANTHRO, ROM) <= 2.5
