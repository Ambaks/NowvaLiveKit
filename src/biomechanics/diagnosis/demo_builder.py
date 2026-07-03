"""Builds choreographed-demo data (corrected pose stack + cue metadata) from a diagnosis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from .graph.parameter_deltas import (
    magnitude_center_weight,
    magnitude_knees_out,
    magnitude_widen_foot_angle,
    magnitude_widen_stance,
)
from .keypoint_corrector import (
    KeypointCorrector,
    HIP_L, HIP_R, KNEE_L, KNEE_R, ANKLE_L, ANKLE_R,
)
from .types import DiagnosisResult, HypothesizedCause

CORRECTOR_CAUSE_ORDER: tuple[str, ...] = (
    "narrow_stance",
    "narrow_foot_angle",
    "knee_track_cue",
    "weight_shift_cue",
    "depth_cue_unfamiliar",
)

GENERIC_MAGNITUDE_TEXT = "a small adjustment"


class DemoCue(BaseModel):
    cue_index: int
    cause_id: str
    explanation: str
    magnitude_text: str


@dataclass
class DemoData:
    pose_stack: np.ndarray
    cues: list[DemoCue]


# Mirrors the cause_id -> parameter_delta_fn pairing in graph/causes.yaml
_MAGNITUDE_FN_BY_CAUSE = {
    "narrow_stance": magnitude_widen_stance,
    "narrow_foot_angle": magnitude_widen_foot_angle,
    "knee_track_cue": magnitude_knees_out,
    "weight_shift_cue": magnitude_center_weight,
}


def order_demo_causes(diagnosis: DiagnosisResult) -> list[HypothesizedCause]:
    by_id = {cause.cause_id: cause for cause in diagnosis.immediate_causes}
    return [by_id[cause_id] for cause_id in CORRECTOR_CAUSE_ORDER if cause_id in by_id]


def summarize_cue_magnitude(cause_id: str, parameter_delta: dict | None) -> str:
    if cause_id == "depth_cue_unfamiliar":
        return "hips down to parallel depth"
    if parameter_delta is None:
        return GENERIC_MAGNITUDE_TEXT
    magnitude_fn = _MAGNITUDE_FN_BY_CAUSE.get(cause_id)
    if magnitude_fn is None:
        return GENERIC_MAGNITUDE_TEXT
    text = magnitude_fn(parameter_delta)
    return text if text is not None else GENERIC_MAGNITUDE_TEXT


def _prepare_observed_kpts(kpts: list[list[float]]) -> list[list[float]]:
    """Ground, center, and flatten feet — match visualize_video_squats preprocessing."""
    arr = np.array(kpts, dtype=np.float64)
    # Feet parallel to ground: project foot_index Y to ankle Y
    arr[17, 1] = arr[15, 1]
    arr[18, 1] = arr[16, 1]
    # Ground feet to Y=0
    ankle_y = min(arr[15, 1], arr[16, 1])
    arr[:, 1] -= ankle_y
    # Center hips at origin
    hip_mid_x = (arr[11, 0] + arr[12, 0]) / 2
    hip_mid_z = (arr[11, 2] + arr[12, 2]) / 2
    arr[:, 0] -= hip_mid_x
    arr[:, 2] -= hip_mid_z
    return arr.tolist()


def build_pose_stack(
    observed_kpts: list[list[float]],
    diagnosis: DiagnosisResult,
    anthro: dict | None = None,
    rom: dict | None = None,
) -> np.ndarray | None:
    """Incremental corrected poses: stack[k] applies cause k on top of stack[k-1]."""
    ordered = order_demo_causes(diagnosis)
    if not ordered:
        return None

    prepared = _prepare_observed_kpts(observed_kpts)

    prep_arr = np.asarray(prepared, dtype=np.float64)
    bone_lengths = (
        float(np.linalg.norm(prep_arr[KNEE_L] - prep_arr[HIP_L])),
        float(np.linalg.norm(prep_arr[ANKLE_L] - prep_arr[KNEE_L])),
        float(np.linalg.norm(prep_arr[KNEE_R] - prep_arr[HIP_R])),
        float(np.linalg.norm(prep_arr[ANKLE_R] - prep_arr[KNEE_R])),
    )

    corrector = KeypointCorrector()
    pose_stack = np.empty((len(ordered) + 1, 19, 3), dtype=np.float32)
    pose_stack[0] = np.asarray(prepared, dtype=np.float32)

    current = prepared
    for i, cause in enumerate(ordered):
        filtered = diagnosis.model_copy(
            update={"immediate_causes": [cause]}
        )
        corrected = corrector.correct(
            current, filtered, anthro=anthro, rom=rom, bone_lengths=bone_lengths,
        )
        if corrected is None:
            return None
        pose_stack[i + 1] = np.asarray(corrected, dtype=np.float32)
        current = corrected

    # Final pose: single all-causes call matching VVS --diagnose exactly
    full_corrected = corrector.correct(
        prepared, diagnosis, anthro=anthro, rom=rom, bone_lengths=bone_lengths,
    )
    if full_corrected is not None:
        pose_stack[-1] = np.asarray(full_corrected, dtype=np.float32)

    return pose_stack


def build_demo_data(
    observed_kpts: list[list[float]],
    diagnosis: DiagnosisResult,
    anthro: dict | None = None,
    rom: dict | None = None,
) -> DemoData | None:
    pose_stack = build_pose_stack(observed_kpts, diagnosis, anthro=anthro, rom=rom)
    if pose_stack is None:
        return None

    ordered = order_demo_causes(diagnosis)
    cues = [
        DemoCue(
            cue_index=index,
            cause_id=cause.cause_id,
            explanation=cause.explanation,
            magnitude_text=summarize_cue_magnitude(cause.cause_id, cause.parameter_delta),
        )
        for index, cause in enumerate(ordered)
    ]
    return DemoData(pose_stack=pose_stack, cues=cues)
