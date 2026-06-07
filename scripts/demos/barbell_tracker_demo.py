#!/usr/bin/env python3
"""
Live barbell tracker demo.

Runs the full detection + Kalman-smoothed tracker + overlay stack on a webcam
feed. Use this after ``scripts/test_barbell_detection.py`` confirms the model
is firing, to visually validate smoothing, path-trail, velocity, and tilt.

Usage:
    python scripts/barbell_tracker_demo.py
    python scripts/barbell_tracker_demo.py --conf 0.3 --imgsz 320

Controls:
    ESC or q - quit
    r        - reset tracker
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import cv2

from biomechanics.barbell_tracking import (
    BarbellDetector,
    BarPathTracker,
    draw_barbell_overlay,
)
from biomechanics.config import BarbellTrackingConfig


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live barbell tracker + overlay demo")
    p.add_argument("--model", default="models/barbell_keypoints.pt")
    p.add_argument("--device", type=int, default=0, help="Camera device id")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--compute-device", default="auto")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = BarbellTrackingConfig()  # default thresholds and color ranges

    detector = BarbellDetector(
        model_path=args.model,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        device=args.compute_device,
    )
    tracker = BarPathTracker(
        bar_length_m=cfg.bar_length_m,
        kalman_q=cfg.kalman_q,
        kalman_r=cfg.kalman_r,
        path_history_len=cfg.path_history_len,
    )

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"Failed to open camera {args.device}", file=sys.stderr)
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    window = "barbell tracker demo"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    frame_index = 0
    fps_window_start = time.time()
    frames_in_window = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed", file=sys.stderr)
                break

            now = time.time()
            detection = detector.detect(frame, timestamp=now, frame_index=frame_index)
            state = tracker.update(detection, timestamp=now)
            draw_barbell_overlay(
                frame, state,
                tilt_warn_deg=cfg.tilt_warn_deg,
                tilt_error_deg=cfg.tilt_error_deg,
            )

            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("r"):
                tracker.reset()

            frame_index += 1
            frames_in_window += 1
            elapsed = now - fps_window_start
            if elapsed >= 1.0:
                fps = frames_in_window / elapsed
                print(f"[{frame_index:05d}] {fps:5.1f} FPS  px/m={state.px_per_meter}")
                fps_window_start = now
                frames_in_window = 0
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
