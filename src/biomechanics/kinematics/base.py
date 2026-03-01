"""
Abstract base class for inverse kinematics solvers.

All IK solvers (analytical, OpenSim, etc.) must inherit from this class
and implement the solve() method.
"""

from abc import ABC, abstractmethod
from typing import Optional

from biomechanics.utils.types import Skeleton3D, JointAngles


class IKSolver(ABC):
    """
    Abstract base class for inverse kinematics.

    Converts 3D skeleton poses to joint angles.
    """

    def __init__(self):
        """Initialize IK solver."""
        self._initialized = False

    @abstractmethod
    def solve(self, skeleton: Skeleton3D) -> JointAngles:
        """
        Compute joint angles from a 3D skeleton.

        Args:
            skeleton: 3D skeleton with keypoints in world coordinates (meters)

        Returns:
            JointAngles with all computed angles in degrees
        """
        pass

    def initialize(self) -> bool:
        """
        Initialize the IK solver.

        Returns:
            True if initialization successful
        """
        self._initialized = True
        return True

    def release(self) -> None:
        """Release any resources held by the solver."""
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if solver is initialized."""
        return self._initialized
