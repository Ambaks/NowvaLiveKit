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

from biomechanics.viz.dashboard import DebugDashboard
from biomechanics.viz.window_anim import precreate_window, animate_window_fullscreen
from biomechanics.viz.demo_renderer import DemoChoreographer

__all__ = [
    "draw_skeleton",
    "draw_fps",
    "draw_skeleton_with_fps",
    "draw_keypoint_labels",
    "FPSCounter",
    "DebugDashboard",
    "precreate_window",
    "animate_window_fullscreen",
    "DemoChoreographer",
]
