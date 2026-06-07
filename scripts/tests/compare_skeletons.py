#!/usr/bin/env python3
"""
Side-by-side skeleton comparison: raw vs. filtered.

Overlays two skeletons on the video feed:
  - GREEN : raw MediaPipe 2D landmarks (unfiltered)
  - CYAN  : pre-IK filtered skeleton (confidence blend → velocity clamp
            → bone constraints), projected back to 2D via per-frame
            affine mapping from the raw 3D↔2D correspondence.

Usage:
    python scripts/compare_skeletons.py [camera_id]

Controls:
    r - Start/stop recording (saves annotated MP4)
    q - Quit
    1 - Toggle confidence blending on/off
    2 - Toggle velocity clamping on/off
    3 - Toggle bone constraints on/off
"""

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

import time
import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.pose.base import COCO_SKELETON_CONNECTIONS
from biomechanics.viz.overlay_2d import FPSCounter
from biomechanics.utils.types import Skeleton2D, Skeleton3D
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.config import load_pipeline_config


def project_filtered_to_2d(
    raw_3d: Skeleton3D,
    raw_2d: Skeleton2D,
    filtered_3d: Skeleton3D,
    min_conf: float = 0.3,
):
    """
    Project filtered 3D keypoints to 2D pixel coordinates.

    Uses per-keypoint displacement: computes the 3D offset (filtered - raw),
    scales it to pixel space via signed per-axis scale factors derived from
    the raw 3D↔2D correspondence, and adds it to the raw 2D position.

    This avoids the distortion of a global affine/homography since the filters
    produce small perturbations — we only need to map those deltas correctly.

    Returns:
        Tuple of (points_2d array shape (17,2), confidences list) or None
        if not enough valid keypoints for a reliable mapping.
    """
    raw_3d_pos = raw_3d.to_numpy()[:, :2]      # (17, 2) world X, Y
    raw_2d_pos = np.array([[kp.x, kp.y] for kp in raw_2d.keypoints])  # (17, 2) pixels
    filtered_3d_pos = filtered_3d.to_numpy()[:, :2]  # (17, 2)

    confs = np.array([kp.confidence for kp in raw_2d.keypoints])
    valid = confs > min_conf
    if valid.sum() < 4:
        return None

    # Compute signed per-axis scale (pixels per world-unit) via least-squares
    # on centered coordinates.  Handles axis flipping (3D Y-up → 2D Y-down).
    mean_3d = raw_3d_pos[valid].mean(axis=0)
    mean_2d = raw_2d_pos[valid].mean(axis=0)
    c3 = raw_3d_pos[valid] - mean_3d
    c2 = raw_2d_pos[valid] - mean_2d

    denom_x = np.dot(c3[:, 0], c3[:, 0]) + 1e-8
    denom_y = np.dot(c3[:, 1], c3[:, 1]) + 1e-8
    scale_x = np.dot(c2[:, 0], c3[:, 0]) / denom_x
    scale_y = np.dot(c2[:, 1], c3[:, 1]) / denom_y
    scale = np.array([scale_x, scale_y])

    # Apply scaled displacement to raw 2D positions
    delta_3d = filtered_3d_pos - raw_3d_pos          # (17, 2) in world units
    projected = raw_2d_pos + delta_3d * scale         # broadcast (17,2) * (2,)

    confidences = [kp.confidence for kp in filtered_3d.keypoints]
    return projected, confidences


def draw_skeleton_overlay(
    frame,
    points_2d,
    confidences,
    connections,
    color,
    radius=4,
    thickness=2,
    min_conf=0.1,
):
    """Draw a skeleton given a (17,2) array of 2D points."""
    # Limbs
    for start_idx, end_idx in connections:
        if start_idx < len(points_2d) and end_idx < len(points_2d):
            if confidences[start_idx] > min_conf and confidences[end_idx] > min_conf:
                pt1 = (int(points_2d[start_idx][0]), int(points_2d[start_idx][1]))
                pt2 = (int(points_2d[end_idx][0]), int(points_2d[end_idx][1]))
                cv2.line(frame, pt1, pt2, color, thickness)

    # Keypoints
    for i, (pt, conf) in enumerate(zip(points_2d, confidences)):
        if conf > min_conf:
            cv2.circle(frame, (int(pt[0]), int(pt[1])), radius, color, -1)


def main(camera_id: int = 0):
    print("=" * 55)
    print("  Skeleton Comparison: Raw vs Filtered")
    print("=" * 55)
    print("Controls:")
    print("  r - Start/stop recording")
    print("  1 - Toggle confidence blending")
    print("  2 - Toggle velocity clamping")
    print("  3 - Toggle bone constraints")
    print("  q - Quit")
    print("=" * 55)

    # --- Load config & init components ---
    cfg = load_pipeline_config()

    pose = MediaPipePoseEstimator(
        confidence_threshold=cfg.pose.confidence_threshold,
        model_complexity=cfg.pose.model_complexity,
    )
    if not pose.initialize():
        print("ERROR: Failed to initialize pose estimator")
        return 1

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

    # Recording state
    recording = False
    writer = None
    record_path = None

    print(f"\nCamera: {width}x{height}  |  model_complexity={cfg.pose.model_complexity}")
    print("Starting comparison loop...\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            skeleton_2d, skeleton_3d = pose.estimate_both(frame)
            fps = fps_counter.update()

            if skeleton_2d is not None and skeleton_3d is not None:
                # --- RAW skeleton (green) ---
                raw_pts = np.array([[kp.x, kp.y] for kp in skeleton_2d.keypoints])
                raw_confs = [kp.confidence for kp in skeleton_2d.keypoints]
                draw_skeleton_overlay(
                    frame, raw_pts, raw_confs, COCO_SKELETON_CONNECTIONS,
                    color=(0, 255, 0), radius=5, thickness=2,
                )

                # --- Apply pre-IK filters to 3D skeleton ---
                raw_3d = skeleton_3d  # keep original reference
                s3d = skeleton_3d
                if use_blend:
                    s3d = blender.blend(s3d)
                if use_clamp:
                    s3d = clamper.clamp(s3d)
                if use_bones:
                    s3d = bone_con.enforce(s3d)

                # --- Project filtered 3D → 2D and draw (cyan) ---
                result = project_filtered_to_2d(raw_3d, skeleton_2d, s3d)
                if result is not None:
                    filt_pts, filt_confs = result
                    draw_skeleton_overlay(
                        frame, filt_pts, filt_confs, COCO_SKELETON_CONNECTIONS,
                        color=(255, 255, 0), radius=4, thickness=2,
                    )

            elif skeleton_2d is not None:
                # Only 2D available — draw raw only
                raw_pts = np.array([[kp.x, kp.y] for kp in skeleton_2d.keypoints])
                raw_confs = [kp.confidence for kp in skeleton_2d.keypoints]
                draw_skeleton_overlay(
                    frame, raw_pts, raw_confs, COCO_SKELETON_CONNECTIONS,
                    color=(0, 255, 0), radius=5, thickness=2,
                )
            else:
                cv2.putText(
                    frame, "No pose detected", (10, height - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2,
                )

            # --- Legend ---
            cv2.rectangle(frame, (5, 5), (235, 55), (30, 30, 30), -1)
            cv2.putText(
                frame, "GREEN = Raw MediaPipe", (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1,
            )
            cv2.putText(
                frame, "CYAN  = After Filtering", (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1,
            )

            # --- Bottom status bar ---
            bar_y = height - 35
            cv2.rectangle(frame, (0, bar_y), (width, height), (30, 30, 30), -1)

            toggle = (
                f"[1]Blend:{'ON' if use_blend else 'OFF'}  "
                f"[2]Clamp:{'ON' if use_clamp else 'OFF'}  "
                f"[3]Bones:{'ON' if use_bones else 'OFF'}"
            )
            cv2.putText(
                frame, toggle, (10, height - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1,
            )

            # Bone calibration status
            if use_bones:
                cal = "cal" if bone_con.is_calibrated else f"{bone_con._frame_count}/{cfg.bone_constraints.calibration_frames}"
                cv2.putText(
                    frame, f"Bones({cal})", (400, height - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1,
                )

            # Recording indicator
            if recording:
                cv2.circle(frame, (width - 20, 20), 8, (0, 0, 255), -1)
                cv2.putText(
                    frame, "REC", (width - 58, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2,
                )

            # FPS
            cv2.putText(
                frame, f"FPS: {fps:.0f}", (width - 85, height - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
            )

            # Write frame if recording
            if recording and writer is not None:
                writer.write(frame)

            cv2.imshow("Skeleton Comparison", frame)

            # --- Keyboard controls ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                if not recording:
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    record_path = f"skeleton_compare_{ts}.mp4"
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    writer = cv2.VideoWriter(record_path, fourcc, 30.0, (width, height))
                    recording = True
                    print(f"Recording started → {record_path}")
                else:
                    recording = False
                    if writer:
                        writer.release()
                        writer = None
                    print(f"Recording saved → {record_path}")
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

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        if writer:
            writer.release()
            print(f"Recording saved → {record_path}")
        cap.release()
        cv2.destroyAllWindows()
        pose.release()

    return 0


if __name__ == "__main__":
    camera_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.exit(main(camera_id))
