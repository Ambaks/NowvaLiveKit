#!/usr/bin/env python3
"""
Live webcam BiLSTM rep counting test (5-class depth classification).

Opens webcam, runs MediaPipe pose → BiLSTM inference, and overlays
rep count + depth class probabilities on the video feed in real-time.

Usage:
    python scripts/test_bilstm_live.py [--camera CAMERA_ID] [--min-depth CLASS]

Controls:
    q - Quit
    r - Reset rep counter
    s - Save screenshot
"""

import argparse
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

import cv2
import numpy as np

from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.ml.inference import BiLSTMInference
from biomechanics.ml.bilstm_counter import BiLSTMCounterConfig
from biomechanics.utils.types import DEPTH_CLASS_NAMES
from biomechanics.viz.overlay_2d import draw_skeleton, FPSCounter


MODEL_PATH = str(Path(__file__).parent.parent / "models" / "bilstm_rep_counter.pt")

# Color for each depth class (BGR)
CLASS_COLORS = {
    0: (0, 255, 0),      # Standing  - green
    1: (0, 255, 255),     # Quarter   - yellow
    2: (0, 165, 255),     # Half      - orange
    3: (0, 140, 255),     # Parallel  - dark orange
    4: (0, 0, 255),       # Deep      - red
}


def draw_bilstm_panel(
    frame: np.ndarray,
    rep_count: int,
    depth_class: int,
    class_probs: np.ndarray,
    in_rep: bool,
    buffer_ready: bool,
    min_depth_class: int,
    max_depth_in_rep: int = 0,
    x_offset: int = 10,
    y_start: int = 100,
) -> np.ndarray:
    font = cv2.FONT_HERSHEY_SIMPLEX
    bg_color = (40, 40, 40)
    panel_w = 310
    panel_h = 280

    cv2.rectangle(
        frame,
        (x_offset - 5, y_start - 15),
        (x_offset + panel_w, y_start + panel_h),
        bg_color, -1,
    )

    y = y_start

    # Title
    cv2.putText(frame, "BiLSTM Rep Counter (5-class)", (x_offset, y), font, 0.55, (0, 255, 255), 1)
    y += 28

    # Rep count (large)
    cv2.putText(frame, f"Reps: {rep_count}", (x_offset, y), font, 1.0, (255, 255, 255), 2)
    y += 32

    # State + current depth class
    state_text = "DOWN" if in_rep else "UP"
    state_color = (0, 140, 255) if in_rep else (0, 255, 0)
    cv2.putText(frame, f"State: {state_text}", (x_offset, y), font, 0.6, state_color, 2)
    y += 28

    if buffer_ready:
        depth_name = DEPTH_CLASS_NAMES.get(depth_class, "?")
        depth_color = CLASS_COLORS.get(depth_class, (200, 200, 200))
        cv2.putText(frame, f"Depth: {depth_name}", (x_offset, y), font, 0.6, depth_color, 2)
        y += 25

        # Max depth in current rep
        if in_rep:
            max_name = DEPTH_CLASS_NAMES.get(max_depth_in_rep, "?")
            max_color = CLASS_COLORS.get(max_depth_in_rep, (200, 200, 200))
            cv2.putText(frame, f"Max: {max_name}", (x_offset + 160, y - 25), font, 0.5, max_color, 1)

        # Min depth threshold indicator
        min_name = DEPTH_CLASS_NAMES.get(min_depth_class, "?")
        cv2.putText(frame, f"Min depth: {min_name}", (x_offset, y), font, 0.45, (150, 150, 150), 1)
        y += 22

        # Per-class probability bars
        bar_x = x_offset
        bar_w = 200
        bar_h = 16

        for cls_idx in range(len(class_probs)):
            cls_name = DEPTH_CLASS_NAMES.get(cls_idx, f"C{cls_idx}")
            prob = class_probs[cls_idx]
            color = CLASS_COLORS.get(cls_idx, (200, 200, 200))

            # Dim color for classes below threshold
            if cls_idx < min_depth_class and cls_idx != 0:
                color = tuple(c // 3 for c in color)

            # Label
            label = f"{cls_name:>9s} {prob:.2f}"
            cv2.putText(frame, label, (bar_x, y + bar_h - 3), font, 0.4, (200, 200, 200), 1)

            # Bar background
            bx = bar_x + 120
            cv2.rectangle(frame, (bx, y), (bx + bar_w, y + bar_h), (60, 60, 60), -1)

            # Bar fill
            fill_w = int(bar_w * prob)
            if fill_w > 0:
                cv2.rectangle(frame, (bx, y), (bx + fill_w, y + bar_h), color, -1)

            # Highlight current predicted class
            if cls_idx == depth_class:
                cv2.rectangle(frame, (bx, y), (bx + bar_w, y + bar_h), (255, 255, 255), 1)

            y += bar_h + 4
    else:
        cv2.putText(frame, "Warming up...", (x_offset, y), font, 0.5, (100, 100, 255), 1)

    return frame


def parse_args():
    parser = argparse.ArgumentParser(description="Live BiLSTM Rep Counter (5-class)")
    parser.add_argument("--camera", type=int, default=0, help="Camera device ID")
    parser.add_argument(
        "--min-depth", type=int, default=3, choices=range(1, 5),
        help="Minimum depth class to count as rep (1=Quarter, 2=Half, 3=Parallel, 4=Deep)",
    )
    parser.add_argument("--model", type=str, default=MODEL_PATH, help="Path to model checkpoint")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 50)
    print("Live BiLSTM Rep Counter (5-class)")
    print("=" * 50)
    print(f"Camera ID: {args.camera}")
    print(f"Model: {args.model}")
    print(f"Min depth class: {args.min_depth} ({DEPTH_CLASS_NAMES.get(args.min_depth, '?')})")
    print("\nControls:")
    print("  q - Quit")
    print("  r - Reset rep counter")
    print("  s - Save screenshot")
    print("=" * 50)

    if not Path(args.model).exists():
        print(f"\nERROR: Model not found at {args.model}")
        print("Run training first:")
        print("  python scripts/generate_opensim_data.py --num-sessions 300 --output data/dataset_5class.npz")
        print("  python scripts/train_bilstm.py --data data/dataset_5class.npz --epochs 80")
        return 1

    # Initialize pose estimator
    print("\nInitializing MediaPipe Pose Estimator...")
    pose_estimator = MediaPipePoseEstimator(
        confidence_threshold=0.3,
        model_complexity=1,
    )

    if not pose_estimator.initialize():
        print("ERROR: Failed to initialize pose estimator")
        return 1

    # Initialize BiLSTM inference with 5-class config
    print("Loading BiLSTM model...")
    bilstm_config = BiLSTMCounterConfig(
        min_depth_class=args.min_depth,
        min_rep_frames=12,
        ema_alpha=0.2,
        num_classes=5,
    )
    bilstm = BiLSTMInference(
        model_path=args.model,
        device="cpu",
        config=bilstm_config,
    )
    print("BiLSTM model loaded")

    # Open webcam
    print(f"\nOpening camera {args.camera}...")
    cap = cv2.VideoCapture(args.camera)

    if not cap.isOpened():
        print(f"ERROR: Could not open camera {args.camera}")
        pose_estimator.release()
        return 1

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened: {width}x{height}")

    fps_counter = FPSCounter(smoothing=0.9)
    screenshot_counter = 0
    frame_index = 0

    print("\nStarting BiLSTM rep counting... Press 'q' to quit")
    print(f"Only counting reps that reach {DEPTH_CLASS_NAMES.get(args.min_depth, '?')} depth or deeper")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to read frame")
                break

            # Run pose estimation
            skeleton_2d, skeleton_3d = pose_estimator.estimate_both(frame)
            fps = fps_counter.update()

            # Draw skeleton
            if skeleton_2d is not None:
                draw_skeleton(frame, skeleton_2d)

            # Run BiLSTM inference
            rep_data = None
            if skeleton_3d is not None:
                skeleton_3d.frame_index = frame_index
                skeleton_3d.timestamp = frame_index / 30.0
                rep_data = bilstm.process_skeleton(skeleton_3d)

                if rep_data is not None:
                    depth_name = DEPTH_CLASS_NAMES.get(rep_data.max_depth_class, "?")
                    print(f"  REP {bilstm.rep_count} completed! (max depth: {depth_name})")

            # Draw BiLSTM panel
            draw_bilstm_panel(
                frame,
                rep_count=bilstm.rep_count,
                depth_class=bilstm.current_depth_class,
                class_probs=bilstm.current_class_probabilities,
                in_rep=bilstm.in_rep,
                buffer_ready=bilstm._buffer.is_ready,
                min_depth_class=args.min_depth,
                max_depth_in_rep=bilstm._counter._max_depth_seen,
            )

            # Draw FPS
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # Pose status
            status = "Pose: Detected" if skeleton_3d else "Pose: Not detected"
            status_color = (0, 255, 0) if skeleton_3d else (0, 0, 255)
            cv2.putText(frame, status, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

            # Help text
            cv2.putText(frame, "[q]uit [r]eset [s]ave", (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("BiLSTM Rep Counter (5-class)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('r'):
                bilstm.reset()
                print("Counter reset!")
            elif key == ord('s'):
                path = f"bilstm_screenshot_{screenshot_counter:03d}.png"
                cv2.imwrite(path, frame)
                print(f"Saved: {path}")
                screenshot_counter += 1

            frame_index += 1

    except KeyboardInterrupt:
        print("\nInterrupted")

    finally:
        print(f"\nFinal rep count: {bilstm.rep_count}")
        cap.release()
        cv2.destroyAllWindows()
        pose_estimator.release()
        print("Done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
