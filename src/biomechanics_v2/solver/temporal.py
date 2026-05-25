"""Gaussian temporal taper centred on the bottom-of-squat frame."""

from __future__ import annotations

import numpy as np


def gaussian_taper(
    n_frames: int,
    bottom_frame: int,
    sigma_frames: float | None = None,
) -> np.ndarray:
    """Return a (n_frames,) array in [0, 1] peaking at *bottom_frame*.

    Parameters
    ----------
    n_frames : total number of frames in the rep
    bottom_frame : frame index where the correction is maximal (1.0)
    sigma_frames : Gaussian sigma in frame units (default: n_frames / 6)
    """
    if sigma_frames is None:
        sigma_frames = n_frames / 6.0
    t = np.arange(n_frames, dtype=np.float64)
    return np.exp(-0.5 * ((t - bottom_frame) / sigma_frames) ** 2)
