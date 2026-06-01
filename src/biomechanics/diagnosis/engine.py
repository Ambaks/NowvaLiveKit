"""Hypothesis engine for causal squat diagnosis.

Operates at set-level: takes aggregated kinematic data for all reps,
detects symptoms, maps them to candidate causes via the knowledge graph,
scores each cause using evidence tests, and returns a structured diagnosis.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .graph.loader import SYMPTOM_GRAPH, CAUSE_GRAPH
from .types import (
    DetectedSymptom,
    DiagnosisResult,
    HypothesizedCause,
    RepKinematicSummary,
    SetFeatures,
)


class HypothesisEngine:
    def diagnose(self, set_features: SetFeatures) -> DiagnosisResult:
        reps = set_features.per_rep_kinematics
        anthro = set_features.anthropometry
        rom = set_features.rom

        detected_symptoms = self._detect_symptoms(reps, anthro)
        cause_scores = self._score_causes(detected_symptoms, reps, anthro, rom)
        filtered_causes = {
            cause_id: info
            for cause_id, info in cause_scores.items()
            if info["aggregate_score"] > 0.25
        }

        hypotheses = self._build_hypotheses(filtered_causes, reps, anthro, rom)
        combined_perturbation = self._merge_perturbations(hypotheses)

        immediate = [h for h in hypotheses if h.tier == 1]
        session = [h for h in hypotheses if h.tier == 2]
        longterm = [h for h in hypotheses if h.tier == 3]
        contextual = [h for h in hypotheses if h.tier == 0]

        confidence = self._compute_confidence(detected_symptoms)

        return DiagnosisResult(
            set_id=set_features.set_id,
            detected_symptoms=detected_symptoms,
            immediate_causes=immediate,
            session_causes=session,
            longterm_causes=longterm,
            contextual_notes=contextual,
            combined_perturbation=combined_perturbation,
            confidence=confidence,
        )

    def _detect_symptoms(
        self, reps: list[RepKinematicSummary], anthro: dict
    ) -> list[DetectedSymptom]:
        detected = []

        for symptom_id, symptom_def in SYMPTOM_GRAPH.items():
            detection = symptom_def["detection"]
            feature_name = detection["feature"]
            aggregation = detection["aggregation"]

            values_per_rep = [
                self._extract_feature(rep, feature_name) for rep in reps
            ]

            aggregated_value = self._aggregate(values_per_rep, aggregation)
            expected_value = symptom_def["expected_value_fn"](anthro)
            threshold = symptom_def["threshold"]
            scoring = symptom_def["severity_scoring"]

            severity = self._compute_severity(
                aggregated_value, expected_value, threshold, scoring
            )

            if severity > 0.0:
                contributing_reps = [
                    rep.rep_number
                    for rep, value in zip(reps, values_per_rep)
                    if self._compute_severity(
                        value, expected_value, threshold, scoring
                    )
                    > 0.0
                ]
                detected.append(
                    DetectedSymptom(
                        symptom_id=symptom_id,
                        severity=severity,
                        contributing_reps=contributing_reps,
                    )
                )

        return detected

    def _score_causes(
        self,
        detected_symptoms: list[DetectedSymptom],
        reps: list[RepKinematicSummary],
        anthro: dict,
        rom: dict,
    ) -> dict[str, dict[str, Any]]:
        cause_posteriors: dict[str, list[float]] = {}
        cause_implicated_by: dict[str, list[str]] = {}

        representative_rep = self._pick_representative_rep(reps)

        for symptom in detected_symptoms:
            symptom_def = SYMPTOM_GRAPH[symptom.symptom_id]
            candidates = symptom_def["candidate_causes"]

            raw_scores: list[tuple[str, float]] = []
            for candidate in candidates:
                cause_id = candidate["cause_id"]
                prior = candidate["prior"]
                cause_def = CAUSE_GRAPH[cause_id]
                evidence_fn = cause_def["evidence_test_fn"]
                evidence_score = evidence_fn(representative_rep, anthro, rom)
                posterior = prior * evidence_score
                raw_scores.append((cause_id, posterior))

            total = sum(score for _, score in raw_scores)
            for cause_id, posterior in raw_scores:
                normalized = posterior / total if total > 0 else 0.0
                cause_posteriors.setdefault(cause_id, []).append(normalized)
                cause_implicated_by.setdefault(cause_id, []).append(
                    symptom.symptom_id
                )

        result: dict[str, dict[str, Any]] = {}
        for cause_id, posteriors in cause_posteriors.items():
            aggregate_score = 1.0 - math.prod(1.0 - p for p in posteriors)
            result[cause_id] = {
                "aggregate_score": aggregate_score,
                "posteriors": posteriors,
                "implicated_by": cause_implicated_by[cause_id],
            }

        return result

    def _build_hypotheses(
        self,
        filtered_causes: dict[str, dict[str, Any]],
        reps: list[RepKinematicSummary],
        anthro: dict,
        rom: dict,
    ) -> list[HypothesizedCause]:
        representative_rep = self._pick_representative_rep(reps)
        hypotheses = []

        for cause_id, info in filtered_causes.items():
            cause_def = CAUSE_GRAPH[cause_id]
            tier = cause_def["tier"]
            evidence_fn = cause_def["evidence_test_fn"]
            evidence_score = evidence_fn(representative_rep, anthro, rom)

            parameter_delta = None
            if tier == 1 and cause_def["parameter_delta_fn"] is not None:
                delta_fn = cause_def["parameter_delta_fn"]
                parameter_delta = delta_fn(representative_rep, anthro, rom)

            explanation = self._fill_template(
                cause_def["explanation_template"],
                representative_rep,
                anthro,
                rom,
                info,
            )

            avg_prior = (
                sum(info["posteriors"]) / len(info["posteriors"])
                if info["posteriors"]
                else 0.0
            )

            hypotheses.append(
                HypothesizedCause(
                    cause_id=cause_id,
                    tier=tier,
                    score=info["aggregate_score"],
                    evidence_score=evidence_score,
                    prior=avg_prior,
                    implicated_by=info["implicated_by"],
                    parameter_delta=parameter_delta,
                    explanation=explanation,
                )
            )

        hypotheses.sort(key=lambda h: (-h.tier, -h.score))
        return hypotheses

    def _merge_perturbations(
        self, hypotheses: list[HypothesizedCause]
    ) -> dict:
        combined: dict[str, float] = {}
        foot_target_deltas: list[list[float]] = []

        for hypothesis in hypotheses:
            if hypothesis.tier != 1 or hypothesis.parameter_delta is None:
                continue

            for key, value in hypothesis.parameter_delta.items():
                if key == "__foot_target_delta":
                    foot_target_deltas.append(value)
                elif isinstance(value, str):
                    combined[key] = value
                else:
                    combined[key] = combined.get(key, 0.0) + value

        if foot_target_deltas:
            merged_foot = [0.0] * 6
            for delta in foot_target_deltas:
                for i in range(6):
                    merged_foot[i] += delta[i]
            combined["__foot_target_delta"] = merged_foot

        return combined

    def _compute_confidence(
        self, detected_symptoms: list[DetectedSymptom]
    ) -> float:
        if not detected_symptoms:
            return 0.0
        mean_severity = sum(s.severity for s in detected_symptoms) / len(
            detected_symptoms
        )
        num_symptoms = len(detected_symptoms)
        confidence = min(1.0, mean_severity * math.sqrt(num_symptoms / 2.0))
        return round(confidence, 3)

    def _extract_feature(
        self, rep: RepKinematicSummary, feature_name: str
    ) -> float:
        if feature_name == "knee_valgus_max":
            return max(rep.knee_valgus_l, rep.knee_valgus_r)
        elif feature_name == "hip_y_asymmetry":
            return abs(rep.hip_y_l_at_bottom - rep.hip_y_r_at_bottom)
        elif feature_name == "depth_deficit":
            avg_hip_y = (rep.hip_y_l_at_bottom + rep.hip_y_r_at_bottom) / 2.0
            avg_knee_y = (
                rep.knee_y_l_at_bottom + rep.knee_y_r_at_bottom
            ) / 2.0
            return max(0.0, avg_hip_y - avg_knee_y)
        else:
            return getattr(rep, feature_name)

    def _aggregate(self, values: list[float], method: str) -> float:
        if not values:
            return 0.0
        if method == "max":
            return max(values)
        elif method == "mean":
            return sum(values) / len(values)
        elif method == "last":
            return values[-1]
        return sum(values) / len(values)

    def _compute_severity(
        self,
        value: float,
        expected: float,
        threshold: float,
        scoring: str,
    ) -> float:
        excess = value - expected
        if scoring == "relative_excess":
            if excess <= threshold:
                return 0.0
            scale = threshold * 2.0 if threshold > 0 else 10.0
            return min(1.0, (excess - threshold) / scale)
        elif scoring == "zscore":
            stdev_estimate = max(threshold, 1.0)
            z = excess / stdev_estimate
            if z <= 1.0:
                return 0.0
            return min(1.0, (z - 1.0) / 2.0)
        return 0.0

    def _pick_representative_rep(
        self, reps: list[RepKinematicSummary]
    ) -> RepKinematicSummary:
        if len(reps) == 1:
            return reps[0]
        sorted_reps = sorted(reps, key=lambda r: r.trunk_pitch_at_bottom)
        return sorted_reps[len(sorted_reps) // 2]

    def _fill_template(
        self,
        template: str,
        rep: RepKinematicSummary,
        anthro: dict,
        rom: dict,
        cause_info: dict[str, Any],
    ) -> str:
        fill_values = {
            "ratio": anthro.get("femur_torso_ratio", 1.0),
            "expected_lean": 30.0
            + (anthro.get("femur_torso_ratio", 1.0) - 1.0) * 120.0,
            "current_ratio": rep.stance_width_ratio,
            "recommended_ratio": max(1.0, rep.stance_width_ratio + 0.15),
            "current_angle": (
                rep.foot_direction_angle_l + rep.foot_direction_angle_r
            )
            / 2.0,
            "recommended_angle": 22.0,
            "current_df": max(rep.ankle_df_l_max, rep.ankle_df_r_max),
            "expected_df": rom.get("dorsiflexion_drop", 35.0),
            "heavier_side": "left"
            if rep.hip_y_l_at_bottom < rep.hip_y_r_at_bottom
            else "right",
            "tighter_side": "left"
            if rep.hip_y_l_at_bottom > rep.hip_y_r_at_bottom
            else "right",
            "first_bad_rep": rep.rep_number,
            "reduction_pct": 10.0,
        }
        try:
            return template.format(**fill_values)
        except (KeyError, IndexError):
            return template
