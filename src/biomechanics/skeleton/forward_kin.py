"""Forward kinematics for the articulated skeleton."""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from .definition import SkeletonModel
from .anthropometry import SEGMENT_TO_JOINTS, SEGMENT_COM_PROXIMAL_FRACTION, SEGMENT_MASS_FRACTIONS


def _local_transform(offset: np.ndarray, dof_axes: tuple[str, ...], dof_values: np.ndarray) -> np.ndarray:
    """Build 4x4 local transform from joint offset and DOF values."""
    T = np.eye(4)
    T[:3, 3] = offset

    trans_vals = []
    rot_axes = []
    rot_vals = []
    for axis, val in zip(dof_axes, dof_values):
        if axis.startswith("t"):
            idx = "xyz".index(axis[1])
            trans_vals.append((idx, val))
        else:
            rot_axes.append(axis[1].upper())
            rot_vals.append(val)

    for idx, val in trans_vals:
        T[idx, 3] = val

    if rot_vals:
        axes_str = "".join(rot_axes)
        R = Rotation.from_euler(axes_str, rot_vals, degrees=False)
        T[:3, :3] = R.as_matrix()

    return T


def forward_kinematics(skeleton: SkeletonModel, q: np.ndarray) -> dict[str, np.ndarray]:
    """Compute world transforms for all joints. Returns dict of joint_name -> 4x4 matrix."""
    transforms: dict[str, np.ndarray] = {}

    for i, jdef in enumerate(skeleton.joints):
        s = skeleton.joint_dofs(jdef.name)
        dof_vals = q[s]

        if jdef.name == "pelvis":
            T = np.eye(4)
            T[0, 3] = dof_vals[0]  # tx
            T[1, 3] = dof_vals[1]  # ty
            T[2, 3] = dof_vals[2]  # tz
            if len(dof_vals) > 3:
                rot_axes = [a[1].upper() for a in jdef.dof_axes[3:]]
                rot_vals = dof_vals[3:]
                R = Rotation.from_euler("".join(rot_axes), rot_vals, degrees=False)
                T[:3, :3] = R.as_matrix()
            transforms[jdef.name] = T
        else:
            offset = skeleton.offset(i)
            local_T = _local_transform(offset, jdef.dof_axes, dof_vals)
            parent_name = jdef.parent
            parent_T = transforms[parent_name]
            # World = parent * (translate to child offset) * (rotate)
            child_T = np.eye(4)
            child_T[:3, 3] = offset
            child_T[:3, :3] = local_T[:3, :3]
            transforms[jdef.name] = parent_T @ child_T

    return transforms


def joint_world_position(skeleton: SkeletonModel, q: np.ndarray, joint_name: str) -> np.ndarray:
    """Get 3D world position of a single joint."""
    transforms = forward_kinematics(skeleton, q)
    return transforms[joint_name][:3, 3].copy()


def body_com_world(skeleton: SkeletonModel, q: np.ndarray, weight_kg: float = 75.0) -> np.ndarray:
    """Mass-weighted center of mass in world space."""
    transforms = forward_kinematics(skeleton, q)
    com = np.zeros(3)
    total_mass = 0.0

    for seg_name, (prox_joint, dist_joint) in SEGMENT_TO_JOINTS.items():
        if prox_joint not in transforms:
            continue

        frac = SEGMENT_MASS_FRACTIONS.get(seg_name, 0.0)
        mass = frac * weight_kg

        prox_pos = transforms[prox_joint][:3, 3]

        if prox_joint == dist_joint:
            # Trunk: COM is at proximal fraction of segment along local Y
            seg_length = np.linalg.norm(skeleton.offset(skeleton.joint_index(prox_joint)))
            local_com_offset = np.array([0, seg_length * SEGMENT_COM_PROXIMAL_FRACTION[seg_name], 0])
            com_world = transforms[prox_joint][:3, :3] @ local_com_offset + prox_pos
        else:
            dist_pos = transforms[dist_joint][:3, 3]
            alpha = SEGMENT_COM_PROXIMAL_FRACTION[seg_name]
            com_world = prox_pos + alpha * (dist_pos - prox_pos)

        com += mass * com_world
        total_mass += mass

    # Add foot mass (at ankle + small offset downward)
    for side in ("L", "R"):
        ankle_name = f"{side}_ankle"
        if ankle_name in transforms:
            foot_mass = SEGMENT_MASS_FRACTIONS[f"{side}_foot"] * weight_kg
            ankle_pos = transforms[ankle_name][:3, 3]
            foot_com = ankle_pos + np.array([0, -0.03, 0.05])
            com += foot_mass * foot_com
            total_mass += foot_mass

    # Arms and head lumped to trunk (already included in trunk mass via anthropometry)
    # Their COM is approximated above the trunk joint
    arm_head_segs = ["head", "L_upper_arm", "R_upper_arm", "L_forearm_hand", "R_forearm_hand"]
    arm_head_mass = sum(SEGMENT_MASS_FRACTIONS[s] for s in arm_head_segs) * weight_kg
    if "trunk" in transforms:
        trunk_pos = transforms["trunk"][:3, 3]
        trunk_up = transforms["trunk"][:3, :3] @ np.array([0, 0.15, 0])
        arm_head_com = trunk_pos + trunk_up
        com += arm_head_mass * arm_head_com
        total_mass += arm_head_mass

    if total_mass > 0:
        com /= total_mass

    return com


def load_reference_point(skeleton: SkeletonModel, q: np.ndarray) -> np.ndarray:
    """C7-ish load reference: trunk world position + [0, 0.20, 0] in trunk frame."""
    transforms = forward_kinematics(skeleton, q)
    trunk_T = transforms["trunk"]
    local_offset = np.array([0, 0.20, 0])
    world_offset = trunk_T[:3, :3] @ local_offset
    return trunk_T[:3, 3] + world_offset


def midfoot_xz(skeleton: SkeletonModel, q: np.ndarray) -> np.ndarray:
    """Midpoint of left and right foot centers in the xz plane."""
    transforms = forward_kinematics(skeleton, q)
    foot_centers = []
    for side in ("L", "R"):
        ankle_pos = transforms[f"{side}_ankle"][:3, 3]
        # Approximate foot center: ankle + forward offset in ankle frame
        ankle_R = transforms[f"{side}_ankle"][:3, :3]
        foot_fwd = ankle_R @ np.array([0, -0.05, 0.10])
        foot_center = ankle_pos + foot_fwd
        foot_centers.append(foot_center)

    mid = (foot_centers[0] + foot_centers[1]) / 2.0
    return np.array([mid[0], mid[2]])
