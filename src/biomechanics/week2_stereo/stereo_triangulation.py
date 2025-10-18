"""
Week 2: Stereo Triangulation
3D reconstruction from stereo camera pair

Success Criteria:
- 3D coordinates from 2D correspondences
- Hip position tracked in 3D
- Reprojection error < 5 pixels
"""

import cv2
import numpy as np
import sys
import os

# Add week1_pose to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'week1_pose'))
from minimal_pose_demo import RTMPoseEstimator


class StereoReconstructor:
    """3D reconstruction from calibrated stereo cameras"""

    def __init__(self, calibration_file='stereo_calibration.npz', baseline=0.3):
        """
        Initialize stereo reconstructor

        Args:
            calibration_file: Path to calibration file
            baseline: Distance between cameras in meters (approximate)
        """
        if os.path.exists(calibration_file):
            print(f"Loading calibration from {calibration_file}")
            calib = np.load(calibration_file)

            self.K0 = calib['cam0_matrix']
            self.dist0 = calib['cam0_dist']
            self.K1 = calib['cam1_matrix']
            self.dist1 = calib['cam1_dist']
        else:
            print(f"Warning: Calibration file not found. Using default parameters.")
            # Default camera matrix (adjust for your cameras)
            self.K0 = np.array([[1000, 0, 640],
                               [0, 1000, 360],
                               [0, 0, 1]], dtype=np.float32)
            self.K1 = self.K0.copy()
            self.dist0 = np.zeros(5, dtype=np.float32)
            self.dist1 = np.zeros(5, dtype=np.float32)

        # Assume cameras are side-by-side (will be more accurate with stereo calibration)
        self.R = np.eye(3)  # Relative rotation
        self.T = np.array([[baseline], [0], [0]])  # Baseline distance

        # Compute projection matrices
        self.P0 = self.K0 @ np.hstack([np.eye(3), np.zeros((3, 1))])
        self.P1 = self.K1 @ np.hstack([self.R, self.T])

        print("Stereo reconstructor initialized")
        print(f"Baseline: {baseline}m")

    def triangulate_points(self, pts0, pts1, confidences=None, threshold=0.3):
        """
        Triangulate 3D points from 2D correspondences

        Args:
            pts0: Nx2 array of 2D points from camera 0
            pts1: Nx2 array of 2D points from camera 1
            confidences: Nx2 array of confidence scores (optional)
            threshold: Minimum confidence to use point

        Returns:
            points_3d: Nx3 array of 3D points
        """
        if len(pts0) == 0 or len(pts1) == 0:
            return np.zeros((0, 3))

        # Filter low-confidence points
        if confidences is not None:
            valid = (confidences[:, 0] > threshold) & (confidences[:, 1] > threshold)
            pts0 = pts0[valid]
            pts1 = pts1[valid]

            if len(pts0) == 0:
                return np.zeros((0, 3))

        # Undistort points
        pts0_undist = cv2.undistortPoints(
            pts0.reshape(-1, 1, 2),
            self.K0,
            self.dist0,
            P=self.K0
        ).reshape(-1, 2)

        pts1_undist = cv2.undistortPoints(
            pts1.reshape(-1, 1, 2),
            self.K1,
            self.dist1,
            P=self.K1
        ).reshape(-1, 2)

        # Triangulate
        points_4d = cv2.triangulatePoints(
            self.P0,
            self.P1,
            pts0_undist.T,
            pts1_undist.T
        )

        # Convert from homogeneous coordinates
        points_3d = points_4d[:3] / points_4d[3]

        return points_3d.T  # Nx3


class DualCameraCapture:
    """Synchronized capture from two cameras"""

    def __init__(self, cam0_id=0, cam1_id=1, width=1280, height=720):
        """
        Initialize dual camera capture

        Args:
            cam0_id: First camera device ID
            cam1_id: Second camera device ID
            width: Frame width
            height: Frame height
        """
        self.cap0 = cv2.VideoCapture(cam0_id)
        self.cap1 = cv2.VideoCapture(cam1_id)

        # Set resolution
        for cap in [self.cap0, self.cap1]:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Test capture
        ret0, _ = self.cap0.read()
        ret1, _ = self.cap1.read()

        if not ret0:
            raise ValueError(f"Failed to open camera {cam0_id}")
        if not ret1:
            raise ValueError(f"Failed to open camera {cam1_id}")

        print(f"Dual camera capture initialized: cam{cam0_id}, cam{cam1_id}")

    def capture_synchronized(self):
        """
        Capture from both cameras (software synchronization)

        Returns:
            frame0, frame1: Captured frames (or None, None on failure)
        """
        ret0, frame0 = self.cap0.read()
        ret1, frame1 = self.cap1.read()

        if ret0 and ret1:
            return frame0, frame1
        return None, None

    def release(self):
        """Release cameras"""
        self.cap0.release()
        self.cap1.release()


def demo_3d_reconstruction(cam0_id=0, cam1_id=1):
    """
    Demo: 3D reconstruction from stereo cameras with pose estimation

    Args:
        cam0_id: First camera ID
        cam1_id: Second camera ID
    """
    print("\n=== Stereo 3D Reconstruction Demo ===")
    print("Press 'q' to quit")
    print("Press 's' to save current 3D points\n")

    # Initialize components
    pose_model = RTMPoseEstimator(device='mps')
    stereo = StereoReconstructor()
    cameras = DualCameraCapture(cam0_id=cam0_id, cam1_id=cam1_id)

    # Keypoint names for display
    joint_names = [
        'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
        'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
        'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
        'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
    ]

    import time
    frame_count = 0
    fps = 0
    start_time = time.time()

    while True:
        frame0, frame1 = cameras.capture_synchronized()
        if frame0 is None:
            print("Failed to capture frames")
            break

        # Get 2D poses from both views
        kpts0 = pose_model.predict(frame0)
        kpts1 = pose_model.predict(frame1)

        # Draw 2D skeletons
        frame0_vis = pose_model.draw_skeleton(frame0.copy(), kpts0)
        frame1_vis = pose_model.draw_skeleton(frame1.copy(), kpts1)

        # Triangulate 3D points
        if kpts0.shape[0] == kpts1.shape[0]:
            confidences = np.stack([kpts0[:, 2], kpts1[:, 2]], axis=1)
            points_3d = stereo.triangulate_points(
                kpts0[:, :2],
                kpts1[:, :2],
                confidences
            )

            # Display 3D information
            if len(points_3d) > 0:
                # Example: show left hip position (index 11)
                if len(points_3d) > 11:
                    left_hip = points_3d[11]
                    cv2.putText(frame0_vis,
                               f"L Hip 3D: ({left_hip[0]:.2f}, {left_hip[1]:.2f}, {left_hip[2]:.2f})m",
                               (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

                # Show number of reconstructed points
                cv2.putText(frame0_vis,
                           f"3D Points: {len(points_3d)}",
                           (10, 90),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Calculate FPS
        frame_count += 1
        if frame_count % 10 == 0:
            end_time = time.time()
            fps = 10 / (end_time - start_time)
            start_time = end_time

        # Display FPS
        cv2.putText(frame0_vis, f'FPS: {fps:.1f}', (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Combine views side-by-side
        combined = np.hstack([frame0_vis, frame1_vis])

        # Add separator line
        h, w = combined.shape[:2]
        cv2.line(combined, (w//2, 0), (w//2, h), (255, 255, 255), 2)

        cv2.imshow('Stereo 3D Reconstruction', combined)

        # Handle keys
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s') and len(points_3d) > 0:
            filename = f'points_3d_{int(time.time())}.npy'
            np.save(filename, points_3d)
            print(f"Saved 3D points to {filename}")
            print(f"Shape: {points_3d.shape}")
            for i, name in enumerate(joint_names[:len(points_3d)]):
                print(f"  {name}: {points_3d[i]}")

    # Cleanup
    cameras.release()
    cv2.destroyAllWindows()

    print(f"\nAverage FPS: {fps:.1f}")
    print("Demo completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        cam0 = int(sys.argv[1])
        cam1 = int(sys.argv[2])
    else:
        cam0, cam1 = 0, 1

    demo_3d_reconstruction(cam0_id=cam0, cam1_id=cam1)
