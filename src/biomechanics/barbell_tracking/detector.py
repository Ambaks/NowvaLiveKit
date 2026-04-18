"""
Barbell YOLO detector.

Wraps a YOLO11n-pose model trained to emit:
- one bounding box around the barbell
- two keypoints: left end (idx 0) and right end (idx 1) of the bar

The checkpoint lives at `models/barbell_keypoints.pt` by default.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np

from biomechanics.utils.types import BarbellDetection, Keypoint2D

log = logging.getLogger(__name__)


def _resolve_device(device: str) -> str:
    """Translate 'auto' into the best available torch device."""
    if device != "auto":
        return device

    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class BarbellDetector:
    """
    Per-frame barbell keypoint detector.

    Example:
        det = BarbellDetector("models/barbell_keypoints.pt")
        detection = det.detect(bgr_frame, timestamp=t, frame_index=i)
        if detection is not None:
            print(detection.tilt_degrees, detection.center)
    """

    def __init__(
        self,
        model_path: Union[str, Path] = "models/barbell_keypoints.pt",
        conf_threshold: float = 0.25,
        imgsz: int = 640,
        device: str = "auto",
    ):
        self.model_path = Path(model_path)
        self.conf_threshold = float(conf_threshold)
        self.imgsz = int(imgsz)
        self.device = _resolve_device(device)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Barbell model not found at {self.model_path}. "
                f"Expected a YOLO11n-pose checkpoint."
            )

        # Lazy import so the rest of the biomechanics package doesn't require
        # ultralytics until a detector is actually instantiated.
        from ultralytics import YOLO

        log.info("Loading barbell YOLO model from %s on device=%s", self.model_path, self.device)
        self._model = YOLO(str(self.model_path))
        try:
            self._model.to(self.device)
        except Exception as e:
            # Non-fatal: some devices (e.g. mps) can be picky with certain ops; fall back to CPU.
            log.warning("Failed to move YOLO model to %s (%s); falling back to cpu", self.device, e)
            self.device = "cpu"
            self._model.to("cpu")

    def detect(
        self,
        frame: np.ndarray,
        timestamp: float = 0.0,
        frame_index: int = 0,
    ) -> Optional[BarbellDetection]:
        """
        Run inference on a single BGR frame.

        Returns None when no barbell is detected above ``conf_threshold``.
        Otherwise returns the highest-confidence detection as a BarbellDetection.
        """
        results = self._model(
            frame,
            conf=self.conf_threshold,
            imgsz=self.imgsz,
            verbose=False,
        )
        if not results:
            return None

        r = results[0]
        if r.keypoints is None or r.boxes is None or len(r.boxes) == 0:
            return None

        box_conf = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, "cpu") else np.asarray(r.boxes.conf)
        if box_conf.size == 0:
            return None

        best = int(np.argmax(box_conf))

        # Extract the two keypoints (shape: (N, K, 2) or (N, K, 3))
        kxy = r.keypoints.xy[best]
        kxy = kxy.cpu().numpy() if hasattr(kxy, "cpu") else np.asarray(kxy)
        if kxy.shape[0] < 2:
            return None

        # Per-keypoint confidence if the model exposes it; fall back to box conf.
        if getattr(r.keypoints, "conf", None) is not None:
            kconf = r.keypoints.conf[best]
            kconf = kconf.cpu().numpy() if hasattr(kconf, "cpu") else np.asarray(kconf)
        else:
            kconf = np.array([float(box_conf[best]), float(box_conf[best])])

        # Normalize left/right by x so the "left" keypoint is the one lower on the x-axis
        # (the trained model may emit them in any order).
        p0 = (float(kxy[0, 0]), float(kxy[0, 1]), float(kconf[0]))
        p1 = (float(kxy[1, 0]), float(kxy[1, 1]), float(kconf[1]))
        if p0[0] <= p1[0]:
            left_tuple, right_tuple = p0, p1
        else:
            left_tuple, right_tuple = p1, p0

        left = Keypoint2D(x=left_tuple[0], y=left_tuple[1], confidence=left_tuple[2])
        right = Keypoint2D(x=right_tuple[0], y=right_tuple[1], confidence=right_tuple[2])

        xyxy = r.boxes.xyxy[best]
        xyxy = xyxy.cpu().numpy() if hasattr(xyxy, "cpu") else np.asarray(xyxy)
        bbox = (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3]))

        return BarbellDetection(
            left_end=left,
            right_end=right,
            bbox_conf=float(box_conf[best]),
            bbox_xyxy=bbox,
            timestamp=timestamp,
            frame_index=frame_index,
        )
