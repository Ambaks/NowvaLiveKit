#!/usr/bin/env python3
"""
Live webcam pose estimation test script.

Opens webcam and runs MediaPipe pose estimation with skeleton overlay.
This is a manual visual verification tool, NOT a pytest test.

Usage:
    python scripts/test_pose_live.py [camera_id]

Controls:
    q - Quit
    l - Toggle keypoint labels
    c - Toggle confidence display
    s - Save screenshot
"""

import sys
import os
from pathlib import Path

# Add src/ to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.viz.overlay_2d import (
    draw_skeleton,
    draw_fps,
    draw_keypoint_labels,
    FPSCounter,
)


def main(camera_id: int = 0):
    """
    Run live pose estimation on webcam feed.

    Args:
        camera_id: OpenCV camera device ID (default 0)
    """
    print("=" * 50)
    print("Live Pose Estimation Test")
    print("=" * 50)
    print(f"Camera ID: {camera_id}")
    print("\nControls:")
    print("  q - Quit")
    print("  l - Toggle keypoint labels")
    print("  c - Toggle confidence display")
    print("  s - Save screenshot")
    print("=" * 50)

    # Initialize pose estimator
    print("\nInitializing MediaPipe Pose Estimator...")
    estimator = MediaPipePoseEstimator(
        confidence_threshold=0.3,
        model_complexity=1,
    )

    if not estimator.initialize():
        print("ERROR: Failed to initialize pose estimator")
        return 1

    print("Pose estimator initialized successfully")

    # Open webcam
    print(f"\nOpening camera {camera_id}...")
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_id}")
        estimator.release()
        return 1

    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened: {width}x{height}")

    # Initialize FPS counter
    fps_counter = FPSCounter(smoothing=0.9)

    # Display options
    show_labels = False
    show_confidence = False
    screenshot_counter = 0

    print("\nStarting pose estimation loop... Press 'q' to quit")

    try:
        while True:
            # Read frame
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to read frame from camera")
                break

            # Run pose estimation
            skeleton = estimator.estimate(frame)

            # Update FPS
            fps = fps_counter.update()

            # Draw skeleton overlay
            if skeleton is not None:
                draw_skeleton(
                    frame,
                    skeleton,
                    draw_confidence=show_confidence,
                )

                if show_labels:
                    draw_keypoint_labels(frame, skeleton)

            # Draw FPS
            draw_fps(frame, fps)

            # Draw status text
            status = f"Pose: {'Detected' if skeleton else 'Not detected'}"
            cv2.putText(
                frame,
                status,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0) if skeleton else (0, 0, 255),
                2,
            )

            # Draw help text
            help_text = "[q]uit [l]abels [c]onf [s]ave"
            cv2.putText(
                frame,
                help_text,
                (10, height - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )

            # Show frame
            cv2.imshow("Pose Estimation", frame)

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('l'):
                show_labels = not show_labels
                print(f"Labels: {'ON' if show_labels else 'OFF'}")
            elif key == ord('c'):
                show_confidence = not show_confidence
                print(f"Confidence: {'ON' if show_confidence else 'OFF'}")
            elif key == ord('s'):
                screenshot_path = f"pose_screenshot_{screenshot_counter:03d}.png"
                cv2.imwrite(screenshot_path, frame)
                print(f"Saved screenshot: {screenshot_path}")
                screenshot_counter += 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    finally:
        # Cleanup
        print("\nCleaning up...")
        cap.release()
        cv2.destroyAllWindows()
        estimator.release()
        print("Done")

    return 0


if __name__ == "__main__":
    # Parse camera ID from command line
    camera_id = 0
    if len(sys.argv) > 1:
        try:
            camera_id = int(sys.argv[1])
        except ValueError:
            print(f"Invalid camera ID: {sys.argv[1]}")
            sys.exit(1)

    sys.exit(main(camera_id))
