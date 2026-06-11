"""Tests for demo_builder pose stack and cue metadata construction."""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.diagnosis.demo_builder import (
    CORRECTOR_CAUSE_ORDER,
    GENERIC_MAGNITUDE_TEXT,
    build_demo_data,
    build_pose_stack,
    order_demo_causes,
    summarize_cue_magnitude,
)
from biomechanics.diagnosis.keypoint_corrector import (
    ANKLE_L,
    ANKLE_R,
    FOOT_L,
    FOOT_R,
    HIP_L,
    HIP_R,
    KNEE_L,
    KNEE_R,
)
from biomechanics.diagnosis.types import DiagnosisResult, HypothesizedCause

STACK_TOL = 1e-5


def _make_19pt_skeleton() -> list[list[float]]:
    kpts = np.zeros((19, 3))

    kpts[0] = [0.0, 1.6, 0.0]
    kpts[5] = [0.0, 1.2, -0.18]
    kpts[6] = [0.0, 1.2, 0.18]
    kpts[7] = [0.15, 1.0, -0.20]
    kpts[8] = [0.15, 1.0, 0.20]
    kpts[9] = [0.25, 0.85, -0.20]
    kpts[10] = [0.25, 0.85, 0.20]

    kpts[HIP_L] = [0.0, 0.50, -0.15]
    kpts[HIP_R] = [0.0, 0.50, 0.15]
    kpts[KNEE_L] = [0.10, 0.30, -0.13]
    kpts[KNEE_R] = [0.10, 0.30, 0.13]
    kpts[ANKLE_L] = [0.0, 0.0, -0.15]
    kpts[ANKLE_R] = [0.0, 0.0, 0.15]
    kpts[FOOT_L] = [0.15, 0.0, -0.15]
    kpts[FOOT_R] = [0.15, 0.0, 0.15]

    return kpts.tolist()


def _make_cause(cause_id: str, parameter_delta: dict | None) -> HypothesizedCause:
    return HypothesizedCause(
        cause_id=cause_id,
        tier=1,
        score=0.8,
        evidence_score=0.7,
        prior=0.3,
        implicated_by=["test"],
        parameter_delta=parameter_delta,
        explanation=f"{cause_id} explanation",
    )


def _make_diagnosis(cause_ids: list[str]) -> DiagnosisResult:
    delta_by_id: dict[str, dict] = {
        "narrow_stance": {"__foot_target_delta": [0.0, 0.0, -0.04, 0.0, 0.0, 0.04]},
        "narrow_foot_angle": {"L_ankle.ry": 0.15, "R_ankle.ry": -0.15},
        "knee_track_cue": {"L_hip.ry": -0.08, "R_hip.ry": 0.08},
        "weight_shift_cue": {"pelvis.tx": 0.02},
        "depth_cue_unfamiliar": {"depth_target": "parallel"},
    }
    causes = [_make_cause(cid, delta_by_id.get(cid)) for cid in cause_ids]
    return DiagnosisResult(
        set_id="test",
        detected_symptoms=[],
        immediate_causes=causes,
        session_causes=[],
        longterm_causes=[],
        contextual_notes=[],
        combined_perturbation={},
        confidence=0.8,
    )


def _stance_width(pose: np.ndarray) -> float:
    return float(np.linalg.norm(pose[ANKLE_R] - pose[ANKLE_L]))


class TestOrderDemoCauses:

    def test_orders_by_corrector_application_order(self) -> None:
        diagnosis = _make_diagnosis(["knee_track_cue", "narrow_stance"])

        ordered = order_demo_causes(diagnosis)

        assert [c.cause_id for c in ordered] == ["narrow_stance", "knee_track_cue"]

    def test_excludes_unsupported_cause_ids(self) -> None:
        diagnosis = _make_diagnosis(["narrow_stance"])
        diagnosis.immediate_causes.append(_make_cause("brace_trunk_cue", None))

        ordered = order_demo_causes(diagnosis)

        assert [c.cause_id for c in ordered] == ["narrow_stance"]

    def test_empty_list_when_no_immediate_causes(self) -> None:
        diagnosis = _make_diagnosis([])

        assert order_demo_causes(diagnosis) == []


class TestBuildPoseStack:

    def test_stack_length_is_cause_count_plus_one(self) -> None:
        diagnosis = _make_diagnosis(["narrow_stance", "knee_track_cue"])

        pose_stack = build_pose_stack(_make_19pt_skeleton(), diagnosis)

        assert pose_stack is not None
        assert pose_stack.shape == (3, 19, 3)

    def test_first_pose_equals_observed(self) -> None:
        observed = _make_19pt_skeleton()
        diagnosis = _make_diagnosis(["narrow_stance"])

        pose_stack = build_pose_stack(observed, diagnosis)

        assert pose_stack is not None
        np.testing.assert_allclose(pose_stack[0], np.array(observed), atol=STACK_TOL)

    def test_stance_width_increases_with_stance_cue(self) -> None:
        diagnosis = _make_diagnosis(["narrow_stance"])

        pose_stack = build_pose_stack(_make_19pt_skeleton(), diagnosis)

        assert pose_stack is not None
        assert _stance_width(pose_stack[1]) > _stance_width(pose_stack[0])

    def test_corrections_accumulate_across_prefixes(self) -> None:
        diagnosis = _make_diagnosis(["narrow_stance", "knee_track_cue"])

        pose_stack = build_pose_stack(_make_19pt_skeleton(), diagnosis)

        assert pose_stack is not None
        widened = _stance_width(pose_stack[1])
        assert widened > _stance_width(pose_stack[0])
        assert _stance_width(pose_stack[2]) == pytest.approx(widened, abs=0.02)

    def test_returns_none_when_no_supported_causes(self) -> None:
        diagnosis = _make_diagnosis([])

        assert build_pose_stack(_make_19pt_skeleton(), diagnosis) is None


class TestSummarizeCueMagnitude:

    def test_narrow_stance_reports_centimeters_per_side(self) -> None:
        text = summarize_cue_magnitude(
            "narrow_stance",
            {"__foot_target_delta": [0.0, 0.0, -0.04, 0.0, 0.0, 0.04]},
        )

        assert "4 centimeters" in text
        assert "each side" in text

    def test_foot_angle_reports_degrees(self) -> None:
        text = summarize_cue_magnitude(
            "narrow_foot_angle", {"L_ankle.ry": 0.35, "R_ankle.ry": -0.35},
        )

        assert "20" in text
        assert "degrees" in text

    def test_knee_track_reports_degrees(self) -> None:
        text = summarize_cue_magnitude(
            "knee_track_cue", {"L_hip.ry": -0.14, "R_hip.ry": 0.14},
        )

        assert "8" in text
        assert "degrees" in text

    def test_weight_shift_reports_centimeters(self) -> None:
        text = summarize_cue_magnitude("weight_shift_cue", {"pelvis.tx": -0.03})

        assert "3 centimeters" in text

    def test_depth_cue_reports_parallel(self) -> None:
        assert "parallel" in summarize_cue_magnitude("depth_cue_unfamiliar", None)

    def test_missing_delta_returns_generic_text(self) -> None:
        assert summarize_cue_magnitude("narrow_stance", None) == GENERIC_MAGNITUDE_TEXT

    def test_unknown_cause_returns_generic_text(self) -> None:
        assert summarize_cue_magnitude("mystery_cause", {"x": 1.0}) == GENERIC_MAGNITUDE_TEXT


class TestBuildDemoData:

    def test_cues_match_stack_segments(self) -> None:
        diagnosis = _make_diagnosis(["narrow_stance", "knee_track_cue"])

        demo = build_demo_data(_make_19pt_skeleton(), diagnosis)

        assert demo is not None
        assert len(demo.cues) == 2
        assert demo.pose_stack.shape[0] == len(demo.cues) + 1
        assert demo.cues[0].cause_id == "narrow_stance"
        assert demo.cues[0].cue_index == 0
        assert demo.cues[1].cue_index == 1

    def test_returns_none_without_supported_causes(self) -> None:
        diagnosis = _make_diagnosis([])

        assert build_demo_data(_make_19pt_skeleton(), diagnosis) is None
