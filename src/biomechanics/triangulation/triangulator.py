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
        cam_ids = [cid for cid in self._cam_ids if cid in multi_view.views]

        # Pull keypoint data out of the Pydantic skeletons once; all math
        # below runs on plain arrays.
        n_cams = len(cam_ids)
        xy = np.zeros((n_cams, NUM_KEYPOINTS, 2), dtype=np.float64)
        conf = np.zeros((n_cams, NUM_KEYPOINTS), dtype=np.float64)
        for cam_idx, cam_id in enumerate(cam_ids):
            keypoints = multi_view.views[cam_id].keypoints
            for kpt_idx in range(min(NUM_KEYPOINTS, len(keypoints))):
                kp = keypoints[kpt_idx]
                xy[cam_idx, kpt_idx, 0] = kp.x
                xy[cam_idx, kpt_idx, 1] = kp.y
                conf[cam_idx, kpt_idx] = kp.confidence

        valid = conf >= self._min_confidence
        triangulable = valid.sum(axis=0) >= self._min_views
        if not triangulable.any():
            return None

        pts = np.zeros((NUM_KEYPOINTS, 3), dtype=np.float64)
        confs_out = np.zeros(NUM_KEYPOINTS, dtype=np.float64)

        # Group keypoints by which cameras see them, so each group
        # triangulates in one batched call instead of per-keypoint.
        groups: Dict[Tuple[int, ...], list] = {}
        for kpt_idx in np.nonzero(triangulable)[0]:
            key = tuple(np.nonzero(valid[:, kpt_idx])[0])
            groups.setdefault(key, []).append(int(kpt_idx))

        for cam_indices, kpt_list in groups.items():
            kpt_arr = np.array(kpt_list)
            cams = list(cam_indices)
            pts_2d = xy[np.ix_(cams, kpt_arr)]  # (V, n, 2)
            proj = np.stack(
                [self._proj_matrices[cam_ids[c]] for c in cams]
            ).astype(np.float64)  # (V, 3, 4)

            if len(cams) == 2:
                point_4d = cv2.triangulatePoints(
                    proj[0], proj[1], pts_2d[0].T, pts_2d[1].T
                )
                pts_3d = (point_4d[:3] / point_4d[3]).T
            else:
                # Batched DLT: stack per-keypoint A matrices, one SVD call
                A = np.empty((len(kpt_arr), 2 * len(cams), 4), dtype=np.float64)
                for view_idx in range(len(cams)):
                    P = proj[view_idx]
                    A[:, 2 * view_idx] = pts_2d[view_idx, :, 0, None] * P[2] - P[0]
                    A[:, 2 * view_idx + 1] = pts_2d[view_idx, :, 1, None] * P[2] - P[1]
                _, _, Vt = np.linalg.svd(A)
                X = Vt[:, -1, :]
                pts_3d = X[:, :3] / X[:, 3:4]

            reproj_err = self._reprojection_errors(pts_3d, pts_2d, proj)

            base_conf = conf[np.ix_(cams, kpt_arr)].min(axis=0)
            conf_scale = np.where(
                reproj_err < self._max_reproj_error,
                1.0 - reproj_err / self._max_reproj_error,
                0.1,
            )
            confs_out[kpt_arr] = np.clip(base_conf * conf_scale, 0.0, 1.0)
            pts[kpt_arr] = pts_3d

        # Re-center at hip midpoint
        if confs_out[CK.LEFT_HIP] > 0 and confs_out[CK.RIGHT_HIP] > 0:
            center = (pts[CK.LEFT_HIP] + pts[CK.RIGHT_HIP]) / 2.0
            pts[confs_out > 0] -= center

        points_3d = [
            Point3D(
                x=float(pts[i, 0]),
                y=float(pts[i, 1]),
                z=float(pts[i, 2]),
                confidence=float(confs_out[i]),
            )
            for i in range(NUM_KEYPOINTS)
        ]

        return Skeleton3D(
            keypoints=points_3d,
            timestamp=multi_view.timestamp,
            frame_index=multi_view.frame_index,
        )

    @staticmethod
    def _reprojection_errors(
        pts_3d: np.ndarray,
        pts_2d: np.ndarray,
        proj: np.ndarray,
    ) -> np.ndarray:
        # Average per-keypoint reprojection error (pixels) across views.
        # pts_3d: (n, 3), pts_2d: (V, n, 2), proj: (V, 3, 4)
        X_h = np.hstack([pts_3d, np.ones((pts_3d.shape[0], 1))])  # (n, 4)
        projected_h = np.einsum("vij,nj->vni", proj, X_h)  # (V, n, 3)

        w = projected_h[:, :, 2]
        good = np.abs(w) >= 1e-8
        safe_w = np.where(good, w, 1.0)
        projected = projected_h[:, :, :2] / safe_w[:, :, None]
        errors = np.linalg.norm(projected - pts_2d, axis=2)  # (V, n)

        n_good = good.sum(axis=0)
        err_sum = np.where(good, errors, 0.0).sum(axis=0)
        return np.where(n_good > 0, err_sum / np.maximum(n_good, 1), 999.0)
