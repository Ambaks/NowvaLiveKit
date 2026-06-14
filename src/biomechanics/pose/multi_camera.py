"""
Multi-camera pose provider.

Captures synced frames from N cameras, runs RTMPose halpe26 on each,
and triangulates to 3D via DLT. From the pipeline's perspective this
is a black box that produces (frame, Skeleton2D, Skeleton3D).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from biomechanics.pose.rtmpose import RTMPoseEstimator
from biomechanics.triangulation.calibration import (
    CalibrationResult,
    TPoseCalibrator,
)
from biomechanics.triangulation.multi_capture import MultiCameraCapture
from biomechanics.triangulation.triangulator import DLTTriangulator
from biomechanics.utils.types import MultiViewPose, Skeleton2D, Skeleton3D

logger = logging.getLogger(__name__)


class MultiCameraPoseProvider:
    """
    Encapsulates multi-camera capture, per-view RTMPose estimation, and
    DLT triangulation into a single get_pose() call.
    """

    def __init__(
        self,
        device_ids: list[int],
        confidence_threshold: float = 0.3,
        model_path: str | None = None,
        min_views: int = 2,
        max_reprojection_error: float = 15.0,
        max_sync_delta_ms: float = 15.0,
        resolution: tuple[int, int] = (1280, 720),
        primary_camera: int = 0,
        focal_length_factor: float = 0.8,
    ):
        self._device_ids = device_ids
        self._confidence_threshold = confidence_threshold
        self._model_path = model_path
        self._min_views = min_views
        self._max_reprojection_error = max_reprojection_error
        self._max_sync_delta_ms = max_sync_delta_ms
        self._resolution = resolution
        self._primary_camera = primary_camera
        self._focal_length_factor = focal_length_factor

        self._capture: MultiCameraCapture | None = None
        self._estimator: RTMPoseEstimator | None = None
        self._triangulator: DLTTriangulator | None = None
        self._calibration: CalibrationResult | None = None
        self._initialized = False

    @property
    def is_calibrated(self) -> bool:
        return self._calibration is not None

    def initialize(self) -> bool:
        """Create the RTMPose halpe26 estimator."""
        if self._initialized:
            return True

        self._estimator = RTMPoseEstimator(
            confidence_threshold=self._confidence_threshold,
            model_path=self._model_path,
            keypoint_format="halpe26",
        )
        self._estimator.initialize()
        self._initialized = True
        return True

    def start(self) -> None:
        """Open cameras and start reader threads."""
        if not self._initialized:
            self.initialize()

        self._capture = MultiCameraCapture(
            device_ids=self._device_ids,
            resolution=self._resolution,
            max_sync_delta_ms=self._max_sync_delta_ms,
        )
        self._capture.start()

    def load_calibration(self, path: str) -> None:
        """Load a saved calibration and build the triangulator."""
        self._calibration = TPoseCalibrator.load_calibration(path)
        self._triangulator = DLTTriangulator(
            calibration=self._calibration,
            min_views=self._min_views,
            max_reprojection_error=self._max_reprojection_error,
            min_confidence=self._confidence_threshold,
        )
        logger.info(
            "Loaded calibration with %d cameras", len(self._calibration.cameras)
        )

    def calibrate(
        self,
        height_m: float,
        n_frames: int = 30,
        save_path: str | None = None,
    ) -> CalibrationResult:
        """
        Run T-pose calibration: capture frames from all cameras, detect
        keypoints, solve for camera extrinsics.
        """
        if not self._initialized:
            self.initialize()
        if self._capture is None:
            self.start()

        calibrator = TPoseCalibrator(
            pose_estimator=self._estimator,
            focal_length_factor=self._focal_length_factor,
        )

        logger.info("Capturing %d T-pose frames from %d cameras...", n_frames, len(self._device_ids))
        frames_per_camera: dict[str, list[np.ndarray]] = {
            str(dev_id): [] for dev_id in self._device_ids
        }

        collected = 0
        while collected < n_frames:
            synced = self._capture.get_synced_frames()
            if synced is None:
                time.sleep(0.01)
                continue
            synced_frames, _ = synced
            for cam_id, frame in synced_frames.items():
                frames_per_camera[cam_id].append(frame)
            collected += 1

        self._calibration = calibrator.calibrate(
            frames=frames_per_camera,
            height_m=height_m,
            resolution=self._resolution,
        )

        self._triangulator = DLTTriangulator(
            calibration=self._calibration,
            min_views=self._min_views,
            max_reprojection_error=self._max_reprojection_error,
            min_confidence=self._confidence_threshold,
        )

        if save_path is not None:
            TPoseCalibrator.save_calibration(self._calibration, save_path)

        logger.info("Calibration complete: %d cameras", len(self._calibration.cameras))
        return self._calibration

    def get_pose(
        self,
    ) -> tuple[np.ndarray | None, Skeleton2D | None, Skeleton3D | None]:
        """
        Grab synced frames, run per-camera pose estimation, triangulate.

        Returns:
            (primary_frame, primary_skeleton_2d, triangulated_skeleton_3d)
        """
        if self._capture is None or self._triangulator is None:
            return None, None, None

        synced = self._capture.get_synced_frames()
        if synced is None:
            return None, None, None

        synced_frames, ref_ts = synced
        primary_id = str(self._primary_camera)

        views: dict[str, Skeleton2D] = {}
        primary_skeleton_2d: Skeleton2D | None = None

        for cam_id, frame in synced_frames.items():
            skeleton_2d = self._estimator.estimate(frame)
            if skeleton_2d is not None:
                views[cam_id] = skeleton_2d
                if cam_id == primary_id:
                    primary_skeleton_2d = skeleton_2d

        if len(views) < self._min_views:
            return synced_frames.get(primary_id), primary_skeleton_2d, None

        multi_view = MultiViewPose(
            views=views,
            timestamp=ref_ts,
            frame_index=0,
        )
        skeleton_3d = self._triangulator.triangulate(multi_view)

        return synced_frames.get(primary_id), primary_skeleton_2d, skeleton_3d

    def release(self) -> None:
        """Stop capture and release resources."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._estimator is not None:
            self._estimator.release()
            self._estimator = None
        self._triangulator = None
        self._calibration = None
        self._initialized = False
