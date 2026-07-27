"""
DLT (Direct Linear Transform) Triangulation.

Triangulates 2D keypoints from multiple calibrated camera views into
3D world coordinates using the DLT algorithm.

For 2 views: uses cv2.triangulatePoints.
For 3+ views: builds the standard DLT system Ax=0 and solves via SVD.
"""

import logging
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from biomechanics.triangulation.calibration import CalibrationResult
from biomechanics.utils.types import (
    MultiViewPose,
    Point3D,
    Skeleton3D,
    CocoKeypoints as CK,
)

logger = logging.getLogger(__name__)

NUM_KEYPOINTS = 19


class DLTTriangulator:
    """
    Triangulates multi-view 2D detections into 3D world coordinates.

    For each keypoint, collects 2D positions from all views where
    confidence exceeds a threshold, then triangulates using DLT.
    Output is re-centered at the hip midpoint to match the convention
    used by AnalyticalIKSolver.
    """

    def __init__(
        self,
        calibration: CalibrationResult,
        min_views: int = 2,
        max_reprojection_error: float = 15.0,
        min_confidence: float = 0.3,
    ):
        self._calibration = calibration
        self._min_views = min_views
        self._max_reproj_error = max_reprojection_error
        self._min_confidence = min_confidence

        self._cam_ids = sorted(calibration.cameras.keys())
        self._proj_matrices = {
            cam_id: calibration.cameras[cam_id].projection_matrix
            for cam_id in self._cam_ids
        }

    def triangulate(self, multi_view: MultiViewPose) -> Optional[Skeleton3D]:
        """
        Triangulate all keypoints from multi-view 2D detections.

        Args:
            multi_view: MultiViewPose with 2D detections from each camera

        Returns:
            Skeleton3D in world coordinates (Y-down, origin at hip midpoint),
            or None if insufficient views.
        """
        points_3d = []
        any_valid = False

        for kpt_idx in range(NUM_KEYPOINTS):
            pts_2d = {}
            confs = {}

            for cam_id in self._cam_ids:
                if cam_id not in multi_view.views:
                    continue

                skeleton = multi_view.views[cam_id]
                if kpt_idx >= len(skeleton.keypoints):
                    continue

                kp = skeleton.keypoints[kpt_idx]
                if kp.confidence >= self._min_confidence:
                    pts_2d[cam_id] = np.array([kp.x, kp.y], dtype=np.float64)
                    confs[cam_id] = kp.confidence

            if len(pts_2d) >= self._min_views:
                point_3d, reproj_err = self._triangulate_point(pts_2d)

                conf = min(confs.values())
                if reproj_err < self._max_reproj_error:
                    conf *= (1.0 - reproj_err / self._max_reproj_error)
                else:
                    conf *= 0.1

                points_3d.append(Point3D(
                    x=float(point_3d[0]),
                    y=float(point_3d[1]),
                    z=float(point_3d[2]),
                    confidence=max(0.0, min(1.0, conf)),
                ))
                any_valid = True
            else:
                points_3d.append(Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0))

        if not any_valid:
            return None

        # Re-center at hip midpoint
        l_hip = points_3d[CK.LEFT_HIP]
        r_hip = points_3d[CK.RIGHT_HIP]

        if l_hip.confidence > 0 and r_hip.confidence > 0:
            cx = (l_hip.x + r_hip.x) / 2.0
            cy = (l_hip.y + r_hip.y) / 2.0
            cz = (l_hip.z + r_hip.z) / 2.0

            for i, pt in enumerate(points_3d):
                if pt.confidence > 0:
                    points_3d[i] = Point3D(
                        x=pt.x - cx,
                        y=pt.y - cy,
                        z=pt.z - cz,
                        confidence=pt.confidence,
                    )

        return Skeleton3D(
            keypoints=points_3d,
            timestamp=multi_view.timestamp,
            frame_index=multi_view.frame_index,
        )

    def _triangulate_point(
        self,
        points_2d: Dict[str, np.ndarray],
    ) -> Tuple[np.ndarray, float]:
        """
        Triangulate a single 3D point from multiple 2D observations.

        For 2 views: uses cv2.triangulatePoints.
        For 3+ views: SVD-based DLT.

        Returns:
            (point_3d, average_reprojection_error_in_pixels)
        """
        cam_ids = sorted(points_2d.keys())
        proj_mats = [self._proj_matrices[cid] for cid in cam_ids]

        if len(cam_ids) == 2:
            pt1 = points_2d[cam_ids[0]].reshape(2, 1).astype(np.float64)
            pt2 = points_2d[cam_ids[1]].reshape(2, 1).astype(np.float64)
            P1 = proj_mats[0].astype(np.float64)
            P2 = proj_mats[1].astype(np.float64)

            point_4d = cv2.triangulatePoints(P1, P2, pt1, pt2)
            point_3d = (point_4d[:3] / point_4d[3]).flatten()
        else:
            # SVD-based DLT for 3+ views
            A = np.zeros((2 * len(cam_ids), 4), dtype=np.float64)
            for i, cid in enumerate(cam_ids):
                P = proj_mats[i]
                x, y = points_2d[cid]
                A[2 * i] = x * P[2] - P[0]
                A[2 * i + 1] = y * P[2] - P[1]

            _, _, Vt = np.linalg.svd(A)
            X = Vt[-1]
            point_3d = (X[:3] / X[3])

        reproj_err = self._compute_reprojection_error(
            point_3d, points_2d, {cid: self._proj_matrices[cid] for cid in cam_ids}
        )

        return point_3d, reproj_err

    def _compute_reprojection_error(
        self,
        point_3d: np.ndarray,
        points_2d: Dict[str, np.ndarray],
        proj_matrices: Dict[str, np.ndarray],
    ) -> float:
        """Average reprojection error across all views in pixels."""
        errors = []
        X_h = np.append(point_3d, 1.0)

        for cam_id, pt_2d in points_2d.items():
            P = proj_matrices[cam_id]
            projected_h = P @ X_h
            if abs(projected_h[2]) < 1e-8:
                continue
            projected = projected_h[:2] / projected_h[2]
            errors.append(np.linalg.norm(projected - pt_2d))

        return float(np.mean(errors)) if errors else 999.0
