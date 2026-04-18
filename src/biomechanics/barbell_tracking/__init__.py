"""
Real-time barbell detection & tracking.

Public entry points:
- BarbellDetector     - YOLO11n-pose wrapper, per-frame bar keypoint detection
- KalmanFilter2D      - constant-velocity Kalman filter used internally
- BarPathTracker      - smooths bar keypoints, maintains path history, derives velocity/accel
- draw_barbell_overlay - cv2 drawing helpers for the demo script
"""

from biomechanics.barbell_tracking.detector import BarbellDetector
from biomechanics.barbell_tracking.kalman import KalmanFilter2D
from biomechanics.barbell_tracking.tracker import BarPathTracker
from biomechanics.barbell_tracking.overlay import (
    draw_barbell_overlay,
    draw_detection_only,
)

__all__ = [
    "BarbellDetector",
    "KalmanFilter2D",
    "BarPathTracker",
    "draw_barbell_overlay",
    "draw_detection_only",
]
