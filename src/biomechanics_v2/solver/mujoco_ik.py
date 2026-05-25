"""MuJoCo Jacobian-based IK solver — Skeleton3D landmarks → q-trajectory.

Uses damped least-squares (Levenberg-Marquardt style) with analytic Jacobians
from mj_jac. Works in MuJoCo's native qpos space internally, converts to the
20-DOF V1 q-vector via MujocoSkeleton.get_qpos()/set_qpos() at the boundary.
"""

from __future__ import annotations

import mujoco
import numpy as np
from scipy.ndimage import gaussian_filter1d

from biomechanics_v2.model.skeleton_model import MujocoSkeleton, N_DOF

# Body names in the same order as the (17, 4) landmark array
_TARGET_BODY_NAMES = [
    "pelvis", "trunk", "L_hip", "R_hip",
    "L_knee", "R_knee", "L_ankle", "R_ankle",
    "head", "L_toe", "R_toe",
    "L_shoulder", "R_shoulder",
    "L_elbow", "R_elbow",
    "L_wrist", "R_wrist",
]

_N_TARGETS = len(_TARGET_BODY_NAMES)


class MujocoIKSolver:
    """Jacobian-based IK: landmark positions → joint angles via damped least-squares."""

    def __init__(self, skeleton: MujocoSkeleton):
        self._skeleton = skeleton
        self._model = skeleton.model
        self._data = skeleton.data

        self._target_body_ids = np.array([
            mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, name)
            for name in _TARGET_BODY_NAMES
        ], dtype=np.intp)

        self._nv = self._model.nv

        # Pre-compute joint limits in MuJoCo native qpos ordering
        self._bounds_low = np.full(self._nv, -1e6)
        self._bounds_high = np.full(self._nv, 1e6)
        for joint_id in range(self._model.njnt):
            dof_adr = self._model.jnt_dofadr[joint_id]
            if self._model.jnt_limited[joint_id]:
                self._bounds_low[dof_adr] = self._model.jnt_range[joint_id, 0]
                self._bounds_high[dof_adr] = self._model.jnt_range[joint_id, 1]

        # Pre-allocate Jacobian workspace
        self._jacobian_pos = np.zeros((3, self._nv))
        self._full_jacobian = np.zeros((_N_TARGETS * 3, self._nv))
        self._identity_nv = np.eye(self._nv)

    def fit_frame(
        self,
        landmarks: np.ndarray,
        q_init: np.ndarray | None = None,
        vis_threshold: float = 0.5,
        weights: np.ndarray | None = None,
        max_steps: int = 100,
        tolerance_m: float = 0.002,
        damping: float = 1e-3,
    ) -> np.ndarray:
        """Fit single frame. Returns (20,) q-vector in the V1 DOF ordering.

        Parameters
        ----------
        landmarks : (11, 4) array — [x, y, z, visibility] in skeleton Y-up coords.
        q_init : (20,) warm-start in V1 DOF ordering. None → neutral pose.
        vis_threshold : landmarks with visibility < this get zero weight.
        weights : (11,) per-target importance. None → equal weights.
        max_steps : maximum Gauss-Newton iterations.
        tolerance_m : RMSE convergence threshold in meters.
        damping : Tikhonov regularisation for the normal equations.
        """
        target_positions = landmarks[:, :3]
        visibility = landmarks[:, 3]

        # Build per-coordinate weight vector (3 * N_TARGETS,)
        if weights is None:
            per_target_weight = np.ones(_N_TARGETS)
        else:
            per_target_weight = weights.copy()

        per_target_weight[visibility < vis_threshold] = 0.0
        per_coord_weight = np.repeat(per_target_weight, 3)

        # Initialise qpos in MuJoCo native space
        if q_init is not None:
            self._skeleton.set_qpos(q_init)
        else:
            neutral = self._skeleton.neutral_q()
            self._skeleton.set_qpos(neutral)

        active_mask = per_coord_weight > 0.0

        for _ in range(max_steps):
            mujoco.mj_forward(self._model, self._data)

            # Position error
            current_positions = self._data.xpos[self._target_body_ids]
            error_vector = (target_positions - current_positions).reshape(-1)
            weighted_error = per_coord_weight * error_vector

            rmse = _weighted_rmse(weighted_error, active_mask)
            if rmse < tolerance_m:
                break

            # Stacked Jacobian
            for i, body_id in enumerate(self._target_body_ids):
                self._jacobian_pos[:] = 0.0
                mujoco.mj_jac(
                    self._model, self._data,
                    self._jacobian_pos, None,
                    self._data.xpos[body_id], body_id,
                )
                self._full_jacobian[i * 3:(i + 1) * 3] = self._jacobian_pos

            # Apply weights to Jacobian rows
            weighted_jacobian = per_coord_weight[:, None] * self._full_jacobian

            # Damped least-squares: dq = Jw^T (Jw Jw^T + λI)^-1 · weighted_error
            gram = weighted_jacobian @ weighted_jacobian.T
            gram[np.diag_indices_from(gram)] += damping
            rhs = np.linalg.solve(gram, weighted_error)
            delta_q = weighted_jacobian.T @ rhs

            # Line-search with backtracking
            current_qpos = self._data.qpos.copy()
            step_size = 1.0
            accepted = False

            for _ in range(5):
                candidate = np.clip(
                    current_qpos + step_size * delta_q,
                    self._bounds_low, self._bounds_high,
                )
                self._data.qpos[:] = candidate
                mujoco.mj_forward(self._model, self._data)

                new_positions = self._data.xpos[self._target_body_ids]
                new_error = per_coord_weight * (target_positions - new_positions).reshape(-1)
                new_rmse = _weighted_rmse(new_error, active_mask)

                if new_rmse < rmse:
                    accepted = True
                    break
                step_size *= 0.5

            if not accepted:
                self._data.qpos[:] = np.clip(
                    current_qpos + 0.1 * delta_q,
                    self._bounds_low, self._bounds_high,
                )

        return self._skeleton.get_qpos()

    def fit_trajectory(
        self,
        landmarks: np.ndarray,
        q_init: np.ndarray | None = None,
        vis_threshold: float = 0.5,
        weights: np.ndarray | None = None,
        smooth_sigma: float = 1.5,
        max_steps_per_frame: int = 100,
    ) -> np.ndarray:
        """Fit trajectory with warm-starting. Returns (T, 20) q-trajectory.

        Parameters
        ----------
        landmarks : (T, 11, 4) array.
        q_init : (20,) initial q for the first frame. None → neutral.
        vis_threshold : per-frame visibility threshold.
        weights : (11,) static per-target weights (applied every frame).
        smooth_sigma : Gaussian σ for post-hoc q-trajectory smoothing (frames).
                       Set to 0 to disable smoothing.
        max_steps_per_frame : max IK iterations per frame.
        """
        num_frames = landmarks.shape[0]
        q_trajectory = np.zeros((num_frames, N_DOF))

        current_q = q_init

        for frame_idx in range(num_frames):
            frame_landmarks = landmarks[frame_idx]
            solved_q = self.fit_frame(
                frame_landmarks,
                q_init=current_q,
                vis_threshold=vis_threshold,
                weights=weights,
                max_steps=max_steps_per_frame,
            )
            q_trajectory[frame_idx] = solved_q
            current_q = solved_q

        if smooth_sigma > 0.0 and num_frames > 3:
            # Smooth rotational DOFs only (skip pelvis translation 0:3)
            q_trajectory[:, 3:] = gaussian_filter1d(
                q_trajectory[:, 3:], sigma=smooth_sigma, axis=0,
            )
            # Re-clip to bounds after smoothing
            bounds = self._skeleton.get_bounds()
            for dof_idx in range(N_DOF):
                low, high = bounds[dof_idx]
                if np.isfinite(low):
                    q_trajectory[:, dof_idx] = np.clip(
                        q_trajectory[:, dof_idx], low, high,
                    )

        return q_trajectory


def _weighted_rmse(weighted_error: np.ndarray, active_mask: np.ndarray) -> float:
    active_errors = weighted_error[active_mask]
    if len(active_errors) == 0:
        return 0.0
    return float(np.sqrt(np.mean(active_errors ** 2)))
