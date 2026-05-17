"""Extract the bottom frame (deepest squat position) from a rep's q-trajectory.

Bottom is defined as the frame with minimum average hip Y position after FK.

Edge cases:
- Multiple local minima (pause at bottom): returns the FIRST global minimum.
- Noisy trajectories: a 5-frame moving average smooths typical jitter.
  If the trajectory has fewer than 5 frames, smoothing is skipped.
- Very short trajectories (<2 frames): returns frame 0.
"""

from __future__ import annotations

import numpy as np

from ..optimizer.ik import _fk_jac, _build_descendants
from ..skeleton.definition import SkeletonModel

_SMOOTHING_WINDOW = 5


def extract_bottom_q(
    rep_trajectory: np.ndarray,
    skeleton: SkeletonModel,
) -> tuple[int, np.ndarray]:
    """Given a rep's q-trajectory, return (bottom_frame_index, q_at_bottom).

    Parameters
    ----------
    rep_trajectory : (n_frames, n_dof) array
    skeleton : SkeletonModel with joint_masses set

    Returns
    -------
    bottom_frame_index : int
    q_at_bottom : (n_dof,) array
    """
    n_frames = rep_trajectory.shape[0]
    if n_frames == 0:
        raise ValueError("rep_trajectory is empty")
    if n_frames == 1:
        return 0, rep_trajectory[0]

    desc = _build_descendants(skeleton)
    l_hip_idx = skeleton.joint_index("L_hip")
    r_hip_idx = skeleton.joint_index("R_hip")

    hip_y_values = np.empty(n_frames)
    for frame_index in range(n_frames):
        pos, _ = _fk_jac(skeleton, rep_trajectory[frame_index], desc)
        hip_y_values[frame_index] = (pos[l_hip_idx, 1] + pos[r_hip_idx, 1]) / 2.0

    if n_frames >= _SMOOTHING_WINDOW:
        pad_width = _SMOOTHING_WINDOW // 2
        padded = np.pad(hip_y_values, pad_width, mode="edge")
        kernel = np.ones(_SMOOTHING_WINDOW) / _SMOOTHING_WINDOW
        smoothed = np.convolve(padded, kernel, mode="valid")
    else:
        smoothed = hip_y_values

    bottom_frame_index = int(np.argmin(smoothed))
    return bottom_frame_index, rep_trajectory[bottom_frame_index]
