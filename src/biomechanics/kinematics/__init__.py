"""
Inverse Kinematics module.

Provides solvers to compute joint angles from 3D skeleton poses:
- AnalyticalIKSolver: Lightweight geometric solver using vector math
- (Future) OpenSimIKSolver: Full musculoskeletal model-based solver
"""

from biomechanics.kinematics.base import IKSolver
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver

__all__ = [
    "IKSolver",
    "AnalyticalIKSolver",
]
