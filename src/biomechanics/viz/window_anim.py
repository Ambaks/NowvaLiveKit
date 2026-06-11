"""Window pre-creation and fullscreen animation helpers."""

from __future__ import annotations

import sys

import cv2
import numpy as np

_IS_MACOS = sys.platform == "darwin"
_PYOBJC_AVAILABLE = False

if _IS_MACOS:
    try:
        from AppKit import NSApplication, NSScreen
        _PYOBJC_AVAILABLE = True
    except ImportError:
        pass

_PLACEHOLDER = np.zeros((1, 1, 3), dtype=np.uint8)


def _find_nswindow(window_name: str):
    app = NSApplication.sharedApplication()
    for win in app.windows():
        if win.title() == window_name:
            return win
    return None


def precreate_window(window_name: str) -> None:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1, 1)
    cv2.moveWindow(window_name, -1, -1)
    cv2.imshow(window_name, _PLACEHOLDER)
    cv2.waitKey(1)


def animate_window_fullscreen(window_name: str) -> None:
    if _PYOBJC_AVAILABLE:
        nswindow = _find_nswindow(window_name)
        if nswindow is not None:
            screen_frame = NSScreen.mainScreen().frame()
            nswindow.setFrame_display_animate_(screen_frame, True, True)
    cv2.setWindowProperty(
        window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN,
    )
