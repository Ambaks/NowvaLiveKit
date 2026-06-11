"""Builds choreographed-demo data (corrected pose stack + cue metadata) from a diagnosis."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from .keypoint_corrector import KeypointCorrector
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


def _magnitude_narrow_stance(parameter_delta: dict) -> str | None:
    target = parameter_delta.get("__foot_target_delta")
    if not target or len(target) < 6:
        return None
    per_side_cm = round(abs(float(target[5])) * 100.0)
    if per_side_cm <= 0:
        return None
    return f"about {per_side_cm} centimeters wider on each side"


def _magnitude_narrow_foot_angle(parameter_delta: dict) -> str | None:
    radians = parameter_delta.get("L_ankle.ry")
    if radians is None:
        return None
    degrees = round(math.degrees(abs(float(radians))))
    if degrees <= 0:
        return None
    return f"toes turned out about {degrees} more degrees"


def _magnitude_knee_track(parameter_delta: dict) -> str | None:
    radians = parameter_delta.get("R_hip.ry")
    if radians is None:
        return None
    degrees = round(math.degrees(abs(float(radians))))
    if degrees <= 0:
        return None
    return f"knees pushed out about {degrees} degrees more"


def _magnitude_weight_shift(parameter_delta: dict) -> str | None:
    shift_m = parameter_delta.get("pelvis.tx")
    if shift_m is None:
        return None
    shift_cm = round(abs(float(shift_m)) * 100.0)
    if shift_cm <= 0:
        return None
    return f"weight centered by about {shift_cm} centimeters"


_MAGNITUDE_FN_BY_CAUSE = {
    "narrow_stance": _magnitude_narrow_stance,
    "narrow_foot_angle": _magnitude_narrow_foot_angle,
    "knee_track_cue": _magnitude_knee_track,
    "weight_shift_cue": _magnitude_weight_shift,
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


def build_pose_stack(
    observed_kpts: list[list[float]],
    diagnosis: DiagnosisResult,
    anthro: dict | None = None,
    rom: dict | None = None,
) -> np.ndarray | None:
    """Per-prefix corrected poses: stack[k] has the first k corrections applied via full FK."""
    ordered = order_demo_causes(diagnosis)
    if not ordered:
        return None

    corrector = KeypointCorrector()
    pose_stack = np.empty((len(ordered) + 1, 19, 3), dtype=np.float32)
    pose_stack[0] = np.asarray(observed_kpts, dtype=np.float32)

    for prefix_len in range(1, len(ordered) + 1):
        filtered = diagnosis.model_copy(
            update={"immediate_causes": ordered[:prefix_len]}
        )
        corrected = corrector.correct(observed_kpts, filtered, anthro=anthro, rom=rom)
        if corrected is None:
            return None
        pose_stack[prefix_len] = np.asarray(corrected, dtype=np.float32)

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
