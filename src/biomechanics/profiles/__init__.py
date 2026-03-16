"""
Exercise Profiles

Modular exercise-specific configuration for the biomechanics pipeline.
Each profile bundles fault rules, rep signal, cues, and calibration
for a specific exercise or movement pattern.
"""

from biomechanics.profiles.base import ExerciseProfile
from biomechanics.profiles.registry import get_profile, register_profile, PROFILE_REGISTRY

# Import profile modules to trigger @register_profile decorators
import biomechanics.profiles.squat  # noqa: F401

__all__ = [
    "ExerciseProfile",
    "get_profile",
    "register_profile",
    "PROFILE_REGISTRY",
]
