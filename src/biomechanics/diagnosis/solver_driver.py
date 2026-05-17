from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from ..optimizer.whatif import whatif_solve
from ..optimizer.ik import _fk_jac, _build_descendants
from ..skeleton.definition import SkeletonModel
from .types import DiagnosisResult


V1_COST_WEIGHTS: dict[str, float] = {
    "torque_proxy": 0.0,
}

_FOOT_CONVERGENCE_TOLERANCE = 1e-3  # 1mm

_RELAXATION_PRIORITY = [
    ("torso_pitch", ["trunk.rx"]),
    ("depth", ["L_hip.rx", "R_hip.rx", "L_knee.rx", "R_knee.rx"]),
    ("stance", ["__foot_target_delta"]),
]


class FormSolverResult(BaseModel):
    q_corrected: list[float]
    converged: bool
    applied_perturbation: dict
    relaxations: list[str]
    cost_terms_used: list[str]


class FormSolverDriver:
    def __init__(self, skeleton: SkeletonModel, kinematic_cost_config: dict | None = None):
        self.skeleton = skeleton
        self.cost_weights = {**V1_COST_WEIGHTS, **(kinematic_cost_config or {})}
        self._desc = _build_descendants(skeleton)

    def solve(
        self,
        q_observed_bottom: np.ndarray,
        diagnosis: DiagnosisResult,
        anthro: dict,
    ) -> FormSolverResult:
        perturbation, foot_target_delta = self._split_perturbation(
            diagnosis.combined_perturbation
        )

        relaxations: list[str] = []
        converged = False

        for relaxation_step in range(len(_RELAXATION_PRIORITY) + 1):
            q_corrected = whatif_solve(
                self.skeleton,
                q_observed_bottom,
                perturbation,
                cost_weights=self.cost_weights,
                foot_target_delta=foot_target_delta,
            )

            converged = self._check_convergence(
                q_observed_bottom, q_corrected, foot_target_delta
            )
            if converged:
                break

            if relaxation_step >= len(_RELAXATION_PRIORITY):
                break

            relaxation_name, keys = _RELAXATION_PRIORITY[relaxation_step]
            perturbation, foot_target_delta = self._apply_relaxation(
                perturbation, foot_target_delta, keys
            )
            relaxations.append(relaxation_name)

        cost_terms_used = [
            term for term, weight in {**{"pose_deviation": 1.0, "torque_proxy": 0.5,
                                         "load_over_midfoot": 2.0, "knee_tracking": 1.0,
                                         "balance_margin": 0.5}, **self.cost_weights}.items()
            if weight > 0.0
        ]

        return FormSolverResult(
            q_corrected=q_corrected.tolist(),
            converged=converged,
            applied_perturbation={
                **perturbation,
                **({"__foot_target_delta": foot_target_delta.tolist()}
                   if foot_target_delta is not None else {}),
            },
            relaxations=relaxations,
            cost_terms_used=cost_terms_used,
        )

    def _split_perturbation(
        self, combined: dict
    ) -> tuple[dict[str, float], np.ndarray | None]:
        perturbation = {k: v for k, v in combined.items() if k != "__foot_target_delta"}
        foot_raw = combined.get("__foot_target_delta")
        foot_target_delta = np.array(foot_raw, dtype=float) if foot_raw else None
        return perturbation, foot_target_delta

    def _check_convergence(
        self,
        q_fitted: np.ndarray,
        q_corrected: np.ndarray,
        foot_target_delta: np.ndarray | None,
    ) -> bool:
        lai = self.skeleton.joint_index("L_ankle")
        rai = self.skeleton.joint_index("R_ankle")

        pos_ref, _ = _fk_jac(self.skeleton, q_fitted, self._desc)
        foot_targets = np.array([pos_ref[lai], pos_ref[rai]])
        if foot_target_delta is not None:
            foot_targets[0] += foot_target_delta[:3]
            foot_targets[1] += foot_target_delta[3:]

        pos_result, _ = _fk_jac(self.skeleton, q_corrected, self._desc)
        error_l = np.linalg.norm(pos_result[lai] - foot_targets[0])
        error_r = np.linalg.norm(pos_result[rai] - foot_targets[1])

        return (error_l + error_r) < _FOOT_CONVERGENCE_TOLERANCE

    def _apply_relaxation(
        self,
        perturbation: dict[str, float],
        foot_target_delta: np.ndarray | None,
        keys: list[str],
    ) -> tuple[dict[str, float], np.ndarray | None]:
        perturbation = perturbation.copy()
        foot_target_delta = foot_target_delta.copy() if foot_target_delta is not None else None

        for key in keys:
            if key == "__foot_target_delta" and foot_target_delta is not None:
                foot_target_delta *= 0.5
            elif key in perturbation:
                perturbation[key] *= 0.5

        return perturbation, foot_target_delta
