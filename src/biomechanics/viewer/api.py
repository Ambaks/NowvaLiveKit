"""PyWebView JS APIs for the kinodynamics what-if solver and diagnosis viewer.

Exposes Python optimizer methods to the browser-side Three.js renderer
via ``window.pywebview.api``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from ..optimizer.whatif import whatif_solve
from ..optimizer.temporal import gaussian_taper
from ..optimizer.ik import _build_descendants
from ..skeleton.definition import SkeletonModel
from ..skeleton.anthropometry import scale_skeleton
from .keypoints import q_to_keypoints_19
from .morph import precompute_morph_frames


class KinodynamicsAPI:
    """Bridge between browser sliders and the Python SLSQP what-if solver.

    Methods prefixed with nothing are callable from JS via
    ``pywebview.api.method_name(args)``.  They receive and return
    JSON-serialisable types only.
    """

    def __init__(
        self,
        skeleton: SkeletonModel,
        q_trajectory_per_rep: list[np.ndarray],
        rep_boundaries: list | None = None,
    ):
        self._skel = skeleton
        self._q_traj = q_trajectory_per_rep
        self._rep_bounds = rep_boundaries or []
        self._desc = _build_descendants(skeleton)
        self._bounds = skeleton.bounds()
        self._cache_key: str = ""
        self._cache_result: list | None = None

    def _bottom_frame(self, rep_idx: int) -> int:
        if rep_idx < len(self._rep_bounds):
            rb = self._rep_bounds[rep_idx]
            if isinstance(rb, (list, tuple)) and len(rb) > 2:
                return int(rb[2])
        return len(self._q_traj[rep_idx]) // 2

    def warp_rep(
        self,
        rep_idx: int,
        perturbation_json: str,
        foot_target_delta_json: str | None = None,
        cost_weights_json: str | None = None,
    ) -> dict:
        """Compute warped q trajectory for one rep.

        Called from JS when kinodynamics sliders change.

        Parameters
        ----------
        rep_idx : index into q_trajectory_per_rep
        perturbation_json : JSON string like ``'{"L_ankle.rx": 0.09}'``
        foot_target_delta_json : JSON string like ``'[dx_L, dy_L, dz_L, dx_R, dy_R, dz_R]'``
        cost_weights_json : JSON string with per-term cost weights

        Returns
        -------
        dict with ``warped_q`` (list[list[float]] or None) and ``solve_ms``.
        """
        perturbation: dict[str, float] = json.loads(perturbation_json)

        foot_target_delta = None
        if foot_target_delta_json:
            foot_target_delta = np.array(json.loads(foot_target_delta_json))

        cost_weights = None
        if cost_weights_json:
            cost_weights = json.loads(cost_weights_json)

        if not perturbation and foot_target_delta is None:
            return {"warped_q": None, "solve_ms": 0.0}

        cache_key = json.dumps(
            [rep_idx, perturbation, foot_target_delta_json, cost_weights_json],
            sort_keys=True,
        )
        if cache_key == self._cache_key and self._cache_result is not None:
            return {"warped_q": self._cache_result, "solve_ms": 0.0}

        t0 = time.perf_counter()

        q_traj = self._q_traj[rep_idx]
        bottom = self._bottom_frame(rep_idx)

        q_corrected = whatif_solve(
            self._skel, q_traj[bottom], perturbation,
            cost_weights=cost_weights,
            foot_target_delta=foot_target_delta,
        )

        taper = gaussian_taper(len(q_traj), bottom)
        delta = q_corrected - q_traj[bottom]

        warped: list[list[float]] = []
        for t in range(len(q_traj)):
            q_w = q_traj[t] + taper[t] * delta
            for i, (lo, hi) in enumerate(self._bounds):
                q_w[i] = np.clip(q_w[i], lo, hi)
            warped.append(q_w.tolist())

        solve_ms = (time.perf_counter() - t0) * 1000.0

        self._cache_key = cache_key
        self._cache_result = warped

        return {"warped_q": warped, "solve_ms": round(solve_ms, 1)}


_TIER_LABELS = {
    1: "Immediate corrections",
    2: "Session-level recommendations",
    3: "Long-term work",
    0: "Anthropometric context",
}

_TIER_FIELD_MAP = {
    1: "immediate_causes",
    2: "session_causes",
    3: "longterm_causes",
    0: "contextual_notes",
}


class DiagnosisViewerAPI:
    """PyWebView JS API for the diagnosis comparison viewer.

    Loads a diagnosis artifact and serves pre-computed morph frames
    and structured diagnosis text to the browser.
    """

    def __init__(
        self,
        diagnosis_artifact_path: str,
        skeleton: SkeletonModel | None = None,
    ):
        artifact_path = Path(diagnosis_artifact_path)
        with open(artifact_path, encoding="utf-8") as fh:
            self._artifact = json.load(fh)

        for required_key in ("diagnosis", "solver_results", "metadata"):
            if required_key not in self._artifact:
                raise ValueError(f"Artifact missing required key: {required_key}")

        has_solver_results = bool(self._artifact.get("solver_results"))

        if skeleton is not None:
            self._skel = skeleton
        elif has_solver_results:
            metadata = self._artifact["metadata"]
            height_m = metadata.get("height_m")
            weight_kg = metadata.get("weight_kg")
            if height_m is None or weight_kg is None:
                raise ValueError(
                    "Artifact metadata missing height_m/weight_kg and no skeleton provided"
                )
            self._skel = scale_skeleton(float(height_m), float(weight_kg))
        else:
            self._skel = None

        self._rep_data = self._prepare_rep_data() if self._skel else []
        self._diagnosis_text = self._organize_diagnosis_text()

    def _prepare_rep_data(self) -> list[dict]:
        rep_data = []
        for solver_result in self._artifact["solver_results"]:
            q_observed_raw = solver_result.get("q_observed_at_bottom")
            if q_observed_raw is None:
                continue
            q_observed = np.array(q_observed_raw, dtype=np.float64)

            q_corrected_raw = solver_result.get("q_corrected")
            observed_keypoints = q_to_keypoints_19(self._skel, q_observed)

            if q_corrected_raw is not None:
                q_corrected = np.array(q_corrected_raw, dtype=np.float64)
                morph_frames = precompute_morph_frames(
                    self._skel, q_observed, q_corrected
                )
                rep_data.append({
                    "rep_number": solver_result["rep_number"],
                    "morph_frames": morph_frames,
                    "observed_keypoints": observed_keypoints,
                    "corrected_keypoints": q_to_keypoints_19(self._skel, q_corrected),
                    "converged": solver_result.get("converged", False),
                    "has_correction": True,
                })
            else:
                rep_data.append({
                    "rep_number": solver_result["rep_number"],
                    "morph_frames": None,
                    "observed_keypoints": observed_keypoints,
                    "corrected_keypoints": None,
                    "converged": False,
                    "has_correction": False,
                })
        return rep_data

    def _organize_diagnosis_text(self) -> dict:
        diagnosis = self._artifact["diagnosis"]

        tiers = {}
        for tier_number in (1, 2, 3, 0):
            field_name = _TIER_FIELD_MAP[tier_number]
            causes_raw = diagnosis.get(field_name, [])
            causes = []
            for cause in causes_raw:
                cause_entry = {
                    "cause_id": cause["cause_id"],
                    "explanation": cause["explanation"],
                    "score": cause["score"],
                    "implicated_by": cause.get("implicated_by", []),
                }
                if tier_number == 3:
                    cause_id = cause["cause_id"]
                    if cause_id.startswith("limited_"):
                        cause_entry["tag"] = "Mobility"
                    elif cause_id.startswith("weak_"):
                        cause_entry["tag"] = "Strength"
                causes.append(cause_entry)

            tiers[str(tier_number)] = {
                "label": _TIER_LABELS[tier_number],
                "causes": causes,
                "expanded": False,
            }

        first_expanded = False
        for tier_key in ("1", "2", "3", "0"):
            if tiers[tier_key]["causes"] and not first_expanded:
                tiers[tier_key]["expanded"] = True
                first_expanded = True

        symptoms = [
            {
                "symptom_id": s["symptom_id"],
                "severity": s["severity"],
                "contributing_reps": s["contributing_reps"],
            }
            for s in diagnosis.get("detected_symptoms", [])
        ]

        return {
            "tiers": tiers,
            "confidence": diagnosis.get("confidence", 0.0),
            "symptoms": symptoms,
        }

    def get_diagnosis_data(self) -> dict:
        """Called once from JS on page load. Returns all pre-computed data."""
        return {
            "reps": self._rep_data,
            "diagnosis": self._diagnosis_text,
            "metadata": self._artifact.get("metadata", {}),
            "n_morph_frames": 60,
            "morph_fps": 30.0,
        }

    def get_rep_count(self) -> int:
        """Number of reps with solver results."""
        return len(self._rep_data)
