"""
Core Biomechanics Implementation
Real-time muscle force and joint kinematics estimation

Main Components:
- week1_pose: 2D pose estimation using RTMPose
- week2_stereo: Camera calibration and 3D reconstruction
- week3_validation: Validation against OpenCap ground truth
- week4_ik: Inverse kinematics solvers
- week6_moco: Training data generation using OpenSim Moco
- week8_ml: Neural network training for muscle force prediction
- complete_pipeline: Integrated real-time pipeline

Quick Start:
    >>> from biomechanics.complete_pipeline import run_complete_pipeline
    >>> run_complete_pipeline()

See README.md and QUICKSTART.md for detailed instructions.
"""

__version__ = "1.0.0"
__author__ = "Biomechanics Pipeline Team"

# Package info
PACKAGE_NAME = "biomechanics"
DESCRIPTION = "Real-time biomechanics analysis from stereo camera input"

# Import key components for convenience
try:
    from .week1_pose.minimal_pose_demo import RTMPoseEstimator
    from .week2_stereo.stereo_triangulation import StereoReconstructor, DualCameraCapture
    from .week4_ik.ik_pytorch_simple import SimpleLowerBodyIK
    from .complete_pipeline import CompleteBiomechanicsPipeline

    __all__ = [
        'RTMPoseEstimator',
        'StereoReconstructor',
        'DualCameraCapture',
        'SimpleLowerBodyIK',
        'CompleteBiomechanicsPipeline',
    ]
except ImportError:
    # Graceful fallback if dependencies not installed
    pass
