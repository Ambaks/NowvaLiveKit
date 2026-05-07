"""
T-Pose Camera Calibration.

Builds a canonical 3D T-pose skeleton scaled to the user's height, then
uses cv2.solvePnP per camera to determine extrinsic parameters. The
user's height provides the absolute scale reference, eliminating the
need for a checkerboard or known inter-camera distance.

Coordinate convention (matches MediaPipe / AnalyticalIKSolver):
  - Y-axis points downward
  - X-axis points to the subject's left
  - Z-axis points forward (toward front camera)
  - Origin at hip midpoint
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from biomechanics.pose.base import PoseEstimator
from biomechanics.utils.types import CocoKeypoints as CK

logger = logging.getLogger(__name__)

# Anthropometric segment-to-height ratios (biomechanics literature averages).
SEGMENT_RATIOS = {
    "head_to_shoulder": 0.130,
    "shoulder_width_half": 0.105,
    "torso": 0.290,
    "hip_width_half": 0.0725,
    "femur": 0.245,
    "tibia": 0.235,
    "upper_arm": 0.175,
    "forearm": 0.150,
}


@dataclass
class CameraCalibration:
    """Calibration result for a single camera."""
    camera_id: str
    projection_matrix: np.ndarray
    intrinsic_matrix: np.ndarray
    rotation_matrix: np.ndarray
    translation_vector: np.ndarray
    reprojection_error: float
    resolution: Tuple[int, int]


@dataclass
class CalibrationResult:
    """Complete multi-camera calibration."""
    cameras: Dict[str, CameraCalibration] = field(default_factory=dict)
    tpose_model_3d: Optional[np.ndarray] = None
    athlete_height_m: float = 0.0
    timestamp: str = ""


class TPoseCalibrator:
    """
    Calibrates multi-camera extrinsics from a T-pose and known height.

    Flow:
    1. Build a canonical T-pose 3D model scaled to user height.
    2. Detect 2D keypoints in each camera's T-pose frames via pose estimator.
    3. Average keypoints per camera to reduce noise.
    4. Use cv2.solvePnP per camera to solve for rotation and translation.
    5. Compute projection matrices P = K @ [R|t].
    """

    def __init__(
        self,
        pose_estimator: PoseEstimator,
        focal_length_factor: float = 0.8,
    ):
        self._estimator = pose_estimator
        self._focal_length_factor = focal_length_factor

    def build_tpose_model(self, height_m: float) -> np.ndarray:
        """
        Return (17, 3) canonical T-pose skeleton in world coordinates.

        The model is defined with:
          - Origin at hip midpoint
          - Y-down, X-left, Z-forward
          - Arms extended horizontally, legs straight down
        """
        r = SEGMENT_RATIOS
        h = height_m

        head_to_shoulder = r["head_to_shoulder"] * h
        shoulder_half = r["shoulder_width_half"] * h
        torso = r["torso"] * h
        hip_half = r["hip_width_half"] * h
        femur = r["femur"] * h
        tibia = r["tibia"] * h
        upper_arm = r["upper_arm"] * h
        forearm = r["forearm"] * h

        # Vertical positions relative to hip midpoint (Y-down: negative = above hip)
        hip_y = 0.0
        shoulder_y = hip_y - torso
        nose_y = shoulder_y - head_to_shoulder
        knee_y = hip_y + femur
        ankle_y = hip_y + femur + tibia

        # Eye and ear positions (slight offsets from nose)
        eye_offset_y = 0.02 * h
        eye_offset_x = 0.015 * h
        ear_offset_x = 0.04 * h

        # COCO 17 keypoints in T-pose
        # Index: 0=nose, 1=l_eye, 2=r_eye, 3=l_ear, 4=r_ear,
        #        5=l_shoulder, 6=r_shoulder, 7=l_elbow, 8=r_elbow,
        #        9=l_wrist, 10=r_wrist, 11=l_hip, 12=r_hip,
        #        13=l_knee, 14=r_knee, 15=l_ankle, 16=r_ankle

        model = np.zeros((17, 3), dtype=np.float64)

        # Head
        model[CK.NOSE] = [0.0, nose_y, 0.0]
        model[CK.LEFT_EYE] = [eye_offset_x, nose_y - eye_offset_y, 0.0]
        model[CK.RIGHT_EYE] = [-eye_offset_x, nose_y - eye_offset_y, 0.0]
        model[CK.LEFT_EAR] = [ear_offset_x, nose_y, 0.0]
        model[CK.RIGHT_EAR] = [-ear_offset_x, nose_y, 0.0]

        # Shoulders (X-left convention: left shoulder has positive X)
        model[CK.LEFT_SHOULDER] = [shoulder_half, shoulder_y, 0.0]
        model[CK.RIGHT_SHOULDER] = [-shoulder_half, shoulder_y, 0.0]

        # Arms in T-pose: extended horizontally along X axis
        model[CK.LEFT_ELBOW] = [shoulder_half + upper_arm, shoulder_y, 0.0]
        model[CK.RIGHT_ELBOW] = [-(shoulder_half + upper_arm), shoulder_y, 0.0]
        model[CK.LEFT_WRIST] = [shoulder_half + upper_arm + forearm, shoulder_y, 0.0]
        model[CK.RIGHT_WRIST] = [-(shoulder_half + upper_arm + forearm), shoulder_y, 0.0]

        # Hips
        model[CK.LEFT_HIP] = [hip_half, hip_y, 0.0]
        model[CK.RIGHT_HIP] = [-hip_half, hip_y, 0.0]

        # Legs straight down
        model[CK.LEFT_KNEE] = [hip_half, knee_y, 0.0]
        model[CK.RIGHT_KNEE] = [-hip_half, knee_y, 0.0]
        model[CK.LEFT_ANKLE] = [hip_half, ankle_y, 0.0]
        model[CK.RIGHT_ANKLE] = [-hip_half, ankle_y, 0.0]

        return model

    def _build_intrinsics(self, resolution: Tuple[int, int]) -> np.ndarray:
        """Build camera intrinsic matrix from resolution and focal length factor."""
        w, h = resolution
        f = self._focal_length_factor * w
        return np.array([
            [f, 0.0, w / 2.0],
            [0.0, f, h / 2.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

    def _detect_keypoints_averaged(
        self,
        frames: List[np.ndarray],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run pose estimation on multiple frames and average 2D keypoints.

        Returns:
            (avg_keypoints (17, 2), avg_confidences (17,))
        """
        all_kpts = []
        all_confs = []

        for frame in frames:
            skeleton = self._estimator.estimate(frame)
            if skeleton is None:
                continue

            kpts = np.zeros((17, 2), dtype=np.float64)
            confs = np.zeros(17, dtype=np.float64)

            for i in range(min(17, len(skeleton.keypoints))):
                kp = skeleton.keypoints[i]
                kpts[i] = [kp.x, kp.y]
                confs[i] = kp.confidence

            all_kpts.append(kpts)
            all_confs.append(confs)

        if not all_kpts:
            return np.zeros((17, 2)), np.zeros(17)

        avg_kpts = np.mean(all_kpts, axis=0)
        avg_confs = np.mean(all_confs, axis=0)
        return avg_kpts, avg_confs

    def calibrate(
        self,
        frames: Dict[str, List[np.ndarray]],
        height_m: float,
        resolution: Tuple[int, int],
    ) -> CalibrationResult:
        """
        Run T-pose calibration on collected frames from all cameras.

        Args:
            frames: Dict mapping camera_id -> list of T-pose frames
            height_m: Athlete height in meters
            resolution: Camera resolution (w, h)

        Returns:
            CalibrationResult with projection matrices for all cameras
        """
        from datetime import datetime

        model_3d = self.build_tpose_model(height_m)
        K = self._build_intrinsics(resolution)
        dist_coeffs = np.zeros(4, dtype=np.float64)

        result = CalibrationResult(
            tpose_model_3d=model_3d,
            athlete_height_m=height_m,
            timestamp=datetime.now().isoformat(),
        )

        for cam_id, cam_frames in frames.items():
            avg_kpts, avg_confs = self._detect_keypoints_averaged(cam_frames)

            # Only use keypoints with sufficient confidence
            valid_mask = avg_confs > 0.5
            valid_indices = np.where(valid_mask)[0]

            if len(valid_indices) < 6:
                logger.warning(
                    "Camera %s: only %d valid keypoints (need 6+), skipping",
                    cam_id, len(valid_indices),
                )
                continue

            object_points = model_3d[valid_indices].astype(np.float64)
            image_points = avg_kpts[valid_indices].astype(np.float64)

            success, rvec, tvec = cv2.solvePnP(
                object_points,
                image_points,
                K,
                dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )

            if not success:
                logger.warning("Camera %s: solvePnP failed", cam_id)
                continue

            # Refine with Levenberg-Marquardt
            rvec, tvec = cv2.solvePnPRefineLM(
                object_points, image_points, K, dist_coeffs, rvec, tvec
            )

            R, _ = cv2.Rodrigues(rvec)
            Rt = np.hstack([R, tvec])
            P = K @ Rt

            # Compute reprojection error
            projected, _ = cv2.projectPoints(
                object_points, rvec, tvec, K, dist_coeffs
            )
            projected = projected.reshape(-1, 2)
            errors = np.linalg.norm(projected - image_points, axis=1)
            reproj_error = float(np.mean(errors))

            if reproj_error > 10.0:
                logger.warning(
                    "Camera %s: high reprojection error %.1f px", cam_id, reproj_error
                )

            logger.info(
                "Camera %s: reprojection error = %.1f px (%d keypoints)",
                cam_id, reproj_error, len(valid_indices),
            )

            result.cameras[cam_id] = CameraCalibration(
                camera_id=cam_id,
                projection_matrix=P,
                intrinsic_matrix=K,
                rotation_matrix=R,
                translation_vector=tvec,
                reprojection_error=reproj_error,
                resolution=resolution,
            )

        if not result.cameras:
            raise RuntimeError("Calibration failed: no cameras calibrated successfully")

        return result

    @staticmethod
    def save_calibration(result: CalibrationResult, path: str) -> None:
        """Save calibration result to JSON."""
        data = {
            "athlete_height_m": result.athlete_height_m,
            "timestamp": result.timestamp,
            "tpose_model_3d": result.tpose_model_3d.tolist() if result.tpose_model_3d is not None else None,
            "cameras": {},
        }

        for cam_id, cam in result.cameras.items():
            data["cameras"][cam_id] = {
                "camera_id": cam.camera_id,
                "projection_matrix": cam.projection_matrix.tolist(),
                "intrinsic_matrix": cam.intrinsic_matrix.tolist(),
                "rotation_matrix": cam.rotation_matrix.tolist(),
                "translation_vector": cam.translation_vector.tolist(),
                "reprojection_error": cam.reprojection_error,
                "resolution": list(cam.resolution),
            }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Calibration saved to %s", path)

    @staticmethod
    def load_calibration(path: str) -> CalibrationResult:
        """Load calibration result from JSON."""
        with open(path) as f:
            data = json.load(f)

        result = CalibrationResult(
            athlete_height_m=data["athlete_height_m"],
            timestamp=data["timestamp"],
            tpose_model_3d=np.array(data["tpose_model_3d"]) if data.get("tpose_model_3d") else None,
        )

        for cam_id, cam_data in data["cameras"].items():
            result.cameras[cam_id] = CameraCalibration(
                camera_id=cam_data["camera_id"],
                projection_matrix=np.array(cam_data["projection_matrix"]),
                intrinsic_matrix=np.array(cam_data["intrinsic_matrix"]),
                rotation_matrix=np.array(cam_data["rotation_matrix"]),
                translation_vector=np.array(cam_data["translation_vector"]),
                reprojection_error=cam_data["reprojection_error"],
                resolution=tuple(cam_data["resolution"]),
            )

        logger.info("Calibration loaded from %s (%d cameras)", path, len(result.cameras))
        return result
