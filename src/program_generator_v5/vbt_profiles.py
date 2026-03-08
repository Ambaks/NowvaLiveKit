"""
V5 VBT (Velocity-Based Training) Profiles

Deterministic velocity lookup tables based on published sport science research:
- González-Badillo & Sánchez-Medina (2010): Bench press load-velocity
- Sánchez-Medina et al. (2017): Squat load-velocity
- Jovanovic & Flanagan (2014): General load-velocity relationships
- Zourdos et al. (2016): Repetition-velocity relationships

Maps exercise categories × intensity (% 1RM) → expected mean concentric velocity (m/s).
"""

from __future__ import annotations

from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# LOAD-VELOCITY PROFILES
# Maps %1RM → expected mean concentric velocity (m/s) for each exercise category
# Data points from published research, intermediate values are interpolated
# ─────────────────────────────────────────────────────────────────────────────

LOAD_VELOCITY_PROFILES: dict[str, dict[int, float]] = {
    "squat": {
        40: 1.13, 45: 1.06, 50: 1.00, 55: 0.93, 60: 0.87,
        65: 0.80, 70: 0.74, 75: 0.67, 80: 0.60, 85: 0.52,
        90: 0.44, 95: 0.32, 100: 0.18,
    },
    "bench_press": {
        40: 1.00, 45: 0.94, 50: 0.88, 55: 0.82, 60: 0.77,
        65: 0.70, 70: 0.62, 75: 0.54, 80: 0.47, 85: 0.38,
        90: 0.30, 95: 0.20, 100: 0.10,
    },
    "deadlift": {
        40: 1.00, 45: 0.94, 50: 0.88, 55: 0.82, 60: 0.76,
        65: 0.70, 70: 0.64, 75: 0.57, 80: 0.50, 85: 0.42,
        90: 0.34, 95: 0.22, 100: 0.12,
    },
    "overhead_press": {
        40: 0.96, 45: 0.90, 50: 0.84, 55: 0.78, 60: 0.72,
        65: 0.65, 70: 0.58, 75: 0.51, 80: 0.43, 85: 0.35,
        90: 0.27, 95: 0.17, 100: 0.08,
    },
    "hip_thrust": {
        40: 1.10, 45: 1.03, 50: 0.96, 55: 0.89, 60: 0.82,
        65: 0.75, 70: 0.68, 75: 0.61, 80: 0.54, 85: 0.46,
        90: 0.38, 95: 0.28, 100: 0.16,
    },
    "power_clean": {
        40: 1.40, 45: 1.32, 50: 1.25, 55: 1.17, 60: 1.10,
        65: 1.02, 70: 0.95, 75: 0.88, 80: 0.80, 85: 0.72,
        90: 0.60,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# EXERCISE → VELOCITY PROFILE MAPPING
# Maps exercise_id to which velocity profile category to use
# ─────────────────────────────────────────────────────────────────────────────

EXERCISE_VELOCITY_MAP: dict[str, str] = {
    # Squats
    "barbell_back_squat": "squat",
    "barbell_front_squat": "squat",

    # Hip Hinges
    "barbell_conventional_deadlift": "deadlift",
    "barbell_sumo_deadlift": "deadlift",
    "barbell_romanian_deadlift": "deadlift",
    "barbell_hip_thrust": "hip_thrust",

    # Horizontal Push
    "barbell_bench_press": "bench_press",
    "barbell_incline_bench_press": "bench_press",
    "barbell_close_grip_bench_press": "bench_press",
    "barbell_floor_press": "bench_press",

    # Vertical Push
    "barbell_overhead_press": "overhead_press",
    "barbell_push_press": "overhead_press",

    # Olympic / Power
    "barbell_power_clean": "power_clean",
    "barbell_hang_power_clean": "power_clean",
    "barbell_hang_clean": "power_clean",
    "barbell_clean_pull": "power_clean",
    "barbell_hang_high_pull": "power_clean",
}


# ─────────────────────────────────────────────────────────────────────────────
# VELOCITY LOOKUP FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────


def _interpolate_velocity(profile: dict[int, float], intensity: float) -> float:
    """
    Linearly interpolate velocity from a load-velocity profile.

    Args:
        profile: Dict mapping %1RM (int) → velocity (float)
        intensity: Target intensity as percentage (e.g. 72.5)

    Returns:
        Interpolated velocity in m/s
    """
    sorted_points = sorted(profile.items())

    # Clamp to profile range
    if intensity <= sorted_points[0][0]:
        return sorted_points[0][1]
    if intensity >= sorted_points[-1][0]:
        return sorted_points[-1][1]

    # Find surrounding points and interpolate
    for i in range(len(sorted_points) - 1):
        low_pct, low_vel = sorted_points[i]
        high_pct, high_vel = sorted_points[i + 1]

        if low_pct <= intensity <= high_pct:
            ratio = (intensity - low_pct) / (high_pct - low_pct)
            return round(low_vel + ratio * (high_vel - low_vel), 2)

    return sorted_points[-1][1]  # Fallback


def get_velocity_targets(
    exercise_id: str,
    intensity_percent: Optional[float],
    protocol: str,
) -> dict[str, Optional[float]]:
    """
    Get VBT velocity targets for an exercise at a given intensity.

    Args:
        exercise_id: Exercise ID from the library
        intensity_percent: Prescribed intensity as % of 1RM
        protocol: "velocity_based" or "load_velocity"

    Returns:
        Dict with velocity_target, velocity_min, velocity_max (all m/s, or None)
    """
    empty = {"velocity_target": None, "velocity_min": None, "velocity_max": None}

    # Not a VBT-eligible exercise
    profile_key = EXERCISE_VELOCITY_MAP.get(exercise_id)
    if not profile_key:
        return empty

    profile = LOAD_VELOCITY_PROFILES.get(profile_key)
    if not profile or not intensity_percent:
        return empty

    velocity_target = _interpolate_velocity(profile, intensity_percent)

    if protocol == "velocity_based":
        # Primary metric = bar speed. Tighter bounds for quality reps.
        velocity_min = round(velocity_target * 0.85, 2)  # 15% fatigue threshold
        velocity_max = round(velocity_target * 1.10, 2)
    else:
        # load_velocity: velocity used for autoregulation, wider tolerance
        velocity_min = round(velocity_target * 0.80, 2)  # 20% tolerance
        velocity_max = round(velocity_target * 1.15, 2)

    return {
        "velocity_target": velocity_target,
        "velocity_min": velocity_min,
        "velocity_max": velocity_max,
    }
