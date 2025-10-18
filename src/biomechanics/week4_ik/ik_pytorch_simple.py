"""
Week 4-5: Inverse Kinematics (PyTorch Implementation)
Simplified analytical IK for lower body using geometric relationships

Success Criteria:
- Joint angles computed for every frame
- Angles look reasonable (hip: 0-120°, knee: 0-140°)
- Smooth tracking without jitter
"""

import torch
import numpy as np
import cv2


class SimpleLowerBodyIK:
    """
    Simplified analytical IK for lower body
    Uses geometric relationships for speed
    """

    def __init__(self, device='mps'):
        """
        Initialize IK solver

        Args:
            device: 'mps', 'cuda', or 'cpu'
        """
        self.device = device

        # Anthropometric parameters (adjust to subject)
        # These are average proportions - can be calibrated per subject
        self.femur_length = 0.4  # meters
        self.tibia_length = 0.4  # meters
        self.pelvis_width = 0.2  # meters

    def solve(self, keypoints_3d):
        """
        Solve IK from 3D keypoints

        Args:
            keypoints_3d: 17x3 array (COCO format) [x, y, z] in meters

        Returns:
            dict of joint angles in degrees
        """
        if len(keypoints_3d) < 17:
            return {}

        # Extract key points (COCO format indices)
        left_hip = keypoints_3d[11]
        left_knee = keypoints_3d[13]
        left_ankle = keypoints_3d[15]

        right_hip = keypoints_3d[12]
        right_knee = keypoints_3d[14]
        right_ankle = keypoints_3d[16]

        left_shoulder = keypoints_3d[5]
        right_shoulder = keypoints_3d[6]

        # Compute angles
        angles = {
            # Left leg
            'hip_flexion_l': self._compute_hip_flexion(left_hip, left_knee, left_ankle),
            'knee_angle_l': self._compute_knee_angle(left_hip, left_knee, left_ankle),
            'ankle_angle_l': self._compute_ankle_angle(left_knee, left_ankle),

            # Right leg
            'hip_flexion_r': self._compute_hip_flexion(right_hip, right_knee, right_ankle),
            'knee_angle_r': self._compute_knee_angle(right_hip, right_knee, right_ankle),
            'ankle_angle_r': self._compute_ankle_angle(right_knee, right_ankle),

            # Trunk
            'trunk_lean': self._compute_trunk_lean(left_hip, right_hip, left_shoulder, right_shoulder),
        }

        return angles

    def _compute_hip_flexion(self, hip, knee, ankle):
        """
        Compute hip flexion angle from 3D points

        Args:
            hip, knee, ankle: 3D points

        Returns:
            angle in degrees (0 = standing straight, positive = flexion)
        """
        # Vector from hip to knee
        thigh_vector = knee - hip

        # Vertical reference (negative y is up in camera coords)
        vertical = np.array([0, -1, 0])

        # Angle between thigh and vertical
        cos_angle = np.dot(thigh_vector, vertical) / (
            np.linalg.norm(thigh_vector) * np.linalg.norm(vertical) + 1e-8
        )
        angle = np.arccos(np.clip(cos_angle, -1, 1))

        return np.rad2deg(angle)

    def _compute_knee_angle(self, hip, knee, ankle):
        """
        Compute knee angle from 3D points

        Args:
            hip, knee, ankle: 3D points

        Returns:
            angle in degrees (0 = fully extended, 140 = fully flexed)
        """
        # Vectors
        thigh = knee - hip
        shank = ankle - knee

        # Normalize
        thigh_norm = thigh / (np.linalg.norm(thigh) + 1e-8)
        shank_norm = shank / (np.linalg.norm(shank) + 1e-8)

        # Angle between thigh and shank
        cos_angle = np.dot(thigh_norm, shank_norm)
        angle = np.arccos(np.clip(cos_angle, -1, 1))

        # Knee angle is 180 - internal angle
        knee_angle = 180 - np.rad2deg(angle)

        return knee_angle

    def _compute_ankle_angle(self, knee, ankle):
        """
        Compute ankle angle (dorsiflexion/plantarflexion)

        Args:
            knee, ankle: 3D points

        Returns:
            angle in degrees (90 = neutral, >90 = dorsiflexion, <90 = plantarflexion)
        """
        # Simplified: assume foot is on ground, measure shank angle
        shank = ankle - knee
        vertical = np.array([0, -1, 0])

        cos_angle = np.dot(shank, vertical) / (np.linalg.norm(shank) + 1e-8)
        angle = np.arccos(np.clip(cos_angle, -1, 1))

        return np.rad2deg(angle)

    def _compute_trunk_lean(self, left_hip, right_hip, left_shoulder, right_shoulder):
        """
        Compute trunk lean angle

        Args:
            left_hip, right_hip, left_shoulder, right_shoulder: 3D points

        Returns:
            angle in degrees (0 = upright, positive = forward lean)
        """
        # Midpoints
        hip_mid = (left_hip + right_hip) / 2
        shoulder_mid = (left_shoulder + right_shoulder) / 2

        # Trunk vector
        trunk = shoulder_mid - hip_mid

        # Vertical reference
        vertical = np.array([0, -1, 0])

        # Angle
        cos_angle = np.dot(trunk, vertical) / (np.linalg.norm(trunk) + 1e-8)
        angle = np.arccos(np.clip(cos_angle, -1, 1))

        return np.rad2deg(angle)


class OpenSimIKSolver:
    """
    OpenSim IK solver wrapper
    NOTE: Requires opensim-core installation
    """

    def __init__(self, model_file='models/gait2392_simbody.osim'):
        """
        Initialize OpenSim IK solver

        Args:
            model_file: Path to OpenSim model file
        """
        try:
            import opensim as osim

            self.model = osim.Model(model_file)
            self.state = self.model.initSystem()

            # Create IK tool
            self.ik_tool = osim.InverseKinematicsTool()
            self.ik_tool.setModel(self.model)

            print(f"OpenSim IK initialized with model: {model_file}")

        except ImportError:
            raise ImportError(
                "OpenSim not installed. Install with: conda install -c opensim-org opensim"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenSim: {e}")

    def solve_frame(self, marker_positions):
        """
        Solve IK for one frame

        Args:
            marker_positions: dict of {'marker_name': [x, y, z]}

        Returns:
            dict of {'joint_name': angle_in_degrees}
        """
        import opensim as osim

        # Create marker data for this frame
        marker_data = osim.MarkerData()
        marker_data.setNumFrames(1)

        for marker_name, pos in marker_positions.items():
            marker_data.addMarker(marker_name)
            marker_data.setMarkerValue(0, marker_name, osim.Vec3(pos[0], pos[1], pos[2]))

        # Write temporary marker file
        temp_file = 'temp_markers.trc'
        marker_data.writeToFile(temp_file)

        # Set up IK problem
        self.ik_tool.setMarkerDataFileName(temp_file)

        # Solve
        self.ik_tool.run()

        # Extract joint angles
        joint_angles = {}
        for i in range(self.model.getCoordinateSet().getSize()):
            coord = self.model.getCoordinateSet().get(i)
            joint_angles[coord.getName()] = np.rad2deg(coord.getValue(self.state))

        return joint_angles


def demo_ik_visualization():
    """
    Demo: Visualize IK results in real-time
    """
    import sys
    import os

    # Add paths
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'week1_pose'))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'week2_stereo'))

    from minimal_pose_demo import RTMPoseEstimator
    from stereo_triangulation import DualCameraCapture, StereoReconstructor

    print("\n=== IK Visualization Demo ===")
    print("Press 'q' to quit\n")

    # Initialize
    pose_model = RTMPoseEstimator(device='mps')
    calib_path = os.path.join(os.path.dirname(__file__), '..', 'week2_stereo', 'stereo_calibration.npz')
    stereo = StereoReconstructor(calibration_file=calib_path)
    cameras = DualCameraCapture(cam0_id=0, cam1_id=2)
    ik_solver = SimpleLowerBodyIK()

    import time
    fps = 0
    frame_count = 0
    start_time = time.time()

    # Storage for smoothing
    from collections import deque
    angle_history = {key: deque(maxlen=5) for key in [
        'hip_flexion_l', 'knee_angle_l', 'hip_flexion_r', 'knee_angle_r'
    ]}

    while True:
        frame0, frame1 = cameras.capture_synchronized()
        if frame0 is None:
            break

        # Always create a visualization frame
        frame_vis = frame0.copy()

        # Get 2D poses
        kpts0 = pose_model.predict(frame0)
        kpts1 = pose_model.predict(frame1)

        # Debug info
        cv2.putText(frame_vis, f'Cam0 kpts: {kpts0.shape[0]}', (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame_vis, f'Cam2 kpts: {kpts1.shape[0]}', (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Triangulate 3D
        if kpts0.shape[0] == kpts1.shape[0] and kpts0.shape[0] > 0:
            confidences = np.stack([kpts0[:, 2], kpts1[:, 2]], axis=1)
            points_3d = stereo.triangulate_points(kpts0[:, :2], kpts1[:, :2], confidences)

            cv2.putText(frame_vis, f'3D points: {len(points_3d)}', (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Solve IK
            if len(points_3d) >= 17:
                joint_angles = ik_solver.solve(points_3d)

                # Smooth angles
                for key in angle_history.keys():
                    if key in joint_angles:
                        angle_history[key].append(joint_angles[key])
                        joint_angles[key] = np.mean(angle_history[key])

                # Display angles
                y_offset = 120
                for i, (name, angle) in enumerate(joint_angles.items()):
                    text = f"{name}: {angle:.1f}°"
                    cv2.putText(frame_vis, text, (10, y_offset + i*25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # Draw angle bars
                x_bar = frame_vis.shape[1] - 200
                for i, (name, angle) in enumerate(joint_angles.items()):
                    # Normalize to 0-180 range
                    bar_length = int((angle / 180.0) * 150)
                    y_bar = 50 + i * 30

                    # Background bar
                    cv2.rectangle(frame_vis, (x_bar, y_bar), (x_bar + 150, y_bar + 20),
                                 (50, 50, 50), -1)

                    # Angle bar (green to red gradient)
                    color = (0, int(255 * (1 - angle/180)), int(255 * angle/180))
                    cv2.rectangle(frame_vis, (x_bar, y_bar), (x_bar + bar_length, y_bar + 20),
                                 color, -1)
            else:
                cv2.putText(frame_vis, 'Waiting for full body detection...', (10, 120),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            cv2.putText(frame_vis, 'Keypoint count mismatch or no detection', (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # FPS
        frame_count += 1
        if frame_count % 10 == 0:
            fps = 10 / (time.time() - start_time)
            start_time = time.time()

        cv2.putText(frame_vis, f'FPS: {fps:.1f}', (10, frame_vis.shape[0] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        cv2.imshow('IK Visualization', frame_vis)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cameras.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    # Example usage
    print("Simple Lower Body IK Solver")
    print("\nExample: Compute joint angles from 3D keypoints")

    # Dummy 3D keypoints (standing pose)
    keypoints_3d = np.array([
        [0.0, 0.0, 1.5],   # 0: nose
        [-0.05, 0.02, 1.5], # 1: left eye
        [0.05, 0.02, 1.5],  # 2: right eye
        [-0.1, 0.0, 1.5],   # 3: left ear
        [0.1, 0.0, 1.5],    # 4: right ear
        [-0.2, -0.2, 1.3],  # 5: left shoulder
        [0.2, -0.2, 1.3],   # 6: right shoulder
        [-0.25, -0.2, 1.0], # 7: left elbow
        [0.25, -0.2, 1.0],  # 8: right elbow
        [-0.3, -0.2, 0.8],  # 9: left wrist
        [0.3, -0.2, 0.8],   # 10: right wrist
        [-0.15, -0.2, 0.9], # 11: left hip
        [0.15, -0.2, 0.9],  # 12: right hip
        [-0.15, -0.2, 0.5], # 13: left knee
        [0.15, -0.2, 0.5],  # 14: right knee
        [-0.15, -0.2, 0.1], # 15: left ankle
        [0.15, -0.2, 0.1],  # 16: right ankle
    ])

    ik = SimpleLowerBodyIK()
    angles = ik.solve(keypoints_3d)

    print("\nComputed Joint Angles:")
    for name, angle in angles.items():
        print(f"  {name}: {angle:.1f}°")

    # Run demo if cameras available
    response = input("\nRun live demo with stereo cameras? (y/n): ")
    if response.lower() == 'y':
        demo_ik_visualization()
