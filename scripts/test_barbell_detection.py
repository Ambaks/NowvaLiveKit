#!/usr/bin/env python3
"""
Minimal real-time barbell detection test.

Opens the default webcam, runs the trained YOLO11n-pose model on each frame,
and draws the bounding box + horizontal line connecting the two bar keypoints.
Use this to validate the model works end-to-end on your hardware before any
downstream tracker/pipeline work.

Usage:
    python scripts/test_barbell_detection.py
    python scripts/test_barbell_detection.py --device 1
    python scripts/test_barbell_detection.py --model models/barbell_keypoints.pt --conf 0.3

Controls:
    ESC or q - quit
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running the script directly from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2

from biomechanics.barbell_tracking.detector import BarbellDetector
from biomechanics.barbell_tracking.overlay import draw_detection_only


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time barbell detection smoke test")
    p.add_argument("--model", default="models/barbell_keypoints.pt",
                   help="Path to YOLO11n-pose checkpoint")
    p.add_argument("--device", type=int, default=0, help="Camera device id")
    p.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    p.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    p.add_argument("--compute-device", default="auto",
                   help="Torch device: auto | cpu | cuda | mps")
    p.add_argument("--width", type=int, default=1280, help="Requested camera width")
    p.add_argument("--height", type=int, default=720, help="Requested camera height")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    detector = BarbellDetector(
        model_path=args.model,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        device=args.compute_device,
    )

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"Failed to open camera {args.device}", file=sys.stderr)
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    window = "barbell detection test"
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
            draw_detection_only(frame, detection)

            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):  # ESC or q
                break

            frame_index += 1
            frames_in_window += 1
            elapsed = now - fps_window_start
            if elapsed >= 1.0:
                fps = frames_in_window / elapsed
                print(f"[{frame_index:05d}] {fps:5.1f} FPS")
                fps_window_start = now
                frames_in_window = 0
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
