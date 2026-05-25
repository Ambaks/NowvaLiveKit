"""Forward-dynamics what-if solver — perturbation → physics settling → corrected pose.

Replaces V1's SLSQP-based whatif.py with MuJoCo forward simulation.
Physics (gravity, contacts, joint limits, damping) finds a stable pose
instead of minimising a hand-crafted cost function.
"""

from __future__ import annotations

import mujoco
import numpy as np

from biomechanics_v2.model.skeleton_model import MujocoSkeleton, N_DOF
from biomechanics_v2.solver.temporal import gaussian_taper


class MujocoWhatIfSolver:
    """Apply joint perturbations and forward-simulate until settled."""

    def __init__(self, skeleton: MujocoSkeleton):
        self._skeleton = skeleton

        # Enable energy computation for settling detection
        skeleton.model.opt.enableflags |= mujoco.mjtEnableBit.mjENBL_ENERGY

        # Cache the actuator → qpos mapping (each position servo targets one joint)
        model = skeleton.model
        self._actuator_qpos_map = np.zeros(model.nu, dtype=np.intp)
        for actuator_idx in range(model.nu):
            joint_id = model.actuator_trnid[actuator_idx, 0]
            self._actuator_qpos_map[actuator_idx] = model.jnt_qposadr[joint_id]

    def solve(
        self,
        q_fitted: np.ndarray,
        perturbation: dict[str, float],
        foot_target_delta: np.ndarray | None = None,
        joint_limit_overrides: dict[str, tuple[float, float]] | None = None,
        max_steps: int = 500,
        energy_threshold: float = 1e-6,
    ) -> np.ndarray:
        """Apply perturbation and forward-simulate until settled.

        Returns (20,) q_corrected in radians.
        """
        model = self._skeleton.model

        saved_ranges = None
        if joint_limit_overrides:
            saved_ranges = model.jnt_range.copy()
            for key, (low_rad, high_rad) in joint_limit_overrides.items():
                mj_joint_name = key.replace(".", "_")
                joint_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, mj_joint_name
                )
                model.jnt_range[joint_id] = [low_rad, high_rad]

        try:
            data = mujoco.MjData(model)

            # Set qpos from q_fitted
            self._write_qpos(data, q_fitted)

            # Apply joint-angle perturbations
            for key, delta_rad in perturbation.items():
                joint_name, axis = key.split(".")
                dof_idx = self._skeleton.get_joint_index(joint_name, axis)
                mj_qpos_idx = self._skeleton._dof_to_qpos_idx[dof_idx]
                data.qpos[mj_qpos_idx] += delta_rad

            # Disable all weld constraints (they are for IK, not what-if)
            if model.neq > 0:
                data.eq_active[:] = 0

            # Handle foot position targets via ankle weld constraints
            if foot_target_delta is not None:
                self._apply_foot_targets(model, data, np.asarray(foot_target_delta))

            # Position servos hold the perturbed pose; gravity/contacts adjust
            self._sync_ctrl_to_qpos(data)

            # Zero velocities — start from rest
            data.qvel[:] = 0

            # Forward-simulate until kinetic energy settles
            for _ in range(max_steps):
                mujoco.mj_step(model, data)
                if data.energy[1] < energy_threshold:
                    break

            return self._read_qpos(data)

        finally:
            if saved_ranges is not None:
                model.jnt_range[:] = saved_ranges

    def warp_trajectory(
        self,
        q_trajectory: np.ndarray,
        bottom_frame: int,
        perturbation: dict[str, float],
        foot_target_delta: np.ndarray | None = None,
        joint_limit_overrides: dict[str, tuple[float, float]] | None = None,
        sigma_frames: float | None = None,
    ) -> np.ndarray:
        """Apply what-if correction across trajectory with Gaussian taper.

        Returns (T, 20) warped trajectory.
        """
        num_frames = q_trajectory.shape[0]

        q_corrected = self.solve(
            q_fitted=q_trajectory[bottom_frame],
            perturbation=perturbation,
            foot_target_delta=foot_target_delta,
            joint_limit_overrides=joint_limit_overrides,
        )

        delta = q_corrected - q_trajectory[bottom_frame]

        taper = gaussian_taper(num_frames, bottom_frame, sigma_frames)

        warped = q_trajectory + taper[:, np.newaxis] * delta[np.newaxis, :]

        # Clip to joint bounds
        bounds = self._skeleton.get_bounds()
        for dof_idx in range(N_DOF):
            low, high = bounds[dof_idx]
            if np.isfinite(low) and np.isfinite(high):
                warped[:, dof_idx] = np.clip(warped[:, dof_idx], low, high)

        return warped

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_qpos(self, data: mujoco.MjData, q: np.ndarray) -> None:
        for i in range(N_DOF):
            data.qpos[self._skeleton._dof_to_qpos_idx[i]] = q[i]

    def _read_qpos(self, data: mujoco.MjData) -> np.ndarray:
        q_out = np.zeros(N_DOF)
        for i in range(N_DOF):
            q_out[i] = data.qpos[self._skeleton._dof_to_qpos_idx[i]]
        return q_out

    def _sync_ctrl_to_qpos(self, data: mujoco.MjData) -> None:
        """Set each position servo's control to its joint's current qpos."""
        for actuator_idx in range(len(self._actuator_qpos_map)):
            qpos_adr = self._actuator_qpos_map[actuator_idx]
            data.ctrl[actuator_idx] = data.qpos[qpos_adr]

    def _apply_foot_targets(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        foot_delta: np.ndarray,
    ) -> None:
        """Set ankle mocap targets and enable ankle weld constraints."""
        # FK to get current ankle world positions
        mujoco.mj_forward(model, data)

        for side, delta_slice in [
            ("L_ankle", foot_delta[:3]),
            ("R_ankle", foot_delta[3:]),
        ]:
            body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, side
            )
            current_ankle_pos = data.xpos[body_id].copy()

            mocap_body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, f"mocap_{side}"
            )
            mocap_idx = model.body_mocapid[mocap_body_id]
            data.mocap_pos[mocap_idx] = current_ankle_pos + delta_slice

        # Enable weld constraints for ankles only
        for eq_idx in range(model.neq):
            if model.eq_type[eq_idx] == mujoco.mjtEq.mjEQ_WELD:
                body1_id = model.eq_obj1id[eq_idx]
                body_name = mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_BODY, body1_id
                )
                if body_name in ("L_ankle", "R_ankle"):
                    data.eq_active[eq_idx] = 1
