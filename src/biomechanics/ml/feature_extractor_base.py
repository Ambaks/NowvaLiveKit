"""
Feature Extractor Protocol

Defines the interface that all feature extractors must satisfy.
Both LandmarkFeatureExtractor (lower-body) and UpperBodyFeatureExtractor
implement this protocol.
"""

from typing import Protocol, runtime_checkable

import numpy as np

from biomechanics.utils.types import Skeleton3D


@runtime_checkable
class FeatureExtractor(Protocol):
    """Protocol for skeleton-to-feature-vector extractors."""

    FEATURE_DIM: int

    def extract(self, skeleton: Skeleton3D) -> np.ndarray:
        """Extract a fixed-length feature vector from one frame's skeleton.

        Returns:
            numpy array of shape (FEATURE_DIM,)
        """
        ...
