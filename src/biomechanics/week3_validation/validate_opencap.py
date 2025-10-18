"""
Week 3: OpenCap Data Validation
Validate your pipeline against OpenCap ground truth

Success Criteria:
- RMSE < 5° for major joint angles
- Visual comparison matches ground truth
- Pipeline runs without crashes
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import cv2
import os
import sys


def download_opencap_instructions():
    """Print instructions for downloading OpenCap data"""
    print("="*70)
    print("OpenCap Dataset Download Instructions")
    print("="*70)
    print("\n1. Visit: https://www.opencap.ai/")
    print("   Or: https://simtk.org/projects/opencap")
    print("\n2. Download example sessions (look for 'Example Data' or 'Sample Data')")
    print("\n3. Save to: data/opencap_samples/")
    print("\n4. Expected structure:")
    print("   data/opencap_samples/")
    print("     ├── session_001/")
    print("     │   ├── Videos/")
    print("     │   │   ├── Cam0.mp4")
    print("     │   │   └── Cam1.mp4")
    print("     │   ├── MarkerData/")
    print("     │   │   └── markers.trc")
    print("     │   └── OpenSimData/")
    print("     │       ├── Kinematics/")
    print("     │       │   └── kinematics.mot")
    print("     │       └── Kinetics/")
    print("\n5. Run this script again after downloading")
    print("="*70)


def load_trc_file(filepath):
    """
    Load OpenCap marker data (TRC format)

    Args:
        filepath: Path to .trc file

    Returns:
        DataFrame with marker positions
    """
    try:
        # TRC format has metadata in first few rows
        with open(filepath, 'r') as f:
            lines = f.readlines()

        # Find data start (after header rows)
        data_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('Frame#'):
                data_start = i + 1
                break

        # Read data
        data = pd.read_csv(filepath, sep='\t', skiprows=data_start)
        return data

    except Exception as e:
        print(f"Error loading TRC file: {e}")
        return None


def load_mot_file(filepath):
    """
    Load OpenSim kinematics/kinetics data (MOT format)

    Args:
        filepath: Path to .mot file

    Returns:
        DataFrame with joint angles/forces
    """
    try:
        # MOT format has metadata in first rows
        with open(filepath, 'r') as f:
            lines = f.readlines()

        # Find data start
        data_start = 0
        for i, line in enumerate(lines):
            if 'endheader' in line.lower():
                data_start = i + 1
                break

        # Read data
        data = pd.read_csv(filepath, sep='\t', skiprows=data_start)
        return data

    except Exception as e:
        print(f"Error loading MOT file: {e}")
        return None


class OpenCapSession:
    """OpenCap session data loader"""

    def __init__(self, session_path):
        """
        Load OpenCap session

        Args:
            session_path: Path to session folder
        """
        self.session_path = session_path
        self.markers = None
        self.kinematics = None
        self.video_files = []

        self._load_session()

    def _load_session(self):
        """Load all session data"""
        # Load marker data
        marker_file = os.path.join(self.session_path, 'MarkerData', 'markers.trc')
        if os.path.exists(marker_file):
            self.markers = load_trc_file(marker_file)
            print(f"✓ Loaded markers: {marker_file}")
        else:
            print(f"✗ Marker file not found: {marker_file}")

        # Load kinematics
        kinematics_file = os.path.join(self.session_path, 'OpenSimData', 'Kinematics', 'kinematics.mot')
        if os.path.exists(kinematics_file):
            self.kinematics = load_mot_file(kinematics_file)
            print(f"✓ Loaded kinematics: {kinematics_file}")
        else:
            print(f"✗ Kinematics file not found: {kinematics_file}")

        # Find video files
        video_dir = os.path.join(self.session_path, 'Videos')
        if os.path.exists(video_dir):
            for file in os.listdir(video_dir):
                if file.endswith(('.mp4', '.avi', '.mov')):
                    self.video_files.append(os.path.join(video_dir, file))
            print(f"✓ Found {len(self.video_files)} video files")
        else:
            print(f"✗ Video directory not found: {video_dir}")

    def get_joint_angle_timeseries(self, joint_name):
        """
        Get time series for a specific joint angle

        Args:
            joint_name: Name of joint (e.g., 'knee_angle_r')

        Returns:
            numpy array of angles over time
        """
        if self.kinematics is None:
            return None

        if joint_name in self.kinematics.columns:
            return self.kinematics[joint_name].values
        else:
            print(f"Joint '{joint_name}' not found. Available joints:")
            print(self.kinematics.columns.tolist())
            return None


def run_pipeline_on_opencap(session_path, output_file='validation_results.png'):
    """
    Run your pipeline on OpenCap data and compare to ground truth

    Args:
        session_path: Path to OpenCap session
        output_file: Where to save validation plot
    """
    # Load OpenCap session
    session = OpenCapSession(session_path)

    if session.kinematics is None:
        print("Cannot validate without kinematics data")
        return

    # Get ground truth joint angles
    # Common joint names in OpenCap: knee_angle_r, knee_angle_l, hip_flexion_r, hip_flexion_l
    joints_to_validate = ['knee_angle_r', 'knee_angle_l', 'hip_flexion_r', 'hip_flexion_l']

    print(f"\n{'='*70}")
    print("Running Pipeline on OpenCap Data")
    print(f"{'='*70}\n")

    # TODO: Run your pipeline on the videos
    # For now, we'll create a placeholder comparison

    # Storage for comparison
    results = {}

    for joint_name in joints_to_validate:
        gt_angles = session.get_joint_angle_timeseries(joint_name)

        if gt_angles is not None:
            # TODO: Replace with your pipeline's predictions
            # For now, add some noise to ground truth as example
            predicted_angles = gt_angles + np.random.normal(0, 2, len(gt_angles))

            # Calculate metrics
            rmse = np.sqrt(np.mean((predicted_angles - gt_angles)**2))
            mae = np.mean(np.abs(predicted_angles - gt_angles))
            correlation = np.corrcoef(predicted_angles, gt_angles)[0, 1]

            results[joint_name] = {
                'ground_truth': gt_angles,
                'predicted': predicted_angles,
                'rmse': rmse,
                'mae': mae,
                'correlation': correlation
            }

            print(f"{joint_name}:")
            print(f"  RMSE: {rmse:.2f}°")
            print(f"  MAE: {mae:.2f}°")
            print(f"  Correlation: {correlation:.3f}")

            # Assessment
            if rmse < 5.0:
                print(f"  ✅ Excellent! Within clinical threshold")
            elif rmse < 10.0:
                print(f"  ✓ Good! Acceptable for most applications")
            else:
                print(f"  ⚠ Needs improvement")
            print()

    # Plot results
    plot_validation_results(results, output_file)

    return results


def plot_validation_results(results, output_file):
    """
    Plot validation results

    Args:
        results: Dict of validation results
        output_file: Where to save plot
    """
    n_joints = len(results)
    fig, axes = plt.subplots(n_joints, 1, figsize=(12, 4*n_joints))

    if n_joints == 1:
        axes = [axes]

    for i, (joint_name, data) in enumerate(results.items()):
        ax = axes[i]

        # Plot ground truth and predicted
        frames = np.arange(len(data['ground_truth']))
        ax.plot(frames, data['ground_truth'], label='OpenCap Ground Truth',
               linewidth=2, color='blue')
        ax.plot(frames, data['predicted'], label='Your Pipeline',
               linestyle='--', linewidth=2, color='red', alpha=0.7)

        # Add error band
        error = np.abs(data['predicted'] - data['ground_truth'])
        ax.fill_between(frames, data['ground_truth'] - error, data['ground_truth'] + error,
                        alpha=0.2, color='red')

        # Labels
        ax.set_xlabel('Frame', fontsize=12)
        ax.set_ylabel('Angle (degrees)', fontsize=12)
        ax.set_title(f"{joint_name} - RMSE: {data['rmse']:.2f}°, Correlation: {data['correlation']:.3f}",
                    fontsize=14, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n✓ Validation plot saved to {output_file}")
    plt.show()


def integrate_with_your_pipeline(session):
    """
    Template for integrating OpenCap validation with your pipeline

    Args:
        session: OpenCapSession object

    Returns:
        dict of predicted joint angles
    """
    # Add your pipeline imports here
    # sys.path.insert(0, ...)
    # from week1_pose.minimal_pose_demo import RTMPoseEstimator
    # from week2_stereo.stereo_triangulation import StereoReconstructor
    # from week4_ik.ik_pytorch_simple import SimpleLowerBodyIK

    print("TODO: Integrate your pipeline here")
    print("Steps:")
    print("1. Load videos from session.video_files")
    print("2. Run pose estimation on each frame")
    print("3. Triangulate 3D points")
    print("4. Solve IK to get joint angles")
    print("5. Return predicted angles for comparison")

    # Example structure:
    """
    predicted_angles = {
        'knee_angle_r': [],
        'knee_angle_l': [],
        'hip_flexion_r': [],
        'hip_flexion_l': []
    }

    for frame_idx in range(num_frames):
        # Get frames from videos
        # Run pose estimation
        # Triangulate
        # Solve IK
        # Store angles
        pass

    return predicted_angles
    """
    return {}


if __name__ == "__main__":
    # Check if OpenCap data exists
    data_dir = 'data/opencap_samples'

    if not os.path.exists(data_dir):
        print("\n⚠ OpenCap data not found!")
        download_opencap_instructions()
        sys.exit(0)

    # Find sessions
    sessions = [d for d in os.listdir(data_dir)
                if os.path.isdir(os.path.join(data_dir, d))]

    if len(sessions) == 0:
        print("\n⚠ No sessions found in data/opencap_samples/")
        download_opencap_instructions()
        sys.exit(0)

    print(f"\nFound {len(sessions)} OpenCap session(s):")
    for i, session in enumerate(sessions):
        print(f"  {i+1}. {session}")

    # Use first session
    session_path = os.path.join(data_dir, sessions[0])
    print(f"\nValidating with session: {sessions[0]}")

    # Run validation
    results = run_pipeline_on_opencap(session_path)
