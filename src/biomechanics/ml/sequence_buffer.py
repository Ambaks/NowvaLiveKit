"""
Sequence Buffer for BiLSTM Input

Accumulates per-frame feature vectors into fixed-length sliding windows
suitable for temporal model input.
"""

from collections import deque
from typing import Optional

import numpy as np


class SequenceBuffer:
    """
    Rolling buffer that collects per-frame feature vectors and returns
    fixed-length sequences for the BiLSTM model.

    Returns None until the buffer has accumulated ``window_size`` frames
    (cold-start period of ~1 second at 30 fps with default window_size=30).
    """

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self._buffer: deque = deque(maxlen=window_size)

    def push(self, features: np.ndarray) -> Optional[np.ndarray]:
        """
        Add one frame's feature vector to the buffer.

        Args:
            features: 1-D array of shape (feature_dim,)

        Returns:
            Array of shape (window_size, feature_dim) when buffer is full,
            None during cold-start.
        """
        self._buffer.append(features)
        if len(self._buffer) < self.window_size:
            return None
        return np.array(self._buffer)

    @property
    def is_ready(self) -> bool:
        """True when the buffer has enough frames for a full sequence."""
        return len(self._buffer) == self.window_size

    def reset(self) -> None:
        """Clear the buffer (e.g. between sets)."""
        self._buffer.clear()
