"""
Pose estimation module.

Provides 2D and 3D pose estimation using various backends:
- MediaPipe (zero-setup fallback, includes built-in 3D)
- RTMPose (higher accuracy 2D, requires ONNX model download)
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

try:
    from biomechanics.pose.rtmpose import RTMPoseEstimator

    RTMPOSE_AVAILABLE = True
except ImportError:
    RTMPOSE_AVAILABLE = False

__all__ = [
    "PoseEstimator",
    "COCO_KEYPOINT_NAMES",
    "COCO_SKELETON_CONNECTIONS",
    "MediaPipePoseEstimator",
    "MEDIAPIPE_AVAILABLE",
    "RTMPoseEstimator",
    "RTMPOSE_AVAILABLE",
]
