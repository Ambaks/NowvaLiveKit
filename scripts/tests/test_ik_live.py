#!/usr/bin/env python3
"""
Live webcam inverse kinematics test script.

Opens webcam and runs MediaPipe pose estimation + Analytical IK.
Overlays joint angle values on the frame in real-time.

This is a manual visual verification tool, NOT a pytest test.

Usage:
    python scripts/test_ik_live.py [camera_id]

Controls:
    q - Quit
    s - Save screenshot
"""

import sys
from pathlib import Path

# Add src/ to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.viz.overlay_2d import draw_skeleton, FPSCounter
from biomechanics.utils.types import JointAngles


def draw_angle_panel(
    frame: np.ndarray,
    angles: JointAngles,
    x_offset: int = 10,
    y_start: int = 30,
) -> np.ndarray:
    """
    Draw a panel showing joint angles on the frame.

    Args:
        frame: BGR image to draw on
        angles: Joint angles to display
        x_offset: X position of panel
        y_start: Y position to start drawing

    Returns:
        Frame with angle panel
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    color = (255, 255, 255)
    bg_color = (40, 40, 40)
    line_height = 20

    y = y_start

    # Draw background panel
    panel_width = 250
    panel_height = 280
    cv2.rectangle(
        frame,
        (x_offset - 5, y_start - 15),
        (x_offset + panel_width, y_start + panel_height),
        bg_color,
        -1
    )

    # Title
    cv2.putText(frame, "Joint Angles (deg)", (x_offset, y), font, 0.6, (0, 255, 255), 1)
    y += line_height + 5

    # Left side angles
    cv2.putText(frame, "LEFT SIDE:", (x_offset, y), font, font_scale, (150, 150, 255), 1)
    y += line_height

    cv2.putText(frame, f"  Hip Flex: {angles.hip_flexion_l:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Knee Flex: {angles.knee_flexion_l:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Ankle Dors: {angles.ankle_dorsiflexion_l:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Hip Add: {angles.hip_adduction_l:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height + 10

    # Right side angles
    cv2.putText(frame, "RIGHT SIDE:", (x_offset, y), font, font_scale, (150, 150, 255), 1)
    y += line_height

    cv2.putText(frame, f"  Hip Flex: {angles.hip_flexion_r:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Knee Flex: {angles.knee_flexion_r:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Ankle Dors: {angles.ankle_dorsiflexion_r:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Hip Add: {angles.hip_adduction_r:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height + 10

    # Trunk angles
    cv2.putText(frame, "TRUNK:", (x_offset, y), font, font_scale, (150, 255, 150), 1)
    y += line_height

    cv2.putText(frame, f"  Flexion: {angles.trunk_flexion:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Lateral: {angles.trunk_lateral_flexion:6.1f}", (x_offset, y), font, font_scale, color, 1)
    y += line_height

    cv2.putText(frame, f"  Pelvis Tilt: {angles.pelvis_tilt:6.1f}", (x_offset, y), font, font_scale, color, 1)

    return frame


def main(camera_id: int = 0):
    """
    Run live IK analysis on webcam feed.

    Args:
        camera_id: OpenCV camera device ID (default 0)
    """
    print("=" * 50)
    print("Live Inverse Kinematics Test")
    print("=" * 50)
    print(f"Camera ID: {camera_id}")
    print("\nControls:")
    print("  q - Quit")
    print("  s - Save screenshot")
    print("=" * 50)

    # Initialize pose estimator
    print("\nInitializing MediaPipe Pose Estimator...")
    pose_estimator = MediaPipePoseEstimator(
        confidence_threshold=0.3,
        model_complexity=1,
    )

    if not pose_estimator.initialize():
        print("ERROR: Failed to initialize pose estimator")
        return 1

    # Initialize IK solver
    print("Initializing Analytical IK Solver...")
    ik_solver = AnalyticalIKSolver()

    print("Initialization complete")

    # Open webcam
    print(f"\nOpening camera {camera_id}...")
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_id}")
        pose_estimator.release()
        return 1

    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened: {width}x{height}")

    # Initialize FPS counter
    fps_counter = FPSCounter(smoothing=0.9)

    screenshot_counter = 0

    print("\nStarting IK analysis loop... Press 'q' to quit")
    print("Try squatting to see hip and knee flexion increase!")

    try:
        while True:
            # Read frame
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to read frame from camera")
                break

            # Run pose estimation (get both 2D and 3D)
            skeleton_2d, skeleton_3d = pose_estimator.estimate_both(frame)

            # Update FPS
            fps = fps_counter.update()

            # Draw skeleton overlay if detected
            if skeleton_2d is not None:
                draw_skeleton(frame, skeleton_2d)

            # Run IK if 3D skeleton available
            angles = None
            if skeleton_3d is not None:
                angles = ik_solver.solve(skeleton_3d)

            # Draw angle panel
            if angles is not None:
                draw_angle_panel(frame, angles, x_offset=width - 260)

            # Draw FPS and status
            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )

            status = "Pose: Detected" if skeleton_3d else "Pose: Not detected"
            status_color = (0, 255, 0) if skeleton_3d else (0, 0, 255)
            cv2.putText(
                frame,
                status,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                status_color,
                2,
            )

            # Draw help text
            cv2.putText(
                frame,
                "[q]uit [s]ave",
                (10, height - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )

            # Show frame
            cv2.imshow("IK Analysis", frame)

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('s'):
                screenshot_path = f"ik_screenshot_{screenshot_counter:03d}.png"
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
        pose_estimator.release()
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
