"""
Core Biomechanics Implementation
Real-time squat form analysis and fault detection

Main Components:
- pose: 2D pose estimation (RTMPose)
- triangulation: Multi-camera 3D reconstruction
- kinematics: Joint angle computation
- faults: Rule-based fault detection
- diagnosis: Graph-based diagnosis engine
- coaching: Cue generation from faults
- profiles: Exercise-specific configuration
"""

__version__ = "1.0.0"
__author__ = "Biomechanics Pipeline Team"

PACKAGE_NAME = "biomechanics"
DESCRIPTION = "Real-time biomechanics analysis from stereo camera input"
