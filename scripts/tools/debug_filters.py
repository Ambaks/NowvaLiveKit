#!/usr/bin/env python3
"""
Debug visualization for pre-IK filter layers.

Runs the pipeline manually step-by-step, showing the effect of each
filter on knee/hip angles. Helps diagnose which filter is causing
rep detection issues.

Displays:
  - Left panel:  per-keypoint confidence values (color-coded)
  - Center:      video feed with skeleton overlay
  - Right panel: knee/hip angles at each pipeline stage
  - Bottom bar:  rep counter state + phase

Usage:
    python scripts/debug_filters.py [camera_id]

Controls:
    q - Quit
    1 - Toggle confidence blending on/off
    2 - Toggle velocity clamping on/off
    3 - Toggle bone constraints on/off
    r - Reset all filters
"""

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

import time
import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.viz.overlay_2d import draw_skeleton, FPSCounter
from biomechanics.utils.types import CocoKeypoints as CK
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.faults import RuleEngine, RepCounter, RepCounterConfig
from biomechanics.config import load_pipeline_config


# Keypoints to show confidence for (the ones that matter for squats)
CONF_KEYPOINTS = [
    (CK.LEFT_HIP, "L Hip"),
    (CK.RIGHT_HIP, "R Hip"),
    (CK.LEFT_KNEE, "L Knee"),
    (CK.RIGHT_KNEE, "R Knee"),
    (CK.LEFT_ANKLE, "L Ankle"),
    (CK.RIGHT_ANKLE, "R Ankle"),
    (CK.LEFT_SHOULDER, "L Shoulder"),
    (CK.RIGHT_SHOULDER, "R Shoulder"),
]


def conf_color(c: float):
    """Map confidence 0-1 to BGR color: red(0) -> yellow(0.5) -> green(1)."""
    if c < 0.5:
        return (0, int(255 * c * 2), 255)  # red -> yellow
    else:
        return (0, 255, int(255 * (1 - c) * 2))  # yellow -> green


def draw_debug_panel(frame, y_start, label, knee_l, knee_r, hip_l, hip_r, color):
    """Draw a row of angle values for one pipeline stage."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    x = frame.shape[1] - 390
    y = y_start

    cv2.putText(frame, label, (x, y), font, 0.45, color, 1)
    cv2.putText(frame, f"KnL:{knee_l:5.1f}", (x + 120, y), font, 0.45, (255, 255, 255), 1)
    cv2.putText(frame, f"KnR:{knee_r:5.1f}", (x + 210, y), font, 0.45, (255, 255, 255), 1)
    cv2.putText(frame, f"HiL:{hip_l:5.1f}", (x + 300, y), font, 0.45, (200, 200, 200), 1)


def main(camera_id: int = 0):
    print("=" * 55)
    print("  Filter Debug Visualizer")
    print("=" * 55)
    print("Controls:")
    print("  1 - Toggle confidence blending")
    print("  2 - Toggle velocity clamping")
    print("  3 - Toggle bone constraints")
    print("  r - Reset all filters")
    print("  q - Quit")
    print("=" * 55)

    # --- Load config and initialize components ---
    cfg = load_pipeline_config()
    print(f"Pose model: complexity={cfg.pose.model_complexity} (0=lite, 1=full, 2=heavy)")

    pose = MediaPipePoseEstimator(
        confidence_threshold=cfg.pose.confidence_threshold,
        model_complexity=cfg.pose.model_complexity,
    )
    if not pose.initialize():
        print("ERROR: Failed to initialize pose estimator")
        return 1

    ik = AnalyticalIKSolver()
    angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)
    deriv_tracker = DerivativeTracker(smoothing_alpha=0.3)

    blender = ConfidenceBlender(
        min_confidence=cfg.confidence_blend.min_confidence,
        max_confidence=cfg.confidence_blend.max_confidence,
    )
    clamper = VelocityClamp(
        max_velocity_m_per_s=cfg.velocity_clamp.max_velocity_m_per_s,
        target_fps=cfg.pipeline.target_fps,
    )
    bone_con = BoneLengthConstraints(
        calibration_frames=cfg.bone_constraints.calibration_frames,
        tolerance=cfg.bone_constraints.tolerance,
    )

    rep_counter = RepCounter(RepCounterConfig(
        entry_knee_angle=cfg.rep_detection.entry_threshold,
        min_rep_duration_frames=cfg.rep_detection.min_rep_duration_frames,
    ))

    # Toggle flags
    use_blend = True
    use_clamp = True
    use_bones = True

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_id}")
        pose.release()
        return 1

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_counter = FPSCounter(smoothing=0.9)

    print(f"\nCamera opened: {width}x{height}")
    print("Starting debug loop...\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            skeleton_2d, skeleton_3d = pose.estimate_both(frame)
            fps = fps_counter.update()

            if skeleton_2d is not None:
                draw_skeleton(frame, skeleton_2d)

            if skeleton_3d is not None:
                # --- Stage 0: Raw angles (no pre-IK filters) ---
                raw_angles_no_filter = ik.solve(skeleton_3d)

                # --- Capture per-keypoint confidences ---
                confidences = [kp.confidence for kp in skeleton_3d.keypoints]

                # --- Stage 1: Confidence blending ---
                s3d = skeleton_3d
                if use_blend:
                    s3d = blender.blend(s3d)
                angles_after_blend = ik.solve(s3d)

                # --- Stage 2: Velocity clamping ---
                if use_clamp:
                    s3d = clamper.clamp(s3d)
                angles_after_clamp = ik.solve(s3d)

                # --- Stage 3: Bone constraints ---
                if use_bones:
                    s3d = bone_con.enforce(s3d)
                angles_after_bones = ik.solve(s3d)

                # --- Stage 4: One Euro filter (final angles used by rep counter) ---
                final_angles = angle_filter.filter_angles(angles_after_bones)
                derivatives = deriv_tracker.update(final_angles)

                # --- Rep counter ---
                rep_data, feedback = rep_counter.update(final_angles, derivatives, [])
                angle_filter.update_phase(rep_counter.phase)

                # ============ DRAW DEBUG INFO ============

                # --- Right panel: angles at each stage ---
                panel_x = width - 395
                cv2.rectangle(frame, (panel_x - 5, 5), (width - 5, 150), (30, 30, 30), -1)

                y = 22
                font = cv2.FONT_HERSHEY_SIMPLEX
                cv2.putText(frame, "STAGE", (panel_x, y), font, 0.4, (150, 150, 150), 1)
                cv2.putText(frame, "Knee L   Knee R   Hip L", (panel_x + 120, y), font, 0.4, (150, 150, 150), 1)
                y += 20

                a = raw_angles_no_filter
                draw_debug_panel(frame, y, "Raw (no filt)", a.knee_flexion_l, a.knee_flexion_r, a.hip_flexion_l, a.hip_flexion_r, (100, 100, 255))
                y += 18

                a = angles_after_blend
                lbl = "Blend" if use_blend else "Blend (OFF)"
                c = (0, 255, 255) if use_blend else (100, 100, 100)
                draw_debug_panel(frame, y, lbl, a.knee_flexion_l, a.knee_flexion_r, a.hip_flexion_l, a.hip_flexion_r, c)
                y += 18

                a = angles_after_clamp
                lbl = "Clamp" if use_clamp else "Clamp (OFF)"
                c = (0, 200, 200) if use_clamp else (100, 100, 100)
                draw_debug_panel(frame, y, lbl, a.knee_flexion_l, a.knee_flexion_r, a.hip_flexion_l, a.hip_flexion_r, c)
                y += 18

                a = angles_after_bones
                lbl = "Bones" if use_bones else "Bones (OFF)"
                c = (0, 180, 180) if use_bones else (100, 100, 100)
                cal_status = " (cal)" if bone_con.is_calibrated else f" ({bone_con._frame_count}/30)"
                draw_debug_panel(frame, y, lbl + cal_status, a.knee_flexion_l, a.knee_flexion_r, a.hip_flexion_l, a.hip_flexion_r, c)
                y += 18

                a = final_angles
                draw_debug_panel(frame, y, "Final (1Euro)", a.knee_flexion_l, a.knee_flexion_r, a.hip_flexion_l, a.hip_flexion_r, (0, 255, 0))

                # --- Left panel: confidence values ---
                cv2.rectangle(frame, (5, 5), (175, 25 + len(CONF_KEYPOINTS) * 18), (30, 30, 30), -1)
                cy = 22
                cv2.putText(frame, "Keypoint Confidence", (10, cy), font, 0.4, (150, 150, 150), 1)
                cy += 18
                for kp_idx, kp_name in CONF_KEYPOINTS:
                    c = confidences[kp_idx]
                    color = conf_color(c)
                    cv2.putText(frame, f"{kp_name}: {c:.2f}", (10, cy), font, 0.42, color, 1)
                    # Confidence bar
                    bar_x = 120
                    cv2.rectangle(frame, (bar_x, cy - 8), (bar_x + int(50 * c), cy), color, -1)
                    cv2.rectangle(frame, (bar_x, cy - 8), (bar_x + 50, cy), (80, 80, 80), 1)
                    cy += 18

                # --- Bottom bar: rep counter state ---
                bar_y = height - 40
                cv2.rectangle(frame, (0, bar_y), (width, height), (30, 30, 30), -1)

                phase = rep_counter.phase
                reps = rep_counter.rep_count
                in_rep = rep_counter.in_rep
                knee_avg = final_angles.avg_knee_flexion

                phase_color = {
                    "idle": (200, 200, 200),
                    "descending": (0, 150, 255),
                    "bottom": (0, 0, 255),
                    "ascending": (0, 255, 150),
                }.get(phase, (200, 200, 200))

                cv2.putText(frame, f"Phase: {phase.upper()}", (10, height - 15), font, 0.55, phase_color, 2)
                cv2.putText(frame, f"Reps: {reps}", (200, height - 15), font, 0.55, (255, 255, 255), 2)
                cv2.putText(frame, f"Knee: {knee_avg:.1f} deg", (320, height - 15), font, 0.55, (255, 255, 255), 1)

                threshold_text = f"Entry: 30.0 deg"
                thresh_color = (0, 255, 0) if knee_avg >= 30.0 else (0, 0, 255)
                cv2.putText(frame, threshold_text, (480, height - 15), font, 0.45, thresh_color, 1)

                toggle_text = f"[1]Blend:{'ON' if use_blend else 'OFF'}  [2]Clamp:{'ON' if use_clamp else 'OFF'}  [3]Bones:{'ON' if use_bones else 'OFF'}"
                cv2.putText(frame, toggle_text, (620, height - 15), font, 0.4, (180, 180, 180), 1)

            else:
                cv2.putText(frame, "No pose detected", (10, height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # FPS
            cv2.putText(frame, f"FPS: {fps:.0f}", (width - 80, height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            cv2.imshow("Filter Debug", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('1'):
                use_blend = not use_blend
                if not use_blend:
                    blender.reset()
                print(f"Confidence blending: {'ON' if use_blend else 'OFF'}")
            elif key == ord('2'):
                use_clamp = not use_clamp
                if not use_clamp:
                    clamper.reset()
                print(f"Velocity clamping: {'ON' if use_clamp else 'OFF'}")
            elif key == ord('3'):
                use_bones = not use_bones
                if not use_bones:
                    bone_con.reset()
                print(f"Bone constraints: {'ON' if use_bones else 'OFF'}")
            elif key == ord('r'):
                blender.reset()
                clamper.reset()
                bone_con.reset()
                angle_filter.reset()
                deriv_tracker.reset()
                print("All filters reset")

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        pose.release()

    return 0


if __name__ == "__main__":
    camera_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.exit(main(camera_id))
