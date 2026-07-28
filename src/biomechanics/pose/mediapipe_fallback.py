"""
MediaPipe pose estimation backend.

Uses MediaPipe's PoseLandmarker task API (v0.10+) and maps the 33 BlazePose
landmarks to COCO 17 format.

Note: The new MediaPipe API requires downloading a model file on first use.
The model is cached in ~/.mediapipe/models/.
"""

import os
import time
import urllib.request
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

from biomechanics.pose.base import PoseEstimator, COCO_KEYPOINT_NAMES
from biomechanics.utils.types import Skeleton2D, Skeleton3D, Keypoint2D, Point3D


# MediaPipe BlazePose (33 landmarks) to COCO 17 mapping
# BlazePose index -> COCO index
BLAZEPOSE_TO_COCO = {
    0: 0,    # nose -> nose
    2: 1,    # left_eye_inner -> left_eye (using inner eye as approximation)
    5: 2,    # right_eye_inner -> right_eye (using inner eye as approximation)
    7: 3,    # left_ear -> left_ear
    8: 4,    # right_ear -> right_ear
    11: 5,   # left_shoulder -> left_shoulder
    12: 6,   # right_shoulder -> right_shoulder
    13: 7,   # left_elbow -> left_elbow
    14: 8,   # right_elbow -> right_elbow
    15: 9,   # left_wrist -> left_wrist
    16: 10,  # right_wrist -> right_wrist
    23: 11,  # left_hip -> left_hip
    24: 12,  # right_hip -> right_hip
    25: 13,  # left_knee -> left_knee
    26: 14,  # right_knee -> right_knee
    27: 15,  # left_ankle -> left_ankle
    28: 16,  # right_ankle -> right_ankle
    31: 17,  # left_foot_index -> left_foot_index
    32: 18,  # right_foot_index -> right_foot_index
    29: 19,  # left_heel -> left_heel
    30: 20,  # right_heel -> right_heel
}

# Keypoints emitted per skeleton: COCO 17 + both toes + both heels.
NUM_KEYPOINTS = 21

# Reverse mapping: COCO index -> BlazePose index
COCO_TO_BLAZEPOSE = {v: k for k, v in BLAZEPOSE_TO_COCO.items()}

# Model URLs for different complexity levels
# lite = fastest, full = balanced, heavy = most accurate
MODEL_URLS = {
    0: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    1: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
    2: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
}

MODEL_NAMES = {
    0: "pose_landmarker_lite.task",
    1: "pose_landmarker_full.task",
    2: "pose_landmarker_heavy.task",
}

# Downsample input frames before inference. MediaPipe rescales internally
# anyway, so feeding full 720p is wasted work.
INFERENCE_SCALE = 0.5


def get_model_path(model_complexity: int = 1) -> Path:
    """
    Get path to pose landmarker model, downloading if necessary.

    Args:
        model_complexity: 0=lite, 1=full, 2=heavy

    Returns:
        Path to the model file
    """
    # Store models in ~/.mediapipe/models/
    cache_dir = Path.home() / ".mediapipe" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)

    model_name = MODEL_NAMES.get(model_complexity, MODEL_NAMES[1])
    model_path = cache_dir / model_name

    if not model_path.exists():
        url = MODEL_URLS.get(model_complexity, MODEL_URLS[1])
        print(f"Downloading MediaPipe pose model: {model_name}")
        print(f"From: {url}")
        print(f"To: {model_path}")

        try:
            urllib.request.urlretrieve(url, model_path)
            print("Download complete.")
        except Exception as e:
            raise RuntimeError(f"Failed to download pose model: {e}")

    return model_path


class MediaPipePoseEstimator(PoseEstimator):
    """
    MediaPipe-based pose estimator using the new tasks API (v0.10+).

    Uses MediaPipe's PoseLandmarker for pose estimation.
    Provides both 2D pixel coordinates and 3D world coordinates.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        """
        Initialize MediaPipe pose estimator.

        Args:
            confidence_threshold: Minimum confidence to consider keypoint valid
            model_complexity: Model complexity (0=lite, 1=full, 2=heavy)
            min_detection_confidence: Minimum confidence for person detection
            min_tracking_confidence: Minimum confidence for pose tracking
        """
        super().__init__(confidence_threshold)

        if not MEDIAPIPE_AVAILABLE:
            raise ImportError("MediaPipe is not installed. Run: pip install mediapipe")

        self.model_complexity = model_complexity
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence

        self._landmarker = None
        self._frame_index = 0
        self._last_timestamp_ms = 0

    def initialize(self) -> bool:
        """Initialize the MediaPipe pose landmarker."""
        if self._initialized:
            return True

        try:
            # Get model path (downloads if needed)
            model_path = get_model_path(self.model_complexity)

            # Configure pose landmarker options
            # Use CPU delegate to avoid Metal SIGTRAP crashes on Apple Silicon
            delegate = mp_tasks.BaseOptions.Delegate.CPU
            if os.getenv("MEDIAPIPE_USE_GPU", "").lower() == "true":
                delegate = mp_tasks.BaseOptions.Delegate.GPU
            base_options = mp_tasks.BaseOptions(
                model_asset_path=str(model_path),
                delegate=delegate,
            )

            options = mp_vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=self.min_detection_confidence,
                min_pose_presence_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
                output_segmentation_masks=False,
            )

            self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
            self._initialized = True
            return True

        except Exception as e:
            print(f"Failed to initialize MediaPipe Pose: {e}")
            return False

    def release(self) -> None:
        """Release MediaPipe resources."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        self._initialized = False

    def _next_timestamp_ms(self) -> int:
        ts = int(time.monotonic() * 1000)
        if ts <= self._last_timestamp_ms:
            ts = self._last_timestamp_ms + 1
        self._last_timestamp_ms = ts
        return ts

    def _downscale(self, frame_rgb: np.ndarray) -> np.ndarray:
        h, w = frame_rgb.shape[:2]
        return cv2.resize(
            frame_rgb,
            (int(w * INFERENCE_SCALE), int(h * INFERENCE_SCALE)),
            interpolation=cv2.INTER_AREA,
        )

    def _convert_landmarks_to_skeleton2d(
        self,
        landmarks,
        frame_width: int,
        frame_height: int,
        timestamp: float,
    ) -> Skeleton2D:
        """Convert MediaPipe landmarks to COCO 17 format Skeleton2D."""
        keypoints = []

        for coco_idx in range(NUM_KEYPOINTS):
            blazepose_idx = COCO_TO_BLAZEPOSE.get(coco_idx)

            if blazepose_idx is not None and blazepose_idx < len(landmarks):
                landmark = landmarks[blazepose_idx]

                # Convert normalized coordinates to pixel coordinates
                x = landmark.x * frame_width
                y = landmark.y * frame_height
                confidence = landmark.visibility if hasattr(landmark, 'visibility') else landmark.presence

                # Filter low confidence keypoints
                if confidence < self.confidence_threshold:
                    keypoints.append(Keypoint2D(x=0.0, y=0.0, confidence=0.0))
                else:
                    keypoints.append(Keypoint2D(x=x, y=y, confidence=confidence))
            else:
                keypoints.append(Keypoint2D(x=0.0, y=0.0, confidence=0.0))

        return Skeleton2D(
            keypoints=keypoints,
            timestamp=timestamp,
            frame_index=self._frame_index,
        )

    def _convert_world_landmarks_to_skeleton3d(
        self,
        world_landmarks,
        timestamp: float,
    ) -> Skeleton3D:
        """Convert MediaPipe world landmarks to COCO 17 format Skeleton3D."""
        keypoints = []

        for coco_idx in range(NUM_KEYPOINTS):
            blazepose_idx = COCO_TO_BLAZEPOSE.get(coco_idx)

            if blazepose_idx is not None and blazepose_idx < len(world_landmarks):
                landmark = world_landmarks[blazepose_idx]

                x = landmark.x
                y = landmark.y
                z = landmark.z
                confidence = landmark.visibility if hasattr(landmark, 'visibility') else landmark.presence

                if confidence < self.confidence_threshold:
                    keypoints.append(Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0))
                else:
                    keypoints.append(Point3D(x=x, y=y, z=z, confidence=confidence))
            else:
                keypoints.append(Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0))

        return Skeleton3D(
            keypoints=keypoints,
            timestamp=timestamp,
            frame_index=self._frame_index,
        )

    def estimate(self, frame: np.ndarray, camera_id: int = 0) -> Optional[Skeleton2D]:
        """
        Estimate 2D pose from a single frame.

        Args:
            frame: BGR image as numpy array (H, W, 3)
            camera_id: Camera identifier (unused for MediaPipe)

        Returns:
            Skeleton2D with 17 keypoints in pixel coordinates, or None if no person detected
        """
        if not self._initialized:
            if not self.initialize():
                return None

        orig_h, orig_w = frame.shape[:2]
        frame_rgb = frame[:, :, ::-1].copy() if frame.shape[2] == 3 else frame.copy()
        frame_small = self._downscale(frame_rgb)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_small)
        result = self._landmarker.detect_for_video(mp_image, self._next_timestamp_ms())

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None

        timestamp = time.time()
        self._frame_index += 1

        landmarks = result.pose_landmarks[0]
        return self._convert_landmarks_to_skeleton2d(landmarks, orig_w, orig_h, timestamp)

    def estimate_3d(self, frame: np.ndarray) -> Optional[Skeleton3D]:
        """
        Estimate 3D pose from a single frame using MediaPipe's world landmarks.

        MediaPipe provides 3D coordinates in meters, centered at the hip.

        Args:
            frame: BGR image as numpy array (H, W, 3)

        Returns:
            Skeleton3D with 17 keypoints in world coordinates (meters), or None if no person detected
        """
        if not self._initialized:
            if not self.initialize():
                return None

        frame_rgb = frame[:, :, ::-1].copy() if frame.shape[2] == 3 else frame.copy()
        frame_small = self._downscale(frame_rgb)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_small)
        result = self._landmarker.detect_for_video(mp_image, self._next_timestamp_ms())

        if not result.pose_world_landmarks or len(result.pose_world_landmarks) == 0:
            return None

        timestamp = time.time()
        self._frame_index += 1

        world_landmarks = result.pose_world_landmarks[0]
        return self._convert_world_landmarks_to_skeleton3d(world_landmarks, timestamp)

    def estimate_both(self, frame: np.ndarray) -> tuple[Optional[Skeleton2D], Optional[Skeleton3D]]:
        """
        Estimate both 2D and 3D pose from a single frame in one pass.

        More efficient than calling estimate() and estimate_3d() separately.

        Args:
            frame: BGR image as numpy array (H, W, 3)

        Returns:
            Tuple of (Skeleton2D, Skeleton3D), either may be None if no person detected
        """
        if not self._initialized:
            if not self.initialize():
                return None, None

        orig_h, orig_w = frame.shape[:2]
        frame_rgb = frame[:, :, ::-1].copy() if frame.shape[2] == 3 else frame.copy()
        frame_small = self._downscale(frame_rgb)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_small)
        result = self._landmarker.detect_for_video(mp_image, self._next_timestamp_ms())

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None, None

        timestamp = time.time()
        self._frame_index += 1

        landmarks = result.pose_landmarks[0]
        skeleton_2d = self._convert_landmarks_to_skeleton2d(landmarks, orig_w, orig_h, timestamp)

        skeleton_3d = None
        if result.pose_world_landmarks and len(result.pose_world_landmarks) > 0:
            world_landmarks = result.pose_world_landmarks[0]
            skeleton_3d = self._convert_world_landmarks_to_skeleton3d(world_landmarks, timestamp)

        return skeleton_2d, skeleton_3d
