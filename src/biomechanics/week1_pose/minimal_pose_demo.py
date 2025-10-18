"""
Week 1: Minimal RTMPose Demo
Real-time pose estimation using RTMPose from MMPose

Success Criteria:
- See skeleton overlay on webcam feed
- 20+ FPS on M2 MacBook
- Keypoints track movement smoothly
"""

import cv2
import torch
import numpy as np
import os
from pathlib import Path

# Fix PyTorch 2.6 weights_only=True default for MMPose compatibility
# MMPose checkpoints contain numpy arrays which require weights_only=False
# This is safe as the checkpoint is from official OpenMMLab source
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# Monkey patch torch.load to use weights_only=False by default
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault('weights_only', False)
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from mmpose.apis import inference_topdown, init_model


class RTMPoseEstimator:
    """RTMPose wrapper for real-time pose estimation"""

    def __init__(self, config=None, checkpoint=None, device='mps'):
        """
        Initialize RTMPose model

        Args:
            config: Path to config file (uses default if None)
            checkpoint: Path to checkpoint (uses default if None)
            device: 'mps' for Apple Silicon, 'cuda' for NVIDIA, 'cpu' otherwise
        """
        # Default RTMPose-M configuration
        models_dir = Path(__file__).parent / 'models'

        if config is None:
            config = models_dir / 'rtmpose-m_8xb256-420e_coco-256x192.py'
        if checkpoint is None:
            checkpoint = models_dir / 'rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth'

        # Check if model files exist
        if not Path(config).exists() or not Path(checkpoint).exists():
            print("⚠ RTMPose model files not found!")
            print("\nPlease run the download script first:")
            print("  python download_rtmpose.py")
            print()
            raise FileNotFoundError(f"Model files not found in {models_dir}/")

        print(f"Loading RTMPose-M on {device}...")
        self.model = init_model(str(config), str(checkpoint), device=device)
        self.device = device
        print("✓ RTMPose-M loaded successfully!")

        # COCO skeleton connections for visualization
        self.skeleton = [
            (5, 7), (7, 9),      # Left arm
            (6, 8), (8, 10),     # Right arm
            (11, 13), (13, 15),  # Left leg
            (12, 14), (14, 16),  # Right leg
            (5, 6),              # Shoulders
            (5, 11), (6, 12),    # Torso
            (11, 12)             # Hips
        ]

        # Keypoint names (COCO format)
        self.keypoint_names = [
            'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
            'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
            'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
            'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
        ]

    def predict(self, frame):
        """
        Predict keypoints for a single frame

        Args:
            frame: BGR image from cv2

        Returns:
            keypoints: Nx3 array (x, y, confidence)
        """
        h, w = frame.shape[:2]
        bbox = np.array([[0, 0, w, h]])

        try:
            results = inference_topdown(self.model, frame, bbox)

            if len(results) > 0:
                keypoints = results[0].pred_instances.keypoints[0]
                scores = results[0].pred_instances.keypoint_scores[0]
                return np.column_stack([keypoints, scores])
        except Exception as e:
            print(f"Prediction error: {e}")

        return np.zeros((17, 3))

    def draw_skeleton(self, frame, keypoints, confidence_threshold=0.3):
        """
        Draw skeleton on frame

        Args:
            frame: BGR image
            keypoints: Nx3 array (x, y, confidence)
            confidence_threshold: Minimum confidence to draw
        """
        # Draw keypoints
        for i, (x, y, conf) in enumerate(keypoints):
            if conf > confidence_threshold:
                color = (0, 255, 0) if i < 11 else (255, 0, 0)  # Green for upper, blue for lower
                cv2.circle(frame, (int(x), int(y)), 4, color, -1)

        # Draw skeleton connections
        for i, j in self.skeleton:
            if keypoints[i][2] > confidence_threshold and keypoints[j][2] > confidence_threshold:
                pt1 = (int(keypoints[i][0]), int(keypoints[i][1]))
                pt2 = (int(keypoints[j][0]), int(keypoints[j][1]))
                cv2.line(frame, pt1, pt2, (0, 255, 255), 2)

        return frame


def run_demo(camera_id=0, show_fps=True):
    """
    Run real-time pose estimation demo

    Args:
        camera_id: Camera device ID (0 for default webcam)
        show_fps: Whether to display FPS counter
    """
    # Initialize pose estimator
    print("Initializing pose estimator...")
    estimator = RTMPoseEstimator(device='mps')
    print("✓ Model loaded successfully!\n")

    # Open camera
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"Error: Cannot open camera {camera_id}")
        print("\nTroubleshooting:")
        print("1. Check camera permissions in System Preferences > Security & Privacy > Camera")
        print("2. Try a different camera ID (run with: python minimal_pose_demo.py 1)")
        return

    # Use 640x480 for better FPS (can change to 1280x720 if needed)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("=== RTMPose Demo ===")
    print("Press 'q' to quit")
    print("Press 's' to save current frame")
    print("Starting capture...\n")

    # FPS calculation
    fps = 0
    frame_count = 0
    import time
    start_time = time.time()

    # Pre-allocate display window for better performance
    cv2.namedWindow('RTMPose Demo', cv2.WINDOW_NORMAL)

    while True:
        loop_start = time.time()

        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Predict keypoints
        keypoints = estimator.predict(frame)

        # Draw skeleton (in-place to avoid copy)
        estimator.draw_skeleton(frame, keypoints)

        # Calculate FPS (based on actual processing time, not display)
        frame_count += 1
        if frame_count % 10 == 0:
            end_time = time.time()
            fps = 10 / (end_time - start_time)
            start_time = end_time

        # Display FPS
        if show_fps:
            cv2.putText(frame, f'FPS: {fps:.1f}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Show frame (non-blocking)
        cv2.imshow('RTMPose Demo', frame)

        # Handle keys
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            filename = f'pose_capture_{int(time.time())}.jpg'
            cv2.imwrite(filename, frame)
            print(f"Saved: {filename}")

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()

    print(f"\nAverage FPS: {fps:.1f}")
    print("Demo completed!")


if __name__ == "__main__":
    import sys

    # Allow specifying camera ID from command line
    camera_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    run_demo(camera_id=camera_id)
