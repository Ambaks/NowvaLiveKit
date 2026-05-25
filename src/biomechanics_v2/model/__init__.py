"""MuJoCo skeleton model generation and anthropometric scaling."""

from .skeleton_model import MujocoSkeleton
from .anthropometry import build_mjcf_xml, scale_mjcf_from_proportions

__all__ = ["MujocoSkeleton", "build_mjcf_xml", "scale_mjcf_from_proportions"]
