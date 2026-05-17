"""Inverse kinematics via L-BFGS-B with analytical Jacobian."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.ndimage import gaussian_filter1d

from ..skeleton.definition import SkeletonModel

_AX = {"x": 0, "y": 1, "z": 2}


def _rot3(a: str, t: float) -> np.ndarray:
    """Single-axis 3×3 rotation matrix."""
    c, s = np.cos(t), np.sin(t)
    if a == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if a == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _build_descendants(skel: SkeletonModel) -> list[np.ndarray]:
    """Per-joint array of descendant indices (excluding self)."""
    n = skel.n_joints
    ch: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        p = skel.parent_index(i)
        if p >= 0:
            ch[p].append(i)
    d: list[set[int]] = [set() for _ in range(n)]
    for i in range(n - 1, -1, -1):
        for c in ch[i]:
            d[i].add(c)
            d[i] |= d[c]
    return [np.array(sorted(s), dtype=np.intp) for s in d]


def _fk_jac(
    skel: SkeletonModel, q: np.ndarray, desc: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    """FK positions (n_joints, 3) and Jacobian (n_joints*3, n_dof).

    Single-pass FK then a Jacobian sweep using the geometric Jacobian
    formula: for rotation DOF theta_i at joint j with world-frame axis a_i,
    d(pos_k)/d(theta_i) = a_i x (pos_k - pos_j) for every descendant k.
    """
    nj = skel.n_joints
    nd = skel.n_dof
    pos = np.zeros((nj, 3))
    Rw: list[np.ndarray | None] = [None] * nj
    J = np.zeros((nj * 3, nd))

    # ── forward pass: positions & world rotations ──
    for i, jd in enumerate(skel.joints):
        sl = skel.joint_dofs(jd.name)
        v = q[sl]
        if jd.parent is None:
            for ax, val in zip(jd.dof_axes, v):
                if ax[0] == "t":
                    pos[i, _AX[ax[1]]] = val
            R = np.eye(3)
            for ax, val in zip(jd.dof_axes, v):
                if ax[0] == "r":
                    R = R @ _rot3(ax[1], val)
            Rw[i] = R
        else:
            pi = skel.parent_index(i)
            pos[i] = pos[pi] + Rw[pi] @ skel.offset(i)
            Rl = np.eye(3)
            for ax, val in zip(jd.dof_axes, v):
                if ax[0] == "r":
                    Rl = Rl @ _rot3(ax[1], val)
            Rw[i] = Rw[pi] @ Rl

    # ── Jacobian pass ──
    for i, jd in enumerate(skel.joints):
        sl = skel.joint_dofs(jd.name)
        v = q[sl]
        d0 = sl.start
        di = desc[i]

        if jd.parent is None:
            Rpre = np.eye(3)
            for k, (ax, val) in enumerate(zip(jd.dof_axes, v)):
                col = d0 + k
                if ax[0] == "t":
                    dim = _AX[ax[1]]
                    J[dim::3, col] = 1.0
                else:
                    u = np.zeros(3)
                    u[_AX[ax[1]]] = 1.0
                    wa = Rpre @ u
                    for j in di:
                        J[j * 3 : j * 3 + 3, col] = np.cross(wa, pos[j] - pos[i])
                    Rpre = Rpre @ _rot3(ax[1], val)
        else:
            Rpar = Rw[skel.parent_index(i)]
            Rpre = np.eye(3)
            for k, (ax, val) in enumerate(zip(jd.dof_axes, v)):
                col = d0 + k
                if ax[0] == "r":
                    u = np.zeros(3)
                    u[_AX[ax[1]]] = 1.0
                    wa = Rpar @ Rpre @ u
                    for j in di:
                        J[j * 3 : j * 3 + 3, col] = np.cross(wa, pos[j] - pos[i])
                    Rpre = Rpre @ _rot3(ax[1], val)

    return pos, J


def _landmark_knee_priors(
    skel: SkeletonModel,
    landmarks: np.ndarray,
    vis_threshold: float,
    weight: float,
) -> list[tuple[int, float, float]]:
    """Estimate knee flexion directly from observed hip-knee-ankle triangles."""
    if weight <= 0:
        return []

    priors: list[tuple[int, float, float]] = []
    bounds = skel.bounds()
    for side in ("L", "R"):
        hip_i = skel.joint_index(f"{side}_hip")
        knee_i = skel.joint_index(f"{side}_knee")
        ankle_i = skel.joint_index(f"{side}_ankle")
        conf = float(np.min(landmarks[[hip_i, knee_i, ankle_i], 3]))
        if conf < vis_threshold:
            continue

        hip = landmarks[hip_i, :3]
        knee = landmarks[knee_i, :3]
        ankle = landmarks[ankle_i, :3]
        thigh = hip - knee
        shank = ankle - knee
        denom = float(np.linalg.norm(thigh) * np.linalg.norm(shank))
        if denom < 1e-8:
            continue

        internal = float(np.arccos(np.clip(np.dot(thigh, shank) / denom, -1.0, 1.0)))
        flexion = np.pi - internal
        dof = skel.dof_index(f"{side}_knee", "rx")
        lo, hi = bounds[dof]
        priors.append((dof, float(np.clip(flexion, lo, hi)), weight * conf))

    return priors


# ───────────────────────────── public API ──────────────────────────────


def fit_frame(
    skeleton: SkeletonModel,
    landmarks: np.ndarray,
    q_init: np.ndarray | None = None,
    depth_mode: str = "metric",
    vis_threshold: float = 0.5,
    weights: np.ndarray | None = None,
    knee_angle_weight: float = 0.08,
    reg_weights: np.ndarray | None = None,
    q_ref: np.ndarray | None = None,
    max_iter: int = 50,
    _desc: list[np.ndarray] | None = None,
) -> np.ndarray:
    """Fit joint angles to one frame of 3-D landmarks via L-BFGS-B.

    Parameters
    ----------
    skeleton : SkeletonModel
    landmarks : (n_joints, 4)  [x, y, z, visibility]
    q_init : initial q; defaults to neutral_q()
    depth_mode : "metric" (calibrated 3-D) or "relative" (single-cam z)
    vis_threshold : minimum visibility to include a landmark
    weights : per-joint scalar weights (n_joints,)
    knee_angle_weight : soft metric-mode prior from observed hip-knee-ankle angle
    reg_weights : per-DOF regularization weights (n_dof,); None to disable
    q_ref : reference pose for regularization; defaults to q_init
    max_iter : L-BFGS-B iteration budget
    _desc : precomputed descendant arrays (internal optimisation)

    Returns
    -------
    q : (n_dof,)
    """
    nj, nd = skeleton.n_joints, skeleton.n_dof
    assert landmarks.shape == (nj, 4)

    if q_init is None:
        q_init = skeleton.neutral_q()

    obs = landmarks[:, :3].copy()
    vis = landmarks[:, 3]
    active = vis >= vis_threshold

    if weights is None:
        weights = np.ones(nj)

    w = np.zeros(nj * 3)
    for j in range(nj):
        if active[j]:
            w[j * 3 : j * 3 + 3] = vis[j] * weights[j]

    relative = depth_mode == "relative"
    if relative:
        for j in range(nj):
            w[j * 3 + 2] *= 0.3

    desc = _desc if _desc is not None else _build_descendants(skeleton)
    bds = skeleton.bounds()
    knee_priors = [] if relative else _landmark_knee_priors(
        skeleton, landmarks, vis_threshold, knee_angle_weight
    )

    def add_knee_priors(cost: float, grad: np.ndarray, q: np.ndarray) -> tuple[float, np.ndarray]:
        for dof, target, prior_w in knee_priors:
            err = q[dof] - target
            cost += 0.5 * prior_w * err * err
            grad[dof] += prior_w * err
        return cost, grad

    if reg_weights is not None:
        _reg_w = np.asarray(reg_weights, dtype=np.float64)
        _q_ref = q_ref if q_ref is not None else q_init.copy()
    else:
        _reg_w = None
        _q_ref = None

    def add_regularization(cost: float, grad: np.ndarray, q: np.ndarray) -> tuple[float, np.ndarray]:
        if _reg_w is not None:
            delta = q - _q_ref
            cost += 0.5 * np.dot(_reg_w * delta, delta)
            grad = grad + _reg_w * delta
        return cost, grad

    if relative:

        def fg(x: np.ndarray) -> tuple[float, np.ndarray]:
            q, s = x[:nd], x[nd]
            tgt = obs.copy()
            tgt[:, 2] *= s
            p, Jm = _fk_jac(skeleton, q, desc)
            r = (p - tgt).ravel()
            wr = w * r
            c = 0.5 * wr.dot(r)
            gq = Jm.T @ wr
            gs = 0.0
            for j in range(nj):
                if active[j]:
                    gs -= w[j * 3 + 2] * r[j * 3 + 2] * obs[j, 2]
            c, gq = add_knee_priors(c, gq, q)
            c, gq = add_regularization(c, gq, q)
            return c, np.append(gq, gs)

        x0 = np.append(q_init, 1.0)
        all_bds = bds + [(0.01, 100.0)]
    else:

        def fg(x: np.ndarray) -> tuple[float, np.ndarray]:
            p, Jm = _fk_jac(skeleton, x, desc)
            r = (p - obs).ravel()
            wr = w * r
            c, g = add_knee_priors(0.5 * wr.dot(r), Jm.T @ wr, x)
            return add_regularization(c, g, x)

        x0 = q_init.copy()
        all_bds = bds

    res = minimize(
        fg,
        x0,
        jac=True,
        method="L-BFGS-B",
        bounds=all_bds,
        options={"maxiter": max_iter, "ftol": 1e-10, "gtol": 1e-6},
    )
    return res.x[:nd]


def fit_trajectory(
    skeleton: SkeletonModel,
    landmarks: np.ndarray,
    q_init: np.ndarray | None = None,
    depth_mode: str = "metric",
    vis_threshold: float = 0.5,
    weights: np.ndarray | None = None,
    knee_angle_weight: float = 0.08,
    reg_weights: np.ndarray | None = None,
    q_ref: np.ndarray | None = None,
    smooth_sigma: float = 1.5,
    max_iter: int = 50,
) -> np.ndarray:
    """Fit a full trajectory with warm-starting and Gaussian smoothing.

    Parameters
    ----------
    landmarks : (T, n_joints, 4)
    reg_weights : per-DOF regularization weights (n_dof,); None to disable
    q_ref : reference pose for regularization; defaults to q_init
    smooth_sigma : Gaussian kernel sigma in frames (0 to disable)

    Returns
    -------
    q_trajectory : (T, n_dof)
    """
    T = landmarks.shape[0]
    nd = skeleton.n_dof
    q_traj = np.zeros((T, nd))

    q_prev = q_init if q_init is not None else skeleton.neutral_q()
    desc = _build_descendants(skeleton)

    for t in range(T):
        q_traj[t] = fit_frame(
            skeleton,
            landmarks[t],
            q_init=q_prev,
            depth_mode=depth_mode,
            vis_threshold=vis_threshold,
            weights=weights,
            knee_angle_weight=knee_angle_weight,
            reg_weights=reg_weights,
            q_ref=q_ref,
            max_iter=max_iter,
            _desc=desc,
        )
        q_prev = q_traj[t]

    if smooth_sigma > 0:
        q_traj = gaussian_filter1d(q_traj, sigma=smooth_sigma, axis=0)
        bounds = skeleton.bounds()
        for i, (lo, hi) in enumerate(bounds):
            q_traj[:, i] = np.clip(q_traj[:, i], lo, hi)

    return q_traj
