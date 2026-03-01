"""
Pose estimation module.

Provides 2D and 3D pose estimation using various backends:
- MediaPipe (zero-setup fallback)
- RTMPose (higher accuracy, requires ONNX model download)
"""

from biomechanics.pose.base import (
    PoseEstimator,
    COCO_KEYPOINT_NAMES,
    COCO_SKELETON_CONNECTIONS,
)
from biomechanics.pose.mediapipe_fallback import (
    MediaPipePoseEstimator,
    MEDIAPIPE_AVAILABLE,
)

__all__ = [
    "PoseEstimator",
    "COCO_KEYPOINT_NAMES",
    "COCO_SKELETON_CONNECTIONS",
    "MediaPipePoseEstimator",
    "MEDIAPIPE_AVAILABLE",
]
