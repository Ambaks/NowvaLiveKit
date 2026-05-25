"""FK helper functions wrapping MuJoCo's forward kinematics and dynamics."""

from __future__ import annotations

import mujoco
import numpy as np

from biomechanics_v2.model.skeleton_model import MujocoSkeleton, N_DOF


def joint_world_positions(skeleton: MujocoSkeleton, q: np.ndarray) -> dict[str, np.ndarray]:
    """Set q, run forward, return joint name -> (3,) world position."""
    skeleton.set_qpos(q)
    skeleton.forward()
    return skeleton.get_body_positions()


def body_com_world(skeleton: MujocoSkeleton, q: np.ndarray) -> np.ndarray:
    """Mass-weighted COM (3,). Uses MuJoCo's built-in COM computation."""
    skeleton.set_qpos(q)
    skeleton.forward()
    return skeleton.get_body_com()


def midfoot_xz(skeleton: MujocoSkeleton, q: np.ndarray) -> np.ndarray:
    """Midpoint of L/R foot centers in XZ plane (2,).

    Uses ankle + toe positions to approximate foot center, then averages L/R.
    """
    positions = joint_world_positions(skeleton, q)
    foot_centers = []
    for side in ("L", "R"):
        ankle_pos = positions[f"{side}_ankle"]
        toe_pos = positions[f"{side}_toe"]
        foot_center = (ankle_pos + toe_pos) / 2.0
        foot_centers.append(foot_center)

    midpoint = (foot_centers[0] + foot_centers[1]) / 2.0
    return np.array([midpoint[0], midpoint[2]])


def inverse_dynamics(
    skeleton: MujocoSkeleton,
    q: np.ndarray,
    qvel: np.ndarray,
    qacc: np.ndarray,
) -> np.ndarray:
    """Compute joint torques via mj_inverse. Returns torques in DOF order.

    Sets qpos/qvel/qacc in MuJoCo's native layout, runs inverse dynamics,
    then reads qfrc_inverse back into DOF order.
    """
    model = skeleton.model
    data = skeleton.data

    skeleton.set_qpos(q)

    native_qvel = np.zeros(model.nv)
    native_qacc = np.zeros(model.nv)
    for i in range(N_DOF):
        mj_idx = skeleton._dof_to_qpos_idx[i]
        native_qvel[mj_idx] = qvel[i]
        native_qacc[mj_idx] = qacc[i]

    data.qvel[:] = native_qvel
    data.qacc[:] = native_qacc

    mujoco.mj_inverse(model, data)

    torques = np.zeros(N_DOF)
    for i in range(N_DOF):
        mj_idx = skeleton._dof_to_qpos_idx[i]
        torques[i] = data.qfrc_inverse[mj_idx]
    return torques


def joint_jacobian(
    skeleton: MujocoSkeleton,
    q: np.ndarray,
    body_name: str,
) -> np.ndarray:
    """Compute 3 x nv positional Jacobian for a body via mj_jac.

    Returns the Jacobian in MuJoCo's native velocity-space dimensions (3, nv).
    """
    model = skeleton.model
    data = skeleton.data

    skeleton.set_qpos(q)
    skeleton.forward()

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    jacp = np.zeros((3, model.nv))
    jacr = np.zeros((3, model.nv))
    mujoco.mj_jac(model, data, jacp, jacr, data.xpos[body_id], body_id)

    return jacp
