"""
2D skeleton overlay visualization.

Provides functions to draw skeleton keypoints and limb connections
on video frames using OpenCV.
"""

import time
from typing import Optional, Tuple
import cv2
import numpy as np

from biomechanics.pose.base import COCO_SKELETON_CONNECTIONS
from biomechanics.utils.types import Skeleton2D


# Default colors
COLOR_HIGH_CONF = (0, 255, 0)     # Green for high confidence
COLOR_LOW_CONF = (0, 255, 255)   # Yellow for low confidence
COLOR_LIMB = (255, 255, 255)      # White for limb connections
COLOR_FPS = (0, 255, 0)           # Green for FPS counter


class FPSCounter:
    """Simple FPS counter using exponential moving average."""

    def __init__(self, smoothing: float = 0.9):
        """
        Initialize FPS counter.

        Args:
            smoothing: EMA smoothing factor (higher = smoother)
        """
        self.smoothing = smoothing
        self._fps = 0.0
        self._last_time = None

    def update(self) -> float:
        """
        Update FPS calculation with current frame.

        Returns:
            Current smoothed FPS value
        """
        current_time = time.time()

        if self._last_time is not None:
            dt = current_time - self._last_time
            if dt > 0:
                instant_fps = 1.0 / dt
                self._fps = self.smoothing * self._fps + (1 - self.smoothing) * instant_fps

        self._last_time = current_time
        return self._fps

    @property
    def fps(self) -> float:
        """Get current FPS value."""
        return self._fps


def draw_skeleton(
    frame: np.ndarray,
    skeleton: Skeleton2D,
    keypoint_radius: int = 5,
    limb_thickness: int = 2,
    confidence_threshold: float = 0.3,
    color_high: Tuple[int, int, int] = COLOR_HIGH_CONF,
    color_low: Tuple[int, int, int] = COLOR_LOW_CONF,
    color_limb: Tuple[int, int, int] = COLOR_LIMB,
    draw_confidence: bool = False,
) -> np.ndarray:
    """
    Draw skeleton overlay on a frame.

    Args:
        frame: BGR image to draw on (modified in place)
        skeleton: 2D skeleton with keypoints
        keypoint_radius: Radius of keypoint circles
        limb_thickness: Thickness of limb lines
        confidence_threshold: Threshold for high/low confidence coloring
        color_high: Color for high confidence keypoints (BGR)
        color_low: Color for low confidence keypoints (BGR)
        color_limb: Color for limb connections (BGR)
        draw_confidence: If True, draw confidence values next to keypoints

    Returns:
        Frame with skeleton overlay (same as input, modified in place)
    """
    if skeleton is None or not skeleton.keypoints:
        return frame

    # Draw limb connections first (so keypoints are on top)
    for start_idx, end_idx in COCO_SKELETON_CONNECTIONS:
        if start_idx < len(skeleton.keypoints) and end_idx < len(skeleton.keypoints):
            kp_start = skeleton.keypoints[start_idx]
            kp_end = skeleton.keypoints[end_idx]

            # Only draw if both keypoints are valid
            if kp_start.confidence > 0 and kp_end.confidence > 0:
                pt1 = (int(kp_start.x), int(kp_start.y))
                pt2 = (int(kp_end.x), int(kp_end.y))
                cv2.line(frame, pt1, pt2, color_limb, limb_thickness)

    # Draw keypoints
    for idx, kp in enumerate(skeleton.keypoints):
        if kp.confidence <= 0:
            continue

        x, y = int(kp.x), int(kp.y)

        # Choose color based on confidence
        color = color_high if kp.confidence >= confidence_threshold else color_low

        # Draw filled circle
        cv2.circle(frame, (x, y), keypoint_radius, color, -1)

        # Draw confidence value if requested
        if draw_confidence:
            text = f"{kp.confidence:.2f}"
            cv2.putText(
                frame,
                text,
                (x + keypoint_radius + 2, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                color,
                1,
            )

    return frame


def draw_fps(
    frame: np.ndarray,
    fps: float,
    position: Tuple[int, int] = (10, 30),
    color: Tuple[int, int, int] = COLOR_FPS,
    font_scale: float = 0.8,
    thickness: int = 2,
) -> np.ndarray:
    """
    Draw FPS counter on frame.

    Args:
        frame: BGR image to draw on (modified in place)
        fps: FPS value to display
        position: Top-left position of text
        color: Text color (BGR)
        font_scale: Font scale
        thickness: Font thickness

    Returns:
        Frame with FPS overlay (same as input, modified in place)
    """
    text = f"FPS: {fps:.1f}"
    cv2.putText(
        frame,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        thickness,
    )
    return frame


def draw_skeleton_with_fps(
    frame: np.ndarray,
    skeleton: Optional[Skeleton2D],
    fps_counter: FPSCounter,
    **kwargs,
) -> np.ndarray:
    """
    Draw skeleton and FPS counter on frame.

    Convenience function that combines draw_skeleton() and draw_fps().

    Args:
        frame: BGR image to draw on (modified in place)
        skeleton: 2D skeleton with keypoints (can be None)
        fps_counter: FPS counter instance (will be updated)
        **kwargs: Additional arguments passed to draw_skeleton()

    Returns:
        Frame with skeleton and FPS overlay
    """
    fps = fps_counter.update()

    if skeleton is not None:
        draw_skeleton(frame, skeleton, **kwargs)

    draw_fps(frame, fps)

    return frame


def draw_keypoint_labels(
    frame: np.ndarray,
    skeleton: Skeleton2D,
    labels: Optional[list[str]] = None,
    color: Tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.4,
) -> np.ndarray:
    """
    Draw keypoint labels/names on frame.

    Args:
        frame: BGR image to draw on
        skeleton: 2D skeleton with keypoints
        labels: List of labels (uses COCO names if None)
        color: Text color (BGR)
        font_scale: Font scale

    Returns:
        Frame with labels overlay
    """
    from biomechanics.pose.base import COCO_KEYPOINT_NAMES

    if labels is None:
        labels = COCO_KEYPOINT_NAMES

    for idx, kp in enumerate(skeleton.keypoints):
        if kp.confidence <= 0 or idx >= len(labels):
            continue

        x, y = int(kp.x), int(kp.y)
        label = labels[idx]

        cv2.putText(
            frame,
            label,
            (x + 8, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            1,
        )

    return frame
