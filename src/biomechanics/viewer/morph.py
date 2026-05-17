"""Pre-compute morph animation frames between observed and corrected poses."""

from __future__ import annotations

import numpy as np

from ..optimizer.temporal import gaussian_taper
from ..skeleton.definition import SkeletonModel
from .keypoints import q_to_keypoints_19


def precompute_morph_frames(
    skeleton: SkeletonModel,
    q_observed: np.ndarray,
    q_corrected: np.ndarray,
    n_morph_frames: int = 60,
) -> list[list[list[float]]]:
    """Pre-compute keypoint arrays for a looping morph animation.

    The first half eases from observed to corrected using a Gaussian
    taper as visual timing.  The second half mirrors back to observed.

    Parameters
    ----------
    skeleton : scaled SkeletonModel
    q_observed : (n_dof,) observed DOF at squat bottom
    q_corrected : (n_dof,) corrected DOF at squat bottom
    n_morph_frames : total frames in the loop (~2 s at 30 fps)

    Returns
    -------
    List of *n_morph_frames* keypoint arrays, each 19 x [x, y, z].
    """
    half = n_morph_frames // 2
    taper_weights = gaussian_taper(half, half - 1, sigma_frames=half / 3.0)

    delta_q = q_corrected - q_observed

    forward_frames: list[list[list[float]]] = []
    for frame_index in range(half):
        alpha = float(taper_weights[frame_index])
        q_blended = q_observed + alpha * delta_q
        forward_frames.append(q_to_keypoints_19(skeleton, q_blended))

    reverse_frames = list(reversed(forward_frames))
    return forward_frames + reverse_frames
