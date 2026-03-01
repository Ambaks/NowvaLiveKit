"""
Visualization module.

Provides functions for drawing skeleton overlays and debug dashboards.
"""

from biomechanics.viz.overlay_2d import (
    draw_skeleton,
    draw_fps,
    draw_skeleton_with_fps,
    draw_keypoint_labels,
    FPSCounter,
)

__all__ = [
    "draw_skeleton",
    "draw_fps",
    "draw_skeleton_with_fps",
    "draw_keypoint_labels",
    "FPSCounter",
]
