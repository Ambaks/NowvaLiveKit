"""Tests for the YAML graph loader — validates parsing, resolution, and freezing."""

from types import MappingProxyType

import pytest

from biomechanics.diagnosis.graph.loader import (
    CAUSE_GRAPH,
    SYMPTOM_GRAPH,
)


class TestGraphLoading:
    def test_symptom_graph_is_frozen(self):
        assert isinstance(SYMPTOM_GRAPH, MappingProxyType)

    def test_cause_graph_is_frozen(self):
        assert isinstance(CAUSE_GRAPH, MappingProxyType)

    def test_symptom_graph_has_expected_symptoms(self):
        expected_ids = {
            "excessive_trunk_lean",
            "knee_not_tracking_toes",
            "asymmetric_depth",
            "depth_limit",
        }
        assert set(SYMPTOM_GRAPH.keys()) == expected_ids

    def test_cause_graph_has_expected_causes(self):
        expected_ids = {
            "anthropometric_femur_torso_ratio",
            "narrow_stance",
            "narrow_foot_angle",
            "bracing_failure",
            "knee_track_cue",
            "weight_shift_cue",
            "depth_cue_unfamiliar",
            "weight_too_heavy",
            "limited_ankle_df",
            "limited_hip_flexion",
            "weak_hip_abductors",
            "foot_collapse_arch",
            "unilateral_hip_mobility_limit",
        }
        assert set(CAUSE_GRAPH.keys()) == expected_ids

    def test_all_symptom_cause_references_resolve(self):
        for symptom_id, symptom_def in SYMPTOM_GRAPH.items():
            for candidate in symptom_def["candidate_causes"]:
                cause_id = candidate["cause_id"]
                assert cause_id in CAUSE_GRAPH, (
                    f"Symptom '{symptom_id}' references missing cause '{cause_id}'"
                )

    def test_all_evidence_test_fns_are_callable(self):
        for cause_id, cause_def in CAUSE_GRAPH.items():
            assert callable(cause_def["evidence_test_fn"]), (
                f"Cause '{cause_id}' has non-callable evidence_test_fn"
            )

    def test_all_parameter_delta_fns_are_callable_or_none(self):
        for cause_id, cause_def in CAUSE_GRAPH.items():
            delta_fn = cause_def["parameter_delta_fn"]
            assert delta_fn is None or callable(delta_fn), (
                f"Cause '{cause_id}' has invalid parameter_delta_fn"
            )

    def test_tier1_causes_have_delta_fns(self):
        for cause_id, cause_def in CAUSE_GRAPH.items():
            if cause_def["tier"] == 1:
                assert cause_def["parameter_delta_fn"] is not None, (
                    f"Tier-1 cause '{cause_id}' is missing parameter_delta_fn"
                )

    def test_expected_value_fns_are_callable(self):
        for symptom_id, symptom_def in SYMPTOM_GRAPH.items():
            assert callable(symptom_def["expected_value_fn"]), (
                f"Symptom '{symptom_id}' has non-callable expected_value_fn"
            )

    def test_priors_sum_approximately_to_one(self):
        for symptom_id, symptom_def in SYMPTOM_GRAPH.items():
            total_prior = sum(
                c["prior"] for c in symptom_def["candidate_causes"]
            )
            assert 0.9 <= total_prior <= 1.1, (
                f"Symptom '{symptom_id}' priors sum to {total_prior:.2f}, "
                f"expected ~1.0"
            )

    def test_symptom_detection_fields_present(self):
        for symptom_id, symptom_def in SYMPTOM_GRAPH.items():
            detection = symptom_def["detection"]
            assert "feature" in detection
            assert "aggregation" in detection
            assert detection["aggregation"] in ("max", "mean", "last")
