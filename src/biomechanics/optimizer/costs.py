"""All 5 soft cost terms for the what-if optimizer.

Each public cost function takes a SkeletonModel and q vector and returns
(cost, gradient_wrt_q).  Internal ``_eval_*`` implementations accept
pre-computed FK data so the combined evaluator can share a single FK pass.
"""

from __future__ import annotations

import numpy as np

from ..skeleton.definition import SkeletonModel
from .ik import _fk_jac, _build_descendants


# ─── helpers ────────────────────────────────────────────────────────────

def _com_from_pos(skeleton: SkeletonModel, pos: np.ndarray) -> np.ndarray:
    segment_params = skeleton.segment_params
    if segment_params is None:
        m = skeleton.joint_masses
        return (m[:, None] * pos).sum(axis=0) / m.sum()
    com = np.zeros(3)
    for proximal_idx, distal_idx, mass_frac, com_ratio in segment_params:
        com += mass_frac * (
            pos[proximal_idx] + com_ratio * (pos[distal_idx] - pos[proximal_idx])
        )
    return com


def _com_jac(skeleton: SkeletonModel, J: np.ndarray) -> np.ndarray:
    segment_params = skeleton.segment_params
    if segment_params is None:
        m = skeleton.joint_masses
        total = m.sum()
        nj = skeleton.n_joints
        jac = np.zeros((3, J.shape[1]))
        for j in range(nj):
            jac += (m[j] / total) * J[j * 3 : j * 3 + 3, :]
        return jac
    jac = np.zeros((3, J.shape[1]))
    for proximal_idx, distal_idx, mass_frac, com_ratio in segment_params:
        jac += mass_frac * (
            (1 - com_ratio) * J[proximal_idx * 3 : proximal_idx * 3 + 3, :]
            + com_ratio * J[distal_idx * 3 : distal_idx * 3 + 3, :]
        )
    return jac


def _support_bounds(skeleton: SkeletonModel, pos: np.ndarray):
    lai = skeleton.joint_index("L_ankle")
    rai = skeleton.joint_index("R_ankle")
    x_min = min(pos[lai, 0], pos[rai, 0]) - 0.05
    x_max = max(pos[lai, 0], pos[rai, 0]) + 0.05
    z_mid = (pos[lai, 2] + pos[rai, 2]) * 0.5
    return (x_min, x_max, z_mid - 0.10, z_mid + 0.15)


# ─── internal cost evaluators (pre-computed FK) ────────────────────────

_TORQUE_JOINTS = ("L_ankle", "R_ankle", "L_knee", "R_knee", "L_hip", "R_hip")


def _eval_pose_deviation(q, q_ref, weight, dof_weights=None):
    diff = q - q_ref
    if dof_weights is not None:
        w = weight * dof_weights
        return 0.5 * np.dot(w * diff, diff), w * diff
    return 0.5 * weight * diff.dot(diff), weight * diff


def _eval_torque_proxy(skeleton, pos, J, com, cj, weight):
    cost = 0.0
    grad = np.zeros(J.shape[1])
    for jname in _TORQUE_JOINTS:
        ji = skeleton.joint_index(jname)
        dx = com[0] - pos[ji, 0]
        dz = com[2] - pos[ji, 2]
        cost += dx ** 2 + dz ** 2
        grad += 2 * dx * (cj[0, :] - J[ji * 3, :])
        grad += 2 * dz * (cj[2, :] - J[ji * 3 + 2, :])
    return 0.5 * weight * cost, 0.5 * weight * grad


def _eval_load_over_midfoot(skeleton, pos, J, com, cj, weight):
    lai = skeleton.joint_index("L_ankle")
    rai = skeleton.joint_index("R_ankle")
    lti = skeleton.joint_index("L_toe")
    rti = skeleton.joint_index("R_toe")

    left_midfoot = 0.5 * (pos[lai] + pos[lti])
    right_midfoot = 0.5 * (pos[rai] + pos[rti])
    midfoot_center = 0.5 * (left_midfoot + right_midfoot)

    dx = com[0] - midfoot_center[0]
    dz = com[2] - midfoot_center[2]
    cost = dx ** 2 + dz ** 2

    midfoot_jac_x = 0.25 * (J[lai * 3, :] + J[lti * 3, :] + J[rai * 3, :] + J[rti * 3, :])
    midfoot_jac_z = 0.25 * (J[lai * 3 + 2, :] + J[lti * 3 + 2, :] + J[rai * 3 + 2, :] + J[rti * 3 + 2, :])
    grad = 2 * dx * (cj[0, :] - midfoot_jac_x) + 2 * dz * (cj[2, :] - midfoot_jac_z)

    return 0.5 * weight * cost, 0.5 * weight * grad


def _eval_knee_tracking(skeleton, pos, J, weight):
    cost = 0.0
    grad = np.zeros(J.shape[1])
    for side in ("L", "R"):
        ki = skeleton.joint_index(f"{side}_knee")
        ai = skeleton.joint_index(f"{side}_ankle")
        ti = skeleton.joint_index(f"{side}_toe")

        toe_dir = pos[ti] - pos[ai]
        toe_dir[1] = 0.0
        toe_len = np.linalg.norm(toe_dir)
        if toe_len < 1e-6:
            toe_dir = np.array([0.0, 0.0, 1.0])
            toe_len = 1.0
        toe_hat = toe_dir / toe_len

        perp = np.array([-toe_hat[2], 0.0, toe_hat[0]])

        knee_rel = pos[ki] - pos[ai]
        lateral_error = np.dot(knee_rel, perp)

        cost += lateral_error ** 2
        d_knee_rel_dq = J[ki * 3 : ki * 3 + 3, :] - J[ai * 3 : ai * 3 + 3, :]
        grad += 2 * lateral_error * (perp @ d_knee_rel_dq)

    return 0.5 * weight * cost, 0.5 * weight * grad


_SYMMETRY_PAIRS = [
    ("L_hip", "R_hip", "rx"),
    ("L_hip", "R_hip", "ry"),
    ("L_knee", "R_knee", "rx"),
    ("L_ankle", "R_ankle", "rx"),
    ("L_ankle", "R_ankle", "ry"),
]


def _eval_symmetry(skeleton, q, weight):
    cost = 0.0
    grad = np.zeros(len(q))
    for left_joint, right_joint, axis in _SYMMETRY_PAIRS:
        li = skeleton.dof_index(left_joint, axis)
        ri = skeleton.dof_index(right_joint, axis)
        if axis == "ry":
            diff = q[li] + q[ri]
        else:
            diff = q[li] - q[ri]
        cost += diff ** 2
        if axis == "ry":
            grad[li] += 2 * diff
            grad[ri] += 2 * diff
        else:
            grad[li] += 2 * diff
            grad[ri] -= 2 * diff
    return 0.5 * weight * cost, 0.5 * weight * grad


def _eval_balance_margin(skeleton, pos, J, com, cj, bounds_xz, weight, margin):
    x_min, x_max, z_min, z_max = bounds_xz
    cost = 0.0
    grad = np.zeros(J.shape[1])
    for dist, jd in [
        (com[0] - x_min, cj[0, :]),
        (x_max - com[0], -cj[0, :]),
        (com[2] - z_min, cj[2, :]),
        (z_max - com[2], -cj[2, :]),
    ]:
        if dist < margin:
            v = margin - dist
            cost += v ** 2
            grad -= 2 * v * jd
    return 0.5 * weight * cost, 0.5 * weight * grad


# ─── public API ─────────────────────────────────────────────────────────


def cost_pose_deviation(
    skeleton: SkeletonModel,
    q: np.ndarray,
    q_ref: np.ndarray,
    weight: float = 1.0,
    dof_weights: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """Quadratic penalty on deviation from *q_ref*."""
    return _eval_pose_deviation(q, q_ref, weight, dof_weights)


def cost_torque_proxy(
    skeleton: SkeletonModel,
    q: np.ndarray,
    weight: float = 1.0,
) -> tuple[float, np.ndarray]:
    """Penalise horizontal moment-arms at major joints."""
    desc = _build_descendants(skeleton)
    pos, J = _fk_jac(skeleton, q, desc)
    com = _com_from_pos(skeleton, pos)
    cj = _com_jac(skeleton, J)
    return _eval_torque_proxy(skeleton, pos, J, com, cj, weight)


def cost_load_over_midfoot(
    skeleton: SkeletonModel,
    q: np.ndarray,
    weight: float = 1.0,
) -> tuple[float, np.ndarray]:
    """Penalise COM drifting from midfoot center in the xz plane."""
    desc = _build_descendants(skeleton)
    pos, J = _fk_jac(skeleton, q, desc)
    com = _com_from_pos(skeleton, pos)
    cj = _com_jac(skeleton, J)
    return _eval_load_over_midfoot(skeleton, pos, J, com, cj, weight)


def cost_knee_tracking(
    skeleton: SkeletonModel,
    q: np.ndarray,
    weight: float = 1.0,
) -> tuple[float, np.ndarray]:
    """Penalise knees deviating from ankles in the frontal plane (x)."""
    desc = _build_descendants(skeleton)
    pos, J = _fk_jac(skeleton, q, desc)
    return _eval_knee_tracking(skeleton, pos, J, weight)


def cost_balance_margin(
    skeleton: SkeletonModel,
    q: np.ndarray,
    weight: float = 1.0,
    margin: float = 0.05,
    support_bounds_xz: tuple[float, float, float, float] | None = None,
) -> tuple[float, np.ndarray]:
    """Barrier-like penalty when COM approaches the support-polygon edge."""
    desc = _build_descendants(skeleton)
    pos, J = _fk_jac(skeleton, q, desc)
    com = _com_from_pos(skeleton, pos)
    cj = _com_jac(skeleton, J)
    if support_bounds_xz is None:
        support_bounds_xz = _support_bounds(skeleton, pos)
    return _eval_balance_margin(
        skeleton, pos, J, com, cj, support_bounds_xz, weight, margin,
    )


# ─── combined evaluator (single FK pass for the optimizer) ─────────────


def combined_cost_and_grad(
    skeleton: SkeletonModel,
    q: np.ndarray,
    q_ref: np.ndarray,
    cost_weights: dict[str, float],
    support_bounds_xz: tuple[float, float, float, float],
    desc: list[np.ndarray],
    margin: float = 0.05,
    dof_weights: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """Evaluate all 5 cost terms with a single FK computation."""
    pos, J = _fk_jac(skeleton, q, desc)
    com = _com_from_pos(skeleton, pos)
    cj = _com_jac(skeleton, J)

    tc, tg = 0.0, np.zeros(skeleton.n_dof)

    c, g = _eval_pose_deviation(
        q, q_ref, cost_weights.get("pose_deviation", 1.0), dof_weights,
    )
    tc += c; tg += g

    c, g = _eval_torque_proxy(
        skeleton, pos, J, com, cj, cost_weights.get("torque_proxy", 0.5),
    )
    tc += c; tg += g

    c, g = _eval_load_over_midfoot(
        skeleton, pos, J, com, cj, cost_weights.get("load_over_midfoot", 2.0),
    )
    tc += c; tg += g

    c, g = _eval_knee_tracking(
        skeleton, pos, J, cost_weights.get("knee_tracking", 1.0),
    )
    tc += c; tg += g

    c, g = _eval_balance_margin(
        skeleton, pos, J, com, cj, support_bounds_xz,
        cost_weights.get("balance_margin", 0.5), margin,
    )
    tc += c; tg += g

    symmetry_weight = cost_weights.get("symmetry", 0.0)
    if symmetry_weight > 0:
        c, g = _eval_symmetry(skeleton, q, symmetry_weight)
        tc += c; tg += g

    return tc, tg
