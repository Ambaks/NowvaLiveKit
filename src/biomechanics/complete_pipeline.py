"""
Complete Biomechanics Pipeline
Integrates all components for real-time muscle force estimation

Pipeline:
1. Pose Estimation (RTMPose) - 2D keypoints from stereo cameras
2. 3D Reconstruction (Triangulation) - 3D keypoints
3. Inverse Kinematics - Joint angles from 3D keypoints
4. Muscle Force Prediction (Neural Network) - Forces from kinematics

Success Criteria:
- Real-time operation (>20 FPS)
- Accurate joint angles (< 5° error)
- Plausible muscle forces
"""

import cv2
import torch
import numpy as np
import time
from collections import deque
import sys
import os

# Add module paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'week1_pose'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'week2_stereo'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'week4_ik'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'week8_ml'))

from minimal_pose_demo import RTMPoseEstimator
from stereo_triangulation import DualCameraCapture, StereoReconstructor
from ik_pytorch_simple import SimpleLowerBodyIK
from train_muscle_predictor import load_trained_model


class CompleteBiomechanicsPipeline:
    """Complete real-time biomechanics analysis pipeline"""

    def __init__(
        self,
        muscle_model_path='muscle_predictor_best.pt',
        calibration_file='stereo_calibration.npz',
        device='mps',
        smoothing_window=5
    ):
        """
        Initialize complete pipeline

        Args:
            muscle_model_path: Path to trained muscle force predictor
            calibration_file: Path to camera calibration
            device: 'mps', 'cuda', or 'cpu'
            smoothing_window: Window size for temporal smoothing
        """
        print("\n" + "="*70)
        print("Initializing Complete Biomechanics Pipeline")
        print("="*70 + "\n")

        self.device = device

        # 1. Pose Estimation
        print("Loading pose estimator...")
        self.pose_estimator = RTMPoseEstimator(device=device)

        # 2. Stereo Reconstruction
        print("Loading stereo reconstructor...")
        self.stereo = StereoReconstructor(calibration_file=calibration_file)

        # 3. Inverse Kinematics
        print("Loading IK solver...")
        self.ik_solver = SimpleLowerBodyIK()

        # 4. Muscle Force Predictor
        print("Loading muscle force predictor...")
        if os.path.exists(muscle_model_path):
            self.muscle_model = load_trained_model(muscle_model_path, device=device)
            self.muscle_predictor_available = True
        else:
            print(f"  ⚠ Model not found: {muscle_model_path}")
            print(f"  Muscle force prediction will be disabled")
            self.muscle_predictor_available = False

        # Performance tracking
        self.fps = 0
        self.frame_times = deque(maxlen=30)

        # Smoothing
        self.smoothing_window = smoothing_window
        self.angle_history = {}
        self.force_history = {}

        print("\n✓ Pipeline initialized successfully\n")

    def process_frame(self, frame0, frame1):
        """
        Process one pair of stereo frames

        Args:
            frame0: Frame from camera 0
            frame1: Frame from camera 1

        Returns:
            dict with results
        """
        start_time = time.time()

        results = {
            'joint_angles': {},
            'muscle_forces': None,
            'points_3d': None,
            'keypoints_2d': {'cam0': None, 'cam1': None},
            'fps': 0,
            'success': False
        }

        try:
            # Step 1: Pose estimation (both views)
            kpts0 = self.pose_estimator.predict(frame0)
            kpts1 = self.pose_estimator.predict(frame1)

            results['keypoints_2d']['cam0'] = kpts0
            results['keypoints_2d']['cam1'] = kpts1

            # Step 2: 3D reconstruction
            if kpts0.shape[0] == kpts1.shape[0] and kpts0.shape[0] >= 17:
                confidences = np.stack([kpts0[:, 2], kpts1[:, 2]], axis=1)
                points_3d = self.stereo.triangulate_points(
                    kpts0[:, :2],
                    kpts1[:, :2],
                    confidences,
                    threshold=0.3
                )

                results['points_3d'] = points_3d

                # Step 3: Inverse kinematics
                if len(points_3d) >= 17:
                    joint_angles = self.ik_solver.solve(points_3d)

                    # Smooth angles
                    joint_angles = self._smooth_angles(joint_angles)
                    results['joint_angles'] = joint_angles

                    # Step 4: Muscle force prediction
                    if self.muscle_predictor_available:
                        muscle_forces = self._predict_muscle_forces(joint_angles)

                        # Smooth forces
                        muscle_forces = self._smooth_forces(muscle_forces)
                        results['muscle_forces'] = muscle_forces

                    results['success'] = True

        except Exception as e:
            print(f"Error processing frame: {e}")

        # Calculate FPS
        elapsed = time.time() - start_time
        self.frame_times.append(elapsed)
        self.fps = 1.0 / np.mean(self.frame_times)
        results['fps'] = self.fps

        return results

    def _smooth_angles(self, angles):
        """Apply temporal smoothing to joint angles"""
        smoothed = {}

        for name, value in angles.items():
            if name not in self.angle_history:
                self.angle_history[name] = deque(maxlen=self.smoothing_window)

            self.angle_history[name].append(value)
            smoothed[name] = np.mean(self.angle_history[name])

        return smoothed

    def _smooth_forces(self, forces):
        """Apply temporal smoothing to muscle forces"""
        if forces is None:
            return None

        # Create key for force vector
        key = 'forces'

        if key not in self.force_history:
            self.force_history[key] = deque(maxlen=self.smoothing_window)

        self.force_history[key].append(forces)
        smoothed = np.mean(self.force_history[key], axis=0)

        return smoothed

    def _predict_muscle_forces(self, joint_angles):
        """
        Predict muscle forces from joint angles

        Args:
            joint_angles: Dict of joint angles

        Returns:
            numpy array of muscle forces
        """
        # Prepare input tensor
        # TODO: Include velocities and accelerations
        kinematics = []

        # Extract angles in consistent order
        angle_keys = [
            'hip_flexion_l', 'knee_angle_l', 'ankle_angle_l',
            'hip_flexion_r', 'knee_angle_r', 'ankle_angle_r'
        ]

        for key in angle_keys:
            kinematics.append(joint_angles.get(key, 0.0))

        # Add velocities and accelerations (placeholder - compute from history)
        kinematics.extend([0.0] * len(angle_keys))  # Velocities
        kinematics.extend([0.0] * len(angle_keys))  # Accelerations

        # Convert to tensor
        kinematics_tensor = torch.tensor(kinematics, dtype=torch.float32).unsqueeze(0).to(self.device)

        # Predict
        with torch.no_grad():
            muscle_forces = self.muscle_model(kinematics_tensor)

        return muscle_forces.cpu().numpy()[0]


def visualize_results(frame, results, show_angles=True, show_forces=True):
    """
    Visualize pipeline results on frame

    Args:
        frame: Input frame
        results: Results dict from pipeline
        show_angles: Whether to show joint angles
        show_forces: Whether to show muscle forces

    Returns:
        Annotated frame
    """
    vis = frame.copy()
    y_offset = 30

    # FPS
    cv2.putText(vis, f'FPS: {results["fps"]:.1f}', (10, y_offset),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    y_offset += 30

    # Status
    if results['success']:
        status_text = "✓ Tracking"
        status_color = (0, 255, 0)
    else:
        status_text = "✗ No detection"
        status_color = (0, 0, 255)

    cv2.putText(vis, status_text, (10, y_offset),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
    y_offset += 40

    # Joint angles
    if show_angles and results['joint_angles']:
        cv2.putText(vis, "Joint Angles:", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_offset += 25

        for name, angle in results['joint_angles'].items():
            text = f"  {name}: {angle:.1f}°"
            cv2.putText(vis, text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_offset += 20

    # Muscle forces
    if show_forces and results['muscle_forces'] is not None:
        y_offset += 10
        cv2.putText(vis, "Muscle Forces (N):", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_offset += 25

        forces = results['muscle_forces']
        for i, force in enumerate(forces[:5]):  # Show first 5
            text = f"  Muscle {i+1}: {force:.1f}N"
            cv2.putText(vis, text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_offset += 20

    return vis


def run_complete_pipeline(
    cam0_id=0,
    cam1_id=1,
    muscle_model_path='muscle_predictor_best.pt',
    calibration_file='stereo_calibration.npz'
):
    """
    Run complete biomechanics pipeline

    Args:
        cam0_id: Camera 0 device ID
        cam1_id: Camera 1 device ID
        muscle_model_path: Path to trained muscle predictor
        calibration_file: Path to camera calibration
    """
    print("\n" + "="*70)
    print("Complete Biomechanics Pipeline - Real-time Demo")
    print("="*70)
    print("\nControls:")
    print("  q - Quit")
    print("  s - Save current data")
    print("  a - Toggle angle display")
    print("  f - Toggle force display")
    print("\n")

    # Initialize pipeline
    pipeline = CompleteBiomechanicsPipeline(
        muscle_model_path=muscle_model_path,
        calibration_file=calibration_file
    )

    # Initialize cameras
    cameras = DualCameraCapture(cam0_id=cam0_id, cam1_id=cam1_id)

    # Display options
    show_angles = True
    show_forces = True

    print("Starting capture... Press 'q' to quit\n")

    while True:
        # Capture frames
        frame0, frame1 = cameras.capture_synchronized()
        if frame0 is None:
            print("Failed to capture frames")
            break

        # Process through pipeline
        results = pipeline.process_frame(frame0, frame1)

        # Visualize
        vis0 = visualize_results(frame0, results, show_angles, show_forces)
        vis1 = visualize_results(frame1, results, False, False)

        # Combine views
        combined = np.hstack([vis0, vis1])

        # Add separator
        h, w = combined.shape[:2]
        cv2.line(combined, (w//2, 0), (w//2, h), (255, 255, 255), 2)

        # Display
        cv2.imshow('Complete Biomechanics Pipeline', combined)

        # Handle keys
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            # Save current data
            timestamp = int(time.time())
            filename = f'biomech_data_{timestamp}.npz'

            np.savez(filename,
                    joint_angles=results['joint_angles'],
                    muscle_forces=results['muscle_forces'],
                    points_3d=results['points_3d'])

            print(f"Saved data to {filename}")

        elif key == ord('a'):
            show_angles = not show_angles
            print(f"Angle display: {'ON' if show_angles else 'OFF'}")

        elif key == ord('f'):
            show_forces = not show_forces
            print(f"Force display: {'ON' if show_forces else 'OFF'}")

    # Cleanup
    cameras.release()
    cv2.destroyAllWindows()

    print(f"\nAverage FPS: {pipeline.fps:.1f}")
    print("Pipeline completed!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Complete Biomechanics Pipeline')
    parser.add_argument('--cam0', type=int, default=0,
                       help='Camera 0 device ID')
    parser.add_argument('--cam1', type=int, default=1,
                       help='Camera 1 device ID')
    parser.add_argument('--model', type=str, default='muscle_predictor_best.pt',
                       help='Path to muscle force predictor')
    parser.add_argument('--calibration', type=str, default='stereo_calibration.npz',
                       help='Path to camera calibration')

    args = parser.parse_args()

    run_complete_pipeline(
        cam0_id=args.cam0,
        cam1_id=args.cam1,
        muscle_model_path=args.model,
        calibration_file=args.calibration
    )
