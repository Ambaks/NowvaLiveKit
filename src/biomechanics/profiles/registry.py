"""
Exercise Profile Registry

Maps exercise names and movement patterns to ExerciseProfile subclasses.
Use @register_profile("name") to register a profile, and get_profile()
to look one up by exercise name.
"""

import logging
from typing import Dict, Type

from biomechanics.profiles.base import ExerciseProfile
from biomechanics.calibration import EXERCISE_TO_MOVEMENT_PATTERN

logger = logging.getLogger(__name__)

PROFILE_REGISTRY: Dict[str, Type[ExerciseProfile]] = {}


def register_profile(*names: str):
    """Decorator to register a profile class under one or more names.

    Usage:
        @register_profile("squat", "back_squat", "front_squat")
        class SquatProfile(ExerciseProfile):
            ...
    """
    def decorator(cls: Type[ExerciseProfile]) -> Type[ExerciseProfile]:
        for name in names:
            PROFILE_REGISTRY[name] = cls
        return cls
    return decorator


def get_profile(exercise_name: str) -> ExerciseProfile:
    """Look up and instantiate a profile for the given exercise.

    Resolution order:
    1. Normalized exact match (e.g. "barbell_back_squat")
    2. Movement pattern fallback (e.g. "squat" for any squat variant)
    3. Substring match (e.g. exercise contains "squat")
    4. Default: "squat" profile

    Args:
        exercise_name: Exercise name (e.g. "Barbell Back Squat").

    Returns:
        An instantiated ExerciseProfile.
    """
    normalized = exercise_name.lower().replace(" ", "_")

    # 1. Direct match
    if normalized in PROFILE_REGISTRY:
        logger.info("[PROFILES] Matched '%s' directly", normalized)
        return PROFILE_REGISTRY[normalized]()

    # 2. Movement pattern fallback
    pattern = EXERCISE_TO_MOVEMENT_PATTERN.get(exercise_name)
    if pattern and pattern in PROFILE_REGISTRY:
        logger.info(
            "[PROFILES] Matched '%s' via movement pattern '%s'",
            exercise_name, pattern,
        )
        return PROFILE_REGISTRY[pattern]()

    # 3. Substring match
    for key, cls in PROFILE_REGISTRY.items():
        if key in normalized:
            logger.info(
                "[PROFILES] Matched '%s' via substring '%s'",
                exercise_name, key,
            )
            return cls()

    # 4. Default fallback
    if "squat" in PROFILE_REGISTRY:
        logger.warning(
            "[PROFILES] No profile for '%s' — falling back to squat",
            exercise_name,
        )
        return PROFILE_REGISTRY["squat"]()

    logger.warning(
        "[PROFILES] No profile for '%s' and no squat fallback — using base",
        exercise_name,
    )
    return ExerciseProfile()
