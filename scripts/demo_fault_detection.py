#!/usr/bin/env python3
"""
Live Fault Detection Demo

Uses webcam + MediaPipe + IK + Fault Detection to provide real-time
squat form feedback.

Usage:
    python scripts/demo_fault_detection.py

Controls:
    'q' - Quit
    'r' - Reset rep counter
    's' - Toggle skeleton display
    'v' - Start/Stop video recording
    'd' - Toggle debug mode (show raw angles)
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2
import time
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.faults import RuleEngine, RepCounter, RepCounterConfig
from biomechanics.utils.types import FaultSeverity
from biomechanics.utils.filters import JointAngleFilter


# Colors (BGR)
COLOR_GREEN = (0, 255, 0)
COLOR_YELLOW = (0, 255, 255)
COLOR_ORANGE = (0, 165, 255)
COLOR_RED = (0, 0, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_BLUE = (255, 100, 100)


def severity_color(severity: FaultSeverity) -> tuple:
    """Get color for fault severity."""
    if severity == FaultSeverity.SEVERE:
        return COLOR_RED
    elif severity == FaultSeverity.MODERATE:
        return COLOR_ORANGE
    elif severity == FaultSeverity.MILD:
        return COLOR_YELLOW
    return COLOR_GREEN


def draw_skeleton(frame, skeleton_2d, color=COLOR_GREEN):
    """Draw 2D skeleton on frame."""
    if skeleton_2d is None:
        return

    # COCO skeleton connections
    connections = [
        (5, 6),   # shoulders
        (5, 7), (7, 9),   # left arm
        (6, 8), (8, 10),  # right arm
        (5, 11), (6, 12), # torso sides
        (11, 12),  # hips
        (11, 13), (13, 15),  # left leg
        (12, 14), (14, 16),  # right leg
    ]

    # Draw connections
    for i, j in connections:
        kp1 = skeleton_2d.keypoints[i]
        kp2 = skeleton_2d.keypoints[j]

        if kp1.confidence > 0.3 and kp2.confidence > 0.3:
            pt1 = (int(kp1.x), int(kp1.y))
            pt2 = (int(kp2.x), int(kp2.y))
            cv2.line(frame, pt1, pt2, color, 2)

    # Draw keypoints
    for kp in skeleton_2d.keypoints:
        if kp.confidence > 0.3:
            cv2.circle(frame, (int(kp.x), int(kp.y)), 5, color, -1)


def draw_info_panel(frame, rep_counter, angles, raw_angles, faults, recent_faults, fps, is_recording, debug_mode, filter_enabled):
    """Draw info panel on frame."""
    h, w = frame.shape[:2]

    # Semi-transparent background for panel
    panel_width = 380
    panel_height = 350 if debug_mode else 300
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (panel_width, panel_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    y = 35
    line_height = 25

    # Title
    cv2.putText(frame, "SQUAT FORM ANALYZER", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_WHITE, 2)
    y += line_height + 10

    # Recording indicator
    if is_recording:
        cv2.circle(frame, (w - 30, 30), 12, COLOR_RED, -1)
        cv2.putText(frame, "REC", (w - 70, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_RED, 2)

    # Rep count
    cv2.putText(frame, f"Reps: {rep_counter.rep_count}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_GREEN, 2)
    y += line_height

    # State with threshold info
    state_color = COLOR_YELLOW if rep_counter.in_rep else COLOR_WHITE
    state_text = "IN REP" if rep_counter.in_rep else "STANDING"
    cv2.putText(frame, f"State: {state_text}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, state_color, 2)
    y += line_height + 5

    # Joint angles
    if angles:
        cv2.putText(frame, "Joint Angles:", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GRAY, 1)
        y += line_height - 5

        hip_avg = (angles.hip_flexion_l + angles.hip_flexion_r) / 2
        knee_avg = angles.avg_knee_flexion
        trunk = angles.trunk_flexion

        # Color code based on threshold
        hip_color = COLOR_YELLOW if hip_avg >= 15 else COLOR_WHITE
        cv2.putText(frame, f"  Hip: {hip_avg:.1f}°  Knee: {knee_avg:.1f}°", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, hip_color, 1)
        y += line_height - 5

        cv2.putText(frame, f"  Trunk: {trunk:.1f}°", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_WHITE, 1)
        y += line_height

        # Debug mode - show more angles
        if debug_mode:
            cv2.putText(frame, f"  Hip L/R: {angles.hip_flexion_l:.1f}/{angles.hip_flexion_r:.1f}", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_BLUE, 1)
            y += line_height - 8
            cv2.putText(frame, f"  Knee L/R: {angles.knee_flexion_l:.1f}/{angles.knee_flexion_r:.1f}", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_BLUE, 1)
            y += line_height - 8
            cv2.putText(frame, f"  Threshold: {rep_counter.config.entry_threshold}° (entry)", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_BLUE, 1)
            y += line_height

    # Current faults
    if faults:
        cv2.putText(frame, "Current Faults:", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_RED, 1)
        y += line_height - 5

        for fault in faults[:3]:  # Show up to 3
            color = severity_color(fault.severity)
            cv2.putText(frame, f"  {fault.fault_type}: {fault.severity.value}", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += line_height - 5

    # Recent faults (last 5 seconds)
    y += 10
    cv2.putText(frame, "Recent Faults:", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GRAY, 1)
    y += line_height - 5

    if recent_faults:
        for fault_type, count in list(recent_faults.items())[:3]:
            cv2.putText(frame, f"  {fault_type}: {count}x", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_YELLOW, 1)
            y += line_height - 5
    else:
        cv2.putText(frame, "  None - Good form!", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN, 1)

    # FPS
    cv2.putText(frame, f"FPS: {fps:.1f}", (w - 100, 60 if is_recording else 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_WHITE, 2)

    # Controls hint
    cv2.putText(frame, "V=Record  R=Reset  D=Debug  Q=Quit", (20, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GRAY, 1)


def draw_fault_alert(frame, fault):
    """Draw large fault alert on screen."""
    h, w = frame.shape[:2]

    color = severity_color(fault.severity)

    # Draw alert box at bottom
    alert_h = 80
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - alert_h - 30), (w, h - 30), color, -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    # Alert text
    cv2.putText(frame, fault.message, (20, h - 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, COLOR_WHITE, 2)
    cv2.putText(frame, f"Severity: {fault.severity.value.upper()}", (20, h - 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_WHITE, 1)


def draw_rep_complete(frame, rep_data):
    """Draw rep completion overlay."""
    h, w = frame.shape[:2]

    # Draw green banner
    banner_h = 100
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h//2 - banner_h//2), (w, h//2 + banner_h//2), COLOR_GREEN, -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    # Rep info
    depth_category = "BELOW PARALLEL" if rep_data.max_depth_angle >= 100 else \
                     "PARALLEL" if rep_data.max_depth_angle >= 90 else \
                     "HALF" if rep_data.max_depth_angle >= 60 else "QUARTER"

    cv2.putText(frame, f"REP {rep_data.rep_number} COMPLETE!",
                (w//2 - 150, h//2 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, COLOR_WHITE, 2)
    cv2.putText(frame, f"Depth: {rep_data.max_depth_angle:.0f}° ({depth_category})",
                (w//2 - 150, h//2 + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_WHITE, 2)


def main():
    print("=" * 50)
    print("  SQUAT FORM ANALYZER - Live Demo")
    print("=" * 50)
    print("\nInitializing...")

    # Initialize components
    pose_estimator = MediaPipePoseEstimator(model_complexity=1)
    ik_solver = AnalyticalIKSolver()
    rule_engine = RuleEngine()

    # Temporal smoothing filter for joint angles
    # One Euro Filter: min_cutoff=1.0 (smooth), beta=0.007 (responsive to fast movements)
    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)

    # Lower thresholds for easier rep detection
    rep_config = RepCounterConfig(
        entry_threshold=15.0,  # Very low - triggers when you start bending
        exit_threshold=12.0,   # Exit when nearly standing
        min_rep_duration_frames=10,  # At least 10 frames (~0.3s at 30fps)
    )
    rep_counter = RepCounter(rep_config)

    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Get actual resolution
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_cap = cap.get(cv2.CAP_PROP_FPS) or 30

    print("\nCamera opened successfully!")
    print(f"Resolution: {frame_width}x{frame_height}")
    print("\nControls:")
    print("  'q' - Quit")
    print("  'r' - Reset rep counter")
    print("  's' - Toggle skeleton display")
    print("  'v' - Start/Stop video recording")
    print("  'd' - Toggle debug mode")
    print("\nStand back so your full body is visible.")
    print("Start squatting to see form analysis!\n")

    # State
    show_skeleton = True
    debug_mode = True  # Start with debug on to see angles
    recent_faults = {}
    fault_decay_time = 5.0
    fault_timestamps = []
    rep_complete_time = 0
    last_rep_data = None
    frame_times = []

    # Video recording
    is_recording = False
    video_writer = None
    output_dir = Path(__file__).parent.parent / "recordings"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_start = time.time()

        # Mirror the frame for natural interaction
        frame = cv2.flip(frame, 1)

        # Get pose estimation (2D and 3D)
        skeleton_2d, skeleton_3d = pose_estimator.estimate_both(frame)

        angles = None
        faults = []
        rep_data = None

        if skeleton_3d is not None:
            # Compute joint angles
            raw_angles = ik_solver.solve(skeleton_3d)

            # Apply temporal smoothing filter (One Euro Filter)
            # This removes noise and jitter for stable rep detection
            angles = angle_filter.filter_angles(raw_angles)

            # Run fault detection
            faults = rule_engine.evaluate(
                angles,
                in_rep=rep_counter.in_rep,
                rep_number=rep_counter.rep_count + 1
            )

            # Update rep counter
            rep_data = rep_counter.update(angles, faults)

            if rep_data is not None:
                last_rep_data = rep_data
                rep_complete_time = time.time()
                print(f"REP {rep_data.rep_number} - Depth: {rep_data.max_depth_angle:.1f}°")

                # Check depth faults at rep completion
                depth_faults = rule_engine.evaluate_rep_complete(
                    rep_data.max_depth_angle, angles, rep_data.rep_number
                )
                faults.extend(depth_faults)

            # Track recent faults
            now = time.time()
            for fault in faults:
                fault_timestamps.append((now, fault.fault_type))
                recent_faults[fault.fault_type] = recent_faults.get(fault.fault_type, 0) + 1

            # Decay old faults
            fault_timestamps = [(t, ft) for t, ft in fault_timestamps if now - t < fault_decay_time]
            recent_faults = {}
            for t, ft in fault_timestamps:
                recent_faults[ft] = recent_faults.get(ft, 0) + 1

        # Draw skeleton
        if show_skeleton and skeleton_2d is not None:
            skel_color = COLOR_RED if faults else (COLOR_YELLOW if rep_counter.in_rep else COLOR_GREEN)
            draw_skeleton(frame, skeleton_2d, skel_color)

        # Calculate FPS
        frame_times.append(time.time() - frame_start)
        if len(frame_times) > 30:
            frame_times.pop(0)
        fps = 1.0 / (sum(frame_times) / len(frame_times)) if frame_times else 0

        # Draw info panel
        draw_info_panel(frame, rep_counter, angles, faults, recent_faults, fps, is_recording, debug_mode)

        # Draw fault alert (most severe)
        if faults:
            worst_fault = max(faults, key=lambda f: f.severity_score)
            if worst_fault.severity in (FaultSeverity.MODERATE, FaultSeverity.SEVERE):
                draw_fault_alert(frame, worst_fault)

        # Draw rep complete overlay (briefly)
        if last_rep_data and time.time() - rep_complete_time < 1.5:
            draw_rep_complete(frame, last_rep_data)

        # Write frame if recording
        if is_recording and video_writer is not None:
            video_writer.write(frame)

        # Show frame
        cv2.imshow("Squat Form Analyzer", frame)

        # Handle keys
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            rep_counter.reset()
            rule_engine.reset()
            angle_filter.reset()
            recent_faults.clear()
            fault_timestamps.clear()
            print("Rep counter reset!")
        elif key == ord('s'):
            show_skeleton = not show_skeleton
        elif key == ord('d'):
            debug_mode = not debug_mode
            print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        elif key == ord('v'):
            if not is_recording:
                # Start recording
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = output_dir / f"squat_session_{timestamp}.mp4"
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                video_writer = cv2.VideoWriter(
                    str(output_path), fourcc, fps_cap, (frame_width, frame_height)
                )
                is_recording = True
                print(f"Recording started: {output_path}")
            else:
                # Stop recording
                if video_writer is not None:
                    video_writer.release()
                    video_writer = None
                is_recording = False
                print("Recording saved!")

    # Cleanup
    if video_writer is not None:
        video_writer.release()
        print("Recording saved!")

    cap.release()
    cv2.destroyAllWindows()
    pose_estimator.release()

    print("\n" + "=" * 50)
    print("  Session Summary")
    print("=" * 50)
    print(f"  Total Reps: {rep_counter.rep_count}")
    if is_recording:
        print(f"  Video saved to: {output_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
