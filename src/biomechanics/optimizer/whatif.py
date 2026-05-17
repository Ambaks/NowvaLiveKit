"""Single-frame what-if optimizer with hard constraints.

Produces a corrected q vector that can be fed through
``q_to_joint_angles()`` for downstream fault comparison.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from ..skeleton.definition import SkeletonModel
from .ik import _fk_jac, _build_descendants
from .costs import (
    _com_from_pos,
    _com_jac,
    _support_bounds,
    combined_cost_and_grad,
)


DEFAULT_COST_WEIGHTS: dict[str, float] = {
    "pose_deviation": 1.0,
    "torque_proxy": 0.5,
    "load_over_midfoot": 2.0,
    "knee_tracking": 1.0,
    "balance_margin": 0.5,
}

_PERTURBATION_LOCK_WEIGHT = 50.0


def whatif_solve(
    skeleton: SkeletonModel,
    q_fitted: np.ndarray,
    perturbation: dict[str, float],
    cost_weights: dict[str, float] | None = None,
    max_iter: int = 100,
    foot_target_delta: np.ndarray | None = None,
) -> np.ndarray:
    """Single-frame SLSQP what-if optimizer.

    Parameters
    ----------
    skeleton : SkeletonModel  (must have ``joint_masses`` via ``scale_skeleton``)
    q_fitted : (n_dof,) — original fitted joint angles from IK
    perturbation : ``{"joint.axis": delta_rad, ...}``
        e.g. ``{"L_hip.rx": 0.09, "R_hip.rx": 0.09}``
    cost_weights : per-term weights (defaults to ``DEFAULT_COST_WEIGHTS``)
    max_iter : SLSQP iteration limit
    foot_target_delta : (6,) array ``[dLx, dLy, dLz, dRx, dRy, dRz]`` or None

    Returns
    -------
    q_corrected : (n_dof,)
    """
    assert skeleton.joint_masses is not None, "call scale_skeleton() first"
    weights = {**DEFAULT_COST_WEIGHTS, **(cost_weights or {})}
    nd = skeleton.n_dof
    desc = _build_descendants(skeleton)
    bounds = skeleton.bounds()

    # ── precompute foot targets & support polygon from fitted pose ──
    pos0, _ = _fk_jac(skeleton, q_fitted, desc)
    lai = skeleton.joint_index("L_ankle")
    rai = skeleton.joint_index("R_ankle")
    foot_targets = np.array([pos0[lai], pos0[rai]])
    if foot_target_delta is not None:
        foot_target_delta = np.asarray(foot_target_delta)
        foot_targets[0] += foot_target_delta[:3]
        foot_targets[1] += foot_target_delta[3:]
    sup = _support_bounds(skeleton, pos0)

    # ── build perturbed reference + per-DOF weights ──
    q_ref = q_fitted.copy()
    dof_w = np.ones(nd)
    perturbed_indices: set[int] = set()
    for key, delta in perturbation.items():
        joint, axis = key.split(".")
        idx = skeleton.dof_index(joint, axis)
        q_ref[idx] += delta
        dof_w[idx] = _PERTURBATION_LOCK_WEIGHT
        perturbed_indices.add(idx)

    # Tighten bounds so non-perturbed DOFs stay near the fitted pose,
    # preventing the optimizer from jumping to flipped IK branches.
    _MAX_WANDER = 0.52  # ~30 deg
    for i in range(nd):
        lo, hi = bounds[i]
        if i not in perturbed_indices:
            bounds[i] = (max(lo, q_fitted[i] - _MAX_WANDER),
                         min(hi, q_fitted[i] + _MAX_WANDER))
    for side in ("L_hip", "R_hip"):
        hip_rx_idx = skeleton.dof_index(side, "rx")
        lo, hi = bounds[hip_rx_idx]
        bounds[hip_rx_idx] = (max(lo, 0.0), hi)

    for i, (lo, hi) in enumerate(bounds):
        q_ref[i] = np.clip(q_ref[i], lo, hi)

    q0 = q_ref.copy()

    # ── objective (all 5 costs, single FK) ──
    def objective(q):
        return combined_cost_and_grad(
            skeleton, q, q_ref, weights, sup, desc,
            dof_weights=dof_w,
        )

    # ── feet-rooted equality constraint ──
    def feet_eq(q):
        pos, _ = _fk_jac(skeleton, q, desc)
        return np.concatenate([pos[lai] - foot_targets[0],
                               pos[rai] - foot_targets[1]])

    def feet_jac(q):
        _, J = _fk_jac(skeleton, q, desc)
        return np.vstack([J[lai * 3 : lai * 3 + 3, :],
                          J[rai * 3 : rai * 3 + 3, :]])

    # ── COM-inside-polygon inequality constraint (>= 0) ──
    x_min, x_max, z_min, z_max = sup

    def com_ineq(q):
        pos, _ = _fk_jac(skeleton, q, desc)
        com = _com_from_pos(skeleton, pos)
        return np.array([
            com[0] - x_min,
            x_max - com[0],
            com[2] - z_min,
            z_max - com[2],
        ])

    def com_ineq_jac(q):
        pos, J = _fk_jac(skeleton, q, desc)
        cj = _com_jac(skeleton, J)
        return np.vstack([cj[0, :], -cj[0, :], cj[2, :], -cj[2, :]])

    constraints = [
        {"type": "eq", "fun": feet_eq, "jac": feet_jac},
        {"type": "ineq", "fun": com_ineq, "jac": com_ineq_jac},
    ]

    res = minimize(
        objective,
        q0,
        jac=True,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": max_iter, "ftol": 1e-10},
    )

    return res.x
