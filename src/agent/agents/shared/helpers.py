"""
Shared helper functions extracted from the monolithic voice agent.
Used by multiple agent classes.
"""

import logging
from typing import Optional

from db.database import SessionLocal

logger = logging.getLogger(__name__)


def normalize_exercise_name(raw_name: str) -> Optional[str]:
    """Normalize a casual exercise name to its formal library name.
    Returns None if the exercise isn't supported for biomechanics tracking.
    """
    name_lower = raw_name.lower().strip()

    EXERCISE_ALIASES = {
        "squat": "Barbell Back Squat",
        "squats": "Barbell Back Squat",
        "back squat": "Barbell Back Squat",
        "back squats": "Barbell Back Squat",
        "barbell squat": "Barbell Back Squat",
        "barbell back squat": "Barbell Back Squat",
        "front squat": "Barbell Front Squat",
        "front squats": "Barbell Front Squat",
        "barbell front squat": "Barbell Front Squat",
        "goblet squat": "Goblet Squat",
        "goblet squats": "Goblet Squat",
        "deadlift": "Barbell Deadlift",
        "deadlifts": "Barbell Deadlift",
        "barbell deadlift": "Barbell Deadlift",
        "romanian deadlift": "Romanian Deadlift",
        "rdl": "Romanian Deadlift",
        "sumo deadlift": "Sumo Deadlift",
        "bench": "Barbell Bench Press",
        "bench press": "Barbell Bench Press",
        "barbell bench press": "Barbell Bench Press",
        "overhead press": "Barbell Overhead Press",
        "ohp": "Barbell Overhead Press",
        "press": "Barbell Overhead Press",
        "military press": "Barbell Overhead Press",
    }

    return EXERCISE_ALIASES.get(name_lower)


async def check_calibration(user_id: str, exercise_name: str) -> Optional[dict]:
    """Check if user has calibration data for this exercise's movement pattern.

    Returns the calibration thresholds dict if it exists, None if calibration is needed.
    """
    from biomechanics.calibration import get_movement_pattern
    from db.calibration_utils import get_user_calibration

    pattern = get_movement_pattern(exercise_name)
    if not pattern:
        return None

    db = SessionLocal()
    try:
        return get_user_calibration(db, user_id, pattern)
    finally:
        db.close()


def start_calibration_mode(state, exercise_name: str, pending_workout: dict):
    """Set state keys to trigger calibration in the pipeline subprocess."""
    from biomechanics.calibration import get_movement_pattern

    state.set("calibration.active", True)
    state.set("calibration.movement_pattern", get_movement_pattern(exercise_name))
    state.set("calibration.pending_workout", pending_workout)


def get_recommended_duration(goal_category: str) -> int:
    """Get recommended program duration based on goal category."""
    if goal_category == "power":
        return 6
    elif goal_category == "strength":
        return 10
    else:  # hypertrophy
        return 12


def normalize_fitness_level(level_str: str) -> str:
    """Normalize fitness level to beginner, intermediate, or advanced."""
    level_lower = level_str.lower()

    beginner_keywords = ["beginner", "new", "just starting", "never", "first time", "noob"]
    advanced_keywords = ["advanced", "experienced", "years", "competitive", "athlete", "expert"]

    if any(kw in level_lower for kw in beginner_keywords):
        return "beginner"
    elif any(kw in level_lower for kw in advanced_keywords):
        return "advanced"
    else:
        return "intermediate"


def should_enable_vbt(fitness_level: str, goal_category: str, specific_sport: str) -> bool:
    """Determine if VBT should be enabled based on training parameters.

    VBT is enabled when:
    1. Goal is power or athletic_performance (any fitness level)
    2. Goal is strength AND fitness level is advanced
    3. Sport involves explosiveness (intermediate or advanced)
    """
    # Rule 1: Power/athletic goals get VBT at any level
    if goal_category in ["power", "athletic_performance"]:
        if fitness_level == "beginner":
            logger.info(f"[VBT] Enabled (BASIC only): {goal_category} goal with beginner level — limited to basic power exercises")
        else:
            logger.info(f"[VBT] Enabled: {goal_category} goal with {fitness_level} level")
        return True

    # Rule 2: Hypertrophy-only goals don't use VBT
    if goal_category == "hypertrophy" and specific_sport == "none":
        logger.info("[VBT] Disabled: hypertrophy goal without sport context")
        return False

    # Rule 3: Beginners with non-power goals don't get VBT
    if fitness_level == "beginner":
        logger.info("[VBT] Disabled: beginner level with non-power goal (form mastery priority)")
        return False

    # Rule 4: Advanced strength athletes use VBT
    if goal_category == "strength" and fitness_level == "advanced":
        logger.info("[VBT] Enabled: advanced strength training")
        return True

    # Rule 5: Check if sport involves explosiveness (intermediate/advanced only)
    explosive_sports = [
        "sprinting", "track and field", "olympic weightlifting", "powerlifting",
        "basketball", "football", "volleyball", "jumping", "throwing",
        "baseball", "softball", "rugby", "hockey", "soccer", "lacrosse"
    ]

    sport_lower = specific_sport.lower() if specific_sport else ""
    if any(sport in sport_lower for sport in explosive_sports):
        logger.info(f"[VBT] Enabled: explosive sport ({specific_sport}) with {fitness_level} level")
        return True

    # Default: No VBT
    logger.info(f"[VBT] Disabled: {fitness_level} + {goal_category} + {specific_sport} doesn't warrant VBT")
    return False
