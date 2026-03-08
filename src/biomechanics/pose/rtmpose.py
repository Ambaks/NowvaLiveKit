"""
RTMPose pose estimation backend using ONNX Runtime.

Uses RTMPose-m (256x192) with SimCC decoding for 2D COCO 17 keypoints.
This is a pure 2D estimator — 3D reconstruction comes from the
triangulation layer when stereo cameras are available.

Requires:
    pip install onnxruntime
    python scripts/download_models.py
"""

import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    import onnxruntime as ort

    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False

from biomechanics.pose.base import PoseEstimator
from biomechanics.utils.types import Keypoint2D, Skeleton2D, Skeleton3D

logger = logging.getLogger(__name__)

# Default model location
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"
DEFAULT_MODEL_NAME = "rtmpose-m-256x192.onnx"

# ImageNet normalization constants
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# SimCC split ratio (standard for RTMPose)
SIMCC_SPLIT_RATIO = 2.0


class RTMPoseEstimator(PoseEstimator):
    """
    RTMPose-based pose estimator using ONNX Runtime.

    Produces COCO 17 keypoints in 2D pixel coordinates via SimCC decoding.
    Uses CoreMLExecutionProvider for Apple Silicon acceleration with
    CPUExecutionProvider as fallback.

    This is a 2D-only estimator. estimate_3d() returns None.
    For 3D reconstruction, use the triangulation layer with stereo cameras.
    """

    # Input resolution for RTMPose-m
    INPUT_WIDTH = 192
    INPUT_HEIGHT = 256

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        model_path: Optional[str] = None,
    ):
        """
        Initialize RTMPose estimator.

        Args:
            confidence_threshold: Minimum confidence to consider keypoint valid
            model_path: Path to ONNX model file. If None, uses default location.
        """
        super().__init__(confidence_threshold)

        if not ONNXRUNTIME_AVAILABLE:
            raise ImportError(
                "onnxruntime is not installed. Run: pip install onnxruntime"
            )

        if model_path is not None:
            self._model_path = Path(model_path)
        else:
            self._model_path = DEFAULT_MODEL_DIR / DEFAULT_MODEL_NAME

        self._session: Optional["ort.InferenceSession"] = None
        self._input_name: Optional[str] = None
        self._frame_index = 0

    def initialize(self) -> bool:
        """Load ONNX model and create inference session."""
        if self._initialized:
            return True

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"RTMPose model not found at {self._model_path}. "
                f"Run: python scripts/download_models.py"
            )

        # Select execution providers: prefer CoreML on Apple Silicon
        providers = []
        available = ort.get_available_providers()

        if "CoreMLExecutionProvider" in available:
            providers.append("CoreMLExecutionProvider")
        providers.append("CPUExecutionProvider")

        logger.info("Loading RTMPose from %s", self._model_path)
        logger.info("ONNX Runtime providers: %s", providers)

        self._session = ort.InferenceSession(
            str(self._model_path),
            providers=providers,
        )

        # Cache input name
        self._input_name = self._session.get_inputs()[0].name

        # Verify expected output count
        outputs = self._session.get_outputs()
        if len(outputs) < 2:
            raise RuntimeError(
                f"Expected at least 2 outputs (simcc_x, simcc_y), got {len(outputs)}"
            )

        active_providers = self._session.get_providers()
        logger.info("Active ONNX Runtime providers: %s", active_providers)

        self._initialized = True
        return True

    def release(self) -> None:
        """Release ONNX session."""
        self._session = None
        self._input_name = None
        self._initialized = False

    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """
        Preprocess frame for RTMPose inference.

        Args:
            frame: BGR image (H, W, 3)

        Returns:
            Tuple of (input_tensor [1,3,256,192], scale_x, scale_y)
        """
        orig_h, orig_w = frame.shape[:2]

        # BGR -> RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize to model input size
        resized = cv2.resize(rgb, (self.INPUT_WIDTH, self.INPUT_HEIGHT))

        # Normalize: float32, /255, ImageNet mean/std
        blob = resized.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD

        # HWC -> CHW -> NCHW
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0).astype(np.float32)

        scale_x = orig_w / self.INPUT_WIDTH
        scale_y = orig_h / self.INPUT_HEIGHT

        return blob, scale_x, scale_y

    def _decode_simcc(
        self,
        x_logits: np.ndarray,
        y_logits: np.ndarray,
        scale_x: float,
        scale_y: float,
    ) -> np.ndarray:
        """
        Decode SimCC logits to keypoint coordinates in original frame space.

        Args:
            x_logits: Shape [1, 17, W*simcc_split_ratio]
            y_logits: Shape [1, 17, H*simcc_split_ratio]
            scale_x: Horizontal scaling from model input to original frame
            scale_y: Vertical scaling from model input to original frame

        Returns:
            Array of shape (17, 3) with [x_pixel, y_pixel, confidence]
        """
        # Remove batch dimension
        x_logits = x_logits[0]  # (17, W*2)
        y_logits = y_logits[0]  # (17, H*2)

        # Argmax to get coordinate indices
        x_indices = np.argmax(x_logits, axis=1).astype(np.float64)  # (17,)
        y_indices = np.argmax(y_logits, axis=1).astype(np.float64)  # (17,)

        # Confidence from max logit values via sigmoid
        x_max = np.max(x_logits, axis=1)
        y_max = np.max(y_logits, axis=1)
        raw_conf = np.minimum(x_max, y_max)
        confidences = 1.0 / (1.0 + np.exp(-raw_conf.astype(np.float64)))

        # Convert from SimCC index to input-space coordinates
        x_coords = x_indices / SIMCC_SPLIT_RATIO
        y_coords = y_indices / SIMCC_SPLIT_RATIO

        # Scale to original frame size
        x_coords = x_coords * scale_x
        y_coords = y_coords * scale_y

        return np.stack([x_coords, y_coords, confidences], axis=1)  # (17, 3)

    def _kpts_to_skeleton2d(
        self, kpts: np.ndarray, timestamp: float
    ) -> Optional[Skeleton2D]:
        """
        Convert (17, 3) keypoints array to Skeleton2D.

        Returns None if no keypoints have sufficient confidence.
        """
        if np.max(kpts[:, 2]) < self.confidence_threshold:
            return None

        keypoints = []
        for i in range(17):
            conf = float(kpts[i, 2])
            if conf < self.confidence_threshold:
                keypoints.append(Keypoint2D(x=0.0, y=0.0, confidence=0.0))
            else:
                keypoints.append(
                    Keypoint2D(
                        x=float(kpts[i, 0]),
                        y=float(kpts[i, 1]),
                        confidence=conf,
                    )
                )

        return Skeleton2D(
            keypoints=keypoints,
            timestamp=timestamp,
            frame_index=self._frame_index,
        )

    def estimate(self, frame: np.ndarray, camera_id: int = 0) -> Optional[Skeleton2D]:
        """
        Estimate 2D pose from a single frame.

        Args:
            frame: BGR image as numpy array (H, W, 3)
            camera_id: Camera identifier (for multi-view tracking)

        Returns:
            Skeleton2D with 17 COCO keypoints in pixel coordinates,
            or None if no person detected
        """
        if not self._initialized:
            if not self.initialize():
                return None

        blob, scale_x, scale_y = self._preprocess(frame)

        outputs = self._session.run(None, {self._input_name: blob})
        x_logits, y_logits = outputs[0], outputs[1]

        kpts = self._decode_simcc(x_logits, y_logits, scale_x, scale_y)

        timestamp = time.time()
        self._frame_index += 1

        return self._kpts_to_skeleton2d(kpts, timestamp)

    def estimate_3d(self, frame: np.ndarray) -> Optional[Skeleton3D]:
        """
        RTMPose is a 2D-only estimator. Returns None.

        For 3D reconstruction, use the triangulation layer with stereo cameras.
        """
        return None

    def estimate_both(
        self, frame: np.ndarray
    ) -> Tuple[Optional[Skeleton2D], Optional[Skeleton3D]]:
        """
        Estimate 2D pose in a single pass. 3D is always None for RTMPose.

        Args:
            frame: BGR image as numpy array (H, W, 3)

        Returns:
            Tuple of (Skeleton2D, None)
        """
        skeleton_2d = self.estimate(frame)
        return skeleton_2d, None
