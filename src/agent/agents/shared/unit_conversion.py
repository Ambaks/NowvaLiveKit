"""
Shared unit conversion and goal categorization utilities for voice agents.
Used by both the website voice agent and main Nova voice agent.
"""

import re
from typing import Optional


def normalize_height_to_cm(height_str: str) -> Optional[float]:
    """Convert various height formats to centimeters.

    Supports: cm, meters, feet/inches, and bare numbers.

    Args:
        height_str: Height as spoken by user (e.g., "5'10\"", "175 cm", "180")

    Returns:
        Height in centimeters, or None if parsing fails
    """
    if not height_str:
        return None

    height_str = height_str.lower().strip()

    # Pattern: X cm or X centimeters
    cm_match = re.search(r'(\d+\.?\d*)\s*(cm|centimeter)', height_str)
    if cm_match:
        return float(cm_match.group(1))

    # Pattern: X.XX m or X.XX meters
    m_match = re.search(r'(\d+\.?\d*)\s*(m|meter)', height_str)
    if m_match:
        return float(m_match.group(1)) * 100

    # Pattern: X feet Y inches OR X foot Y inches OR X'Y"
    feet_inches_match = re.search(r"(\d+)\s*(?:feet|foot|ft|')\s*(\d+)\s*(?:inches?|in|\")?", height_str)
    if feet_inches_match:
        feet = int(feet_inches_match.group(1))
        inches = int(feet_inches_match.group(2))
        total_inches = (feet * 12) + inches
        return total_inches * 2.54

    # Pattern: Just feet
    feet_only_match = re.search(r'(\d+)\s*(?:feet|foot|ft)', height_str)
    if feet_only_match:
        feet = int(feet_only_match.group(1))
        return feet * 12 * 2.54

    # Pattern: Just inches
    inches_match = re.search(r'(\d+)\s*(?:inches?|in)', height_str)
    if inches_match:
        inches = int(inches_match.group(1))
        return inches * 2.54

    # Pattern: Just a number - try to infer
    number_match = re.search(r'(\d+\.?\d*)', height_str)
    if number_match:
        num = float(number_match.group(1))
        if num < 10:  # Likely meters
            return num * 100
        elif 50 <= num <= 300:  # Likely cm
            return num
        elif num > 300:  # Likely inches
            return num * 2.54

    return None


def normalize_weight_to_kg(weight_str: str) -> Optional[float]:
    """Convert various weight formats to kilograms.

    Supports: kg, lbs/pounds, and bare numbers (assumes pounds if < 500).

    Args:
        weight_str: Weight as spoken by user (e.g., "185 pounds", "80 kg", "185")

    Returns:
        Weight in kilograms, or None if parsing fails
    """
    if not weight_str:
        return None

    weight_str = weight_str.lower().strip()

    # Pattern: X kg or X kilograms
    kg_match = re.search(r'(\d+\.?\d*)\s*(kg|kilogram)', weight_str)
    if kg_match:
        return float(kg_match.group(1))

    # Pattern: X lbs or X pounds
    lbs_match = re.search(r'(\d+\.?\d*)\s*(lbs?|pounds?)', weight_str)
    if lbs_match:
        return float(lbs_match.group(1)) * 0.453592

    # Pattern: Just a number - assume pounds if < 500, kg if >= 500
    number_match = re.search(r'(\d+\.?\d*)', weight_str)
    if number_match:
        num = float(number_match.group(1))
        if num < 500:  # Likely pounds
            return num * 0.453592
        else:  # Likely kg
            return num

    return None


def categorize_goal(goal_text: str) -> str:
    """Categorize user's fitness goal into power, strength, or hypertrophy.

    Args:
        goal_text: User's description of their fitness goal

    Returns:
        One of: "power", "strength", "hypertrophy"
    """
    goal_lower = goal_text.lower()

    power_keywords = [
        "explosive", "power", "athletic", "speed", "jump", "sprint",
        "vertical", "fast", "quick", "agility", "reactive", "plyometric",
        "burst", "acceleration"
    ]

    strength_keywords = [
        "strong", "strength", "lift heavy", "max", "1rm", "powerlifting",
        "squat", "deadlift", "bench", "press", "force"
    ]

    hypertrophy_keywords = [
        "muscle", "size", "big", "mass", "bulk", "bodybuilding",
        "aesthetic", "look good", "physique", "gain weight", "grow"
    ]

    power_score = sum(1 for kw in power_keywords if kw in goal_lower)
    strength_score = sum(1 for kw in strength_keywords if kw in goal_lower)
    hypertrophy_score = sum(1 for kw in hypertrophy_keywords if kw in goal_lower)

    if power_score > strength_score and power_score > hypertrophy_score:
        return "power"
    elif strength_score > hypertrophy_score:
        return "strength"
    else:
        return "hypertrophy"
