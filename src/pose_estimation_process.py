"""
Pose Estimation Process
Wrapper for running stereo pose estimation with IPC communication
"""

import sys
import os
import time
from pathlib import Path

# Add biomechanics to path
sys.path.insert(0, str(Path(__file__).parent / 'biomechanics' / 'week2_stereo'))
sys.path.insert(0, str(Path(__file__).parent / 'biomechanics' / 'week1_pose'))

from ipc_communication import IPCClient


def run_pose_estimation_with_ipc(cam0_id: int = 0, cam1_id: int = 1):
    """
    Run pose estimation and send data via IPC

    Args:
        cam0_id: First camera ID
        cam1_id: Second camera ID
    """
    print("\n=== Pose Estimation Process Started ===")
    print(f"Using cameras: {cam0_id}, {cam1_id}")

    # Connect to IPC server
    ipc_client = IPCClient()
    if not ipc_client.connect(timeout=10):
        print("Failed to connect to IPC server. Exiting.")
        return

    # Import here to avoid issues if biomechanics imports fail
    try:
        from stereo_triangulation import StereoReconstructor, DualCameraCapture
        from minimal_pose_demo import RTMPoseEstimator
        import cv2
        import numpy as np
    except ImportError as e:
        print(f"Error importing pose estimation modules: {e}")
        ipc_client.disconnect()
        return

    # Initialize components
    try:
        print("Initializing pose estimation...")

        # Load calibration from week2_stereo directory
        calibration_path = Path(__file__).parent / 'biomechanics' / 'week2_stereo' / 'stereo_calibration.npz'

        pose_model = RTMPoseEstimator(device='mps')
        stereo = StereoReconstructor(calibration_file=str(calibration_path))
        cameras = DualCameraCapture(cam0_id=cam0_id, cam1_id=cam1_id)

        print("Pose estimation initialized successfully")

        # Send initialization message
        ipc_client.send_message({
            "type": "status",
            "value": "initialized"
        })

    except Exception as e:
        print(f"Error initializing pose estimation: {e}")
        ipc_client.send_message({
            "type": "error",
            "value": str(e)
        })
        ipc_client.disconnect()
        return

    # Main processing loop
    frame_count = 0
    rep_count = 0  # Placeholder

    print("\nStarting pose estimation loop...")
    print("Press 'q' in the OpenCV window to quit")

    try:
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
            points_3d = np.zeros((0, 3))
            if kpts0.shape[0] == kpts1.shape[0]:
                confidences = np.stack([kpts0[:, 2], kpts1[:, 2]], axis=1)
                points_3d = stereo.triangulate_points(
                    kpts0[:, :2],
                    kpts1[:, :2],
                    confidences
                )

            # Send placeholder data via IPC every 30 frames (~1 second at 30fps)
            if frame_count % 30 == 0:
                # Placeholder: increment rep count
                rep_count += 1

                ipc_client.send_message({
                    "type": "rep_count",
                    "value": rep_count
                })

                # Placeholder: send random form feedback
                if rep_count % 3 == 0:
                    ipc_client.send_message({
                        "type": "feedback",
                        "value": "knees caving"
                    })

            # Display combined view
            combined = np.hstack([frame0_vis, frame1_vis])
            h, w = combined.shape[:2]
            cv2.line(combined, (w//2, 0), (w//2, h), (255, 255, 255), 2)

            # Add rep count overlay
            cv2.putText(combined, f'Reps: {rep_count}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow('Pose Estimation', combined)

            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

            frame_count += 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError during pose estimation: {e}")
        ipc_client.send_message({
            "type": "error",
            "value": str(e)
        })
    finally:
        # Cleanup
        cameras.release()
        cv2.destroyAllWindows()
        ipc_client.disconnect()
        print("\nPose estimation process stopped")


if __name__ == "__main__":
    # Parse command line arguments for camera IDs
    cam0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cam1 = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    run_pose_estimation_with_ipc(cam0_id=cam0, cam1_id=cam1)
