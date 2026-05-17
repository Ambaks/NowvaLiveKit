"""Convert a 20-DOF q vector to 19 COCO-format keypoints for Three.js rendering.

Uses the same FK forward pass as ``_fk_jac`` in ``optimizer/ik.py`` (lines 56-75)
and mirrors the JS ``kinoQToKeypoints`` coordinate transform and upper-body synthesis.
"""

from __future__ import annotations

import numpy as np

from ..optimizer.ik import _rot3, _AX, _build_descendants
from ..skeleton.definition import SkeletonModel

_REF_SHOULDER_WIDTH = 0.36
_REF_HEAD_OFFSET = 0.22
_REF_UPPER_ARM = 0.30
_REF_FOREARM = 0.26
_REF_FOOT_LEN = 0.26


def _fk_pos_and_rotations(
    skeleton: SkeletonModel, q: np.ndarray,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """FK forward pass only — same logic as _fk_jac lines 56-75, no Jacobian."""
    num_joints = skeleton.n_joints
    pos = np.zeros((num_joints, 3))
    Rw: list[np.ndarray | None] = [None] * num_joints

    for i, jd in enumerate(skeleton.joints):
        sl = skeleton.joint_dofs(jd.name)
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
            pi = skeleton.parent_index(i)
            pos[i] = pos[pi] + Rw[pi] @ skeleton.offset(i)
            Rl = np.eye(3)
            for ax, val in zip(jd.dof_axes, v):
                if ax[0] == "r":
                    Rl = Rl @ _rot3(ax[1], val)
            Rw[i] = Rw[pi] @ Rl

    return pos, Rw


def q_to_keypoints_19(skeleton: SkeletonModel, q: np.ndarray) -> list[list[float]]:
    """Convert skeleton DOF vector to 19 COCO keypoints in vis-space.

    Mirrors the JS ``kinoQToKeypoints`` (visualize_video_squats.py lines 2085-2168).
    """
    fk_pos, Rw = _fk_pos_and_rotations(skeleton, q)

    num_joints = skeleton.n_joints

    # --- Axis swap: vis_x=fk_z, vis_y=fk_y, vis_z=fk_x ---
    vis_pos = np.empty((num_joints, 3))
    vis_pos[:, 0] = fk_pos[:, 2]
    vis_pos[:, 1] = fk_pos[:, 1]
    vis_pos[:, 2] = fk_pos[:, 0]

    # --- Ground and center ---
    la_idx = skeleton.joint_index("L_ankle")
    ra_idx = skeleton.joint_index("R_ankle")
    lh_idx = skeleton.joint_index("L_hip")
    rh_idx = skeleton.joint_index("R_hip")

    ankle_min_y = min(vis_pos[la_idx, 1], vis_pos[ra_idx, 1])
    hip_mid_x = (vis_pos[lh_idx, 0] + vis_pos[rh_idx, 0]) / 2
    hip_mid_z = (vis_pos[lh_idx, 2] + vis_pos[rh_idx, 2]) / 2

    vis_pos[:, 0] -= hip_mid_x
    vis_pos[:, 1] -= ankle_min_y
    vis_pos[:, 2] -= hip_mid_z

    # --- Lower-body joints (direct from FK) ---
    kpts = np.zeros((19, 3))
    for joint_name, coco_idx in (
        ("L_hip", 11), ("R_hip", 12),
        ("L_knee", 13), ("R_knee", 14),
        ("L_ankle", 15), ("R_ankle", 16),
    ):
        kpts[coco_idx] = vis_pos[skeleton.joint_index(joint_name)]

    # --- Trunk-rotation-aware upper body (mirrors JS lines 2111-2153) ---
    trunk_idx = skeleton.joint_index("trunk")
    trunk_Rw = Rw[trunk_idx]
    # Trunk local-Y in FK space is column 1 of Rw
    # Swap to vis: vis_x=fk_z, vis_y=fk_y, vis_z=fk_x
    trunk_up_vis = np.array([trunk_Rw[2, 1], trunk_Rw[1, 1], trunk_Rw[0, 1]])

    remaining_torso = 0.22
    sm_x = vis_pos[trunk_idx, 0] + trunk_up_vis[0] * remaining_torso
    sm_y = vis_pos[trunk_idx, 1] + trunk_up_vis[1] * remaining_torso
    sm_z = vis_pos[trunk_idx, 2] + trunk_up_vis[2] * remaining_torso

    sw = _REF_SHOULDER_WIDTH
    kpts[5] = [sm_x, sm_y, sm_z - sw / 2]
    kpts[6] = [sm_x, sm_y, sm_z + sw / 2]

    head_h = _REF_HEAD_OFFSET
    head_x = sm_x + head_h * 0.3 * trunk_up_vis[0] / max(trunk_up_vis[1], 0.3)
    head_y = sm_y + head_h
    kpts[0] = [head_x, head_y, 0.0]
    kpts[1] = [head_x, head_y + 0.02, -0.03]
    kpts[2] = [head_x, head_y + 0.02, 0.03]
    kpts[3] = [head_x, head_y - 0.01, -0.06]
    kpts[4] = [head_x, head_y - 0.01, 0.06]

    elbow_drop = _REF_UPPER_ARM * 0.7 + 0.15
    kpts[7] = [sm_x, sm_y - elbow_drop, -sw / 2]
    kpts[8] = [sm_x, sm_y - elbow_drop, sw / 2]
    kpts[9] = [kpts[7][0] + 0.02, kpts[7][1] - _REF_FOREARM * 0.5, kpts[7][2]]
    kpts[10] = [kpts[8][0] + 0.02, kpts[8][1] - _REF_FOREARM * 0.5, kpts[8][2]]

    # --- Ankle-rotation-aware foot tips (mirrors JS lines 2155-2166) ---
    for ankle_name, foot_idx, ankle_idx in (("L_ankle", 17, 15), ("R_ankle", 18, 16)):
        ankle_Rw = Rw[skeleton.joint_index(ankle_name)]
        # FK Z-axis (column 2) → vis: fwd_vis_x = fk_fwd_z, fwd_vis_z = fk_fwd_x
        fwd_vis_x = ankle_Rw[2, 2]
        fwd_vis_z = ankle_Rw[0, 2]
        fwd_len = np.sqrt(fwd_vis_x**2 + fwd_vis_z**2) or 1.0
        kpts[foot_idx] = [
            kpts[ankle_idx][0] + (fwd_vis_x / fwd_len) * _REF_FOOT_LEN,
            0.0,
            kpts[ankle_idx][2] + (fwd_vis_z / fwd_len) * _REF_FOOT_LEN,
        ]

    return [kpts[i].tolist() for i in range(19)]
