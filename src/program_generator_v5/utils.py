"""
V5 Program Generator — Shared Utilities
Used by multiple layers for prescription, time estimation, sorting, etc.
"""

from __future__ import annotations

import math
from typing import Optional

from .schemas import (
    Exercise,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    PrescribedSet,
    PrescribedExercise,
    WeekProfile,
)


# ─────────────────────────────────────────────────────────────────────────────
# A) PRESCRIPTION ENGINE — THE CORE OF LAYER 4
# ─────────────────────────────────────────────────────────────────────────────

# Rep ranges by exercise_type × goal
REP_RANGES = {
    "hypertrophy": {
        "heavy_compound": (6, 10),
        "light_compound": (8, 12),
        "isolation": (10, 15),
        "power": (3, 5),
        "plyometric": (3, 5),
    },
    "strength": {
        "heavy_compound": (1, 5),
        "light_compound": (5, 8),
        "isolation": (8, 12),
        "power": (1, 3),
        "plyometric": (3, 5),
    },
    "power": {
        "heavy_compound": (3, 5),
        "light_compound": (5, 8),
        "isolation": (6, 10),
        "power": (1, 3),
        "plyometric": (3, 5),
    },
}

# Rest periods (seconds) by exercise_type × goal
REST_SECONDS = {
    "hypertrophy": {
        "heavy_compound": 150,
        "light_compound": 100,
        "isolation": 75,
        "power": 240,
        "plyometric": 240,
    },
    "strength": {
        "heavy_compound": 240,
        "light_compound": 150,
        "isolation": 100,
        "power": 270,
        "plyometric": 240,
    },
    "power": {
        "heavy_compound": 210,
        "light_compound": 150,
        "isolation": 90,
        "power": 270,
        "plyometric": 270,
    },
}

# Tempo prescriptions by exercise_type × goal
# Format: "eccentric-pause_bottom-concentric-pause_top"
TEMPOS = {
    "hypertrophy": {
        "heavy_compound": "2-1-1-0",
        "light_compound": "2-1-1-1",
        "isolation": "3-1-1-1",
        "power": "1-0-X-0",
        "plyometric": "1-0-X-0",
    },
    "strength": {
        "heavy_compound": "1-1-X-0",
        "light_compound": "2-0-1-0",
        "isolation": "2-0-1-0",
        "power": "1-0-X-0",
        "plyometric": "1-0-X-0",
    },
    "power": {
        "power": "1-0-X-0",
        "plyometric": "1-0-X-0",
        "heavy_compound": "1-1-X-0",
        "light_compound": "2-0-1-0",
        "isolation": "2-0-1-0",
    },
}

# Map week intensity_modifier to rep position within range
# 0.0 = bottom of range (heaviest), 1.0 = top of range (lightest)
INTENSITY_TO_REP_POSITION = {
    "deload": 1.0,
    "light": 0.85,
    "moderate": 0.6,
    "moderate_heavy": 0.35,
    "heavy": 0.15,
    "very_heavy": 0.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# INTENSITY CALCULATION TABLES — PERIODIZATION-BASED
# ─────────────────────────────────────────────────────────────────────────────

# Base intensity ranges by intensity_modifier (for heavy compounds)
# These ranges are the PRIMARY driver of intensity, derived from WeekProfile
INTENSITY_BY_MODIFIER = {
    "deload": (50, 60),       # Light technique work, recovery
    "light": (60, 70),        # Recovery/introduction weeks
    "moderate": (70, 77),     # Standard training intensity
    "moderate_heavy": (77, 83),  # Pushing harder, overreaching
    "heavy": (83, 88),        # Strength-focused, lower reps
    "very_heavy": (88, 93),   # Peak intensity, near maximal
}

# Exercise type intensity offsets (relative to heavy compounds)
EXERCISE_TYPE_INTENSITY_OFFSET = {
    "heavy_compound": 0,      # Baseline (squat, bench, deadlift)
    "light_compound": -3,     # Slightly lighter (lunges, RDL)
    "power": +3,              # Explosive movements use heavier relative loads
    "plyometric": 0,          # Returns None (bodyweight)
    "isolation": -8,          # Much lighter relative loads
}

# Reps → intensity position within range
# Fewer reps = higher end of intensity range
# More reps = lower end of intensity range
REPS_TO_INTENSITY_POSITION = {
    1: 1.0,    # Top of range (heaviest)
    2: 0.95,
    3: 0.90,
    4: 0.85,
    5: 0.80,
    6: 0.70,
    7: 0.60,
    8: 0.50,   # Middle of range
    9: 0.40,
    10: 0.30,
    11: 0.25,
    12: 0.20,
    13: 0.15,
    14: 0.10,
    15: 0.05,
}

# Progressive overload: intensity bump per mesocycle
MESOCYCLE_PROGRESSION_PERCENT = 1.5  # +1.5% per mesocycle after first

# RIR adjustment factor
RIR_INTENSITY_REDUCTION = 2.0  # -2% per RIR point


def calculate_intensity_percent(
    reps: int,
    rir: int,
    exercise_type: str,
    week_profile: Optional[WeekProfile] = None,
    program_goal: str = "hypertrophy",
) -> Optional[float]:
    """
    Calculate intensity as % of 1RM following periodization principles.

    This is the PRODUCTION intensity calculator that integrates with V5's
    periodization system for proper progressive overload.

    Factors (in order of importance):
    1. intensity_modifier from WeekProfile (primary driver)
    2. Exercise type offset (compounds vs isolations)
    3. Reps (position within intensity range)
    4. RIR (further adjustment for effort level)
    5. Mesocycle progression (+1.5% per mesocycle)

    Args:
        reps: Number of reps prescribed
        rir: Reps in reserve
        exercise_type: "heavy_compound", "light_compound", "isolation", "power", "plyometric"
        week_profile: WeekProfile with intensity_modifier, mesocycle_number
        program_goal: "hypertrophy", "strength", or "power"

    Returns:
        Intensity as percentage of 1RM, or None for bodyweight exercises
    """
    # Plyometric exercises don't use %1RM - display as "BW"
    if exercise_type == "plyometric":
        return None

    # ── 1. Get base intensity range from intensity_modifier ──────────────────
    if week_profile:
        modifier = week_profile.intensity_modifier
    else:
        # Fallback if no week_profile (shouldn't happen in normal flow)
        modifier = "moderate"

    intensity_range = INTENSITY_BY_MODIFIER.get(modifier, (70, 77))
    range_low, range_high = intensity_range

    # ── 2. Position within range based on reps ───────────────────────────────
    # Fewer reps → higher intensity within range
    if reps <= 15:
        position = REPS_TO_INTENSITY_POSITION.get(reps, 0.3)
    else:
        # High reps: use lower end of range
        position = max(0.0, 0.05 - (reps - 15) * 0.01)

    base_intensity = range_low + position * (range_high - range_low)

    # ── 3. Apply exercise type offset ────────────────────────────────────────
    type_offset = EXERCISE_TYPE_INTENSITY_OFFSET.get(exercise_type, 0)
    intensity = base_intensity + type_offset

    # ── 4. Apply RIR adjustment ──────────────────────────────────────────────
    # More RIR = working below true max = lower effective intensity
    rir_adjustment = rir * RIR_INTENSITY_REDUCTION
    intensity -= rir_adjustment

    # ── 5. Apply mesocycle progression ───────────────────────────────────────
    # Progressive overload: each mesocycle starts slightly higher
    if week_profile and week_profile.mesocycle_number > 1:
        progression = (week_profile.mesocycle_number - 1) * MESOCYCLE_PROGRESSION_PERCENT
        intensity += progression

    # ── 6. Clamp isolations to reasonable range ──────────────────────────────
    # Isolation exercises don't truly operate at high %1RM
    if exercise_type == "isolation":
        intensity = min(intensity, 75)

    # ── 7. Final clamp to valid range ────────────────────────────────────────
    intensity = max(40, min(95, intensity))

    return round(intensity, 1)


def calculate_intensity_percent_simple(
    reps: int,
    rir: int,
    exercise_type: str,
) -> Optional[float]:
    """
    Simple intensity calculator for use when WeekProfile is not available.

    Used by validator/mutator when copying or adjusting existing sets.
    Falls back to reasonable defaults.
    """
    if exercise_type == "plyometric":
        return None

    # Use rep-based estimation (Epley formula approximation)
    REPS_TO_INTENSITY = {
        1: 100, 2: 97, 3: 94, 4: 92, 5: 89,
        6: 86, 7: 83, 8: 81, 9: 78, 10: 75,
        11: 73, 12: 71, 13: 69, 14: 67, 15: 65,
    }

    if reps <= 15:
        base = REPS_TO_INTENSITY.get(reps, 65)
    else:
        base = max(50, 65 - (reps - 15) * 2)

    # RIR adjustment
    intensity = base - (rir * 2.0)

    # Exercise type adjustment
    if exercise_type == "isolation":
        intensity = min(intensity, 75)
    elif exercise_type == "power":
        intensity += 3

    return round(max(40, min(95, intensity)), 1)


def prescribe_exercise(
    exercise: Exercise,
    total_sets: int,
    week_profile: WeekProfile,
    program_goal: str,
    is_last_set_to_failure: bool = False,
    vbt_enabled: bool = False,
    vbt_protocol: str = "",
) -> list[PrescribedSet]:
    """
    Prescribe sets, reps, RPE, RIR, rest, tempo, and notes for an exercise
    based on its type, the week profile, and the program goal.

    This is the DETERMINISTIC prescription engine — no LLM, pure rules.
    When VBT is enabled and the exercise is eligible, velocity targets are added.
    """
    from .vbt_profiles import get_velocity_targets

    ex_type = exercise.exercise_type.value

    # ── 1. Determine rep range ──────────────────────────────────────────────
    min_rep, max_rep = REP_RANGES[program_goal][ex_type]

    # Clamp to exercise's own constraints
    min_rep = max(min_rep, exercise.min_reps)
    max_rep = min(max_rep, exercise.max_reps)

    # ── 2. Select reps within range based on week intensity ─────────────────
    position = INTENSITY_TO_REP_POSITION.get(week_profile.intensity_modifier, 0.6)
    reps = round(min_rep + position * (max_rep - min_rep))
    reps = max(min_rep, min(max_rep, reps))

    # ── 3. Determine rest ────────────────────────────────────────────────────
    rest = REST_SECONDS[program_goal][ex_type]
    if week_profile.is_deload:
        rest = int(rest * 0.75)  # Lighter loads = less rest needed

    # VBT: ensure full recovery for velocity-tracked exercises
    if vbt_enabled and exercise.vbt_eligible and rest < 180:
        rest = 180

    # ── 4. RPE/RIR from week profile, adjusted by exercise type ─────────────
    base_rpe_low, base_rpe_high = week_profile.rpe_range
    base_rir_low, base_rir_high = week_profile.rir_range

    if ex_type == "isolation":
        # Isolations can be pushed harder (less systemic fatigue)
        rpe = round(base_rpe_high, 1)
        rir = base_rir_low
    elif ex_type == "heavy_compound":
        # Compounds stay conservative (more fatigue, injury risk)
        rpe = round(base_rpe_low, 1)
        rir = base_rir_high
    else:
        rpe = round((base_rpe_low + base_rpe_high) / 2, 1)
        rir = round((base_rir_low + base_rir_high) / 2)

    # ── 5. Tempo ─────────────────────────────────────────────────────────────
    tempo = TEMPOS.get(program_goal, {}).get(ex_type, "2-0-1-0")

    # ── 6. Build sets ────────────────────────────────────────────────────────
    sets = []
    for i in range(total_sets):
        set_notes = ""
        set_rpe = rpe
        set_rir = rir

        # First set warmup note for heavy compounds
        if i == 0 and ex_type == "heavy_compound":
            set_notes = "Ramp up with 2-3 warm-up sets before working weight"

        # Last set of last hard week in mesocycle: push isolations to failure
        # week_in_mesocycle == 3 → "Overreaching" week (before deload)
        if (
            i == total_sets - 1
            and week_profile.week_in_mesocycle == 3
            and ex_type == "isolation"
            and not week_profile.is_deload
        ):
            set_notes = "Push to failure on this set"
            set_rpe = 10.0
            set_rir = 0

        # Optional override for last-set failure (used by validators/mutations)
        if is_last_set_to_failure and i == total_sets - 1:
            set_notes = "Push to failure on this set"
            set_rpe = 10.0
            set_rir = 0

        # Calculate intensity_percent using full periodization context
        intensity_pct = calculate_intensity_percent(
            reps=reps,
            rir=set_rir,
            exercise_type=ex_type,
            week_profile=week_profile,
            program_goal=program_goal,
        )

        # ── 7. VBT velocity targets ─────────────────────────────────────────
        velocity_target = None
        velocity_min = None
        velocity_max = None

        if vbt_enabled and exercise.vbt_eligible and intensity_pct:
            vbt_data = get_velocity_targets(exercise.id, intensity_pct, vbt_protocol)
            velocity_target = vbt_data["velocity_target"]
            velocity_min = vbt_data["velocity_min"]
            velocity_max = vbt_data["velocity_max"]

            if velocity_target:
                if vbt_protocol == "velocity_based":
                    vbt_note = f"Target: {velocity_target} m/s — stop set if below {velocity_min} m/s"
                else:
                    vbt_note = f"Velocity check: expect ~{velocity_target} m/s"
                set_notes = f"{set_notes}. {vbt_note}" if set_notes else vbt_note

        sets.append(
            PrescribedSet(
                set_number=i + 1,
                reps=reps,
                rpe=set_rpe,
                rir=set_rir,
                intensity_percent=intensity_pct,
                rest_seconds=rest,
                tempo=tempo,
                notes=set_notes,
                velocity_target=velocity_target,
                velocity_min=velocity_min,
                velocity_max=velocity_max,
            )
        )

    return sets


# ─────────────────────────────────────────────────────────────────────────────
# B) TIME ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────


def estimate_session_duration(exercises: list[PrescribedExercise]) -> int:
    """
    Estimate total session time in minutes.

    Calculation:
      - 5 min warmup
      - 3 min cooldown
      - Per exercise:
          - First exercise: 90s setup
          - Subsequent exercises: 45s transition
          - Per set: (reps × tempo_seconds) + rest_seconds
          - Supersetted exercises: rest reduced by 40%
      - Return total minutes, rounded up
    """
    duration_seconds = 5 * 60  # 5 min warmup

    for idx, prescribed_ex in enumerate(exercises):
        # Setup/transition time
        if idx == 0:
            duration_seconds += 90  # First exercise setup
        else:
            duration_seconds += 45  # Transition between exercises

        # Per-set execution time
        for set_obj in prescribed_ex.sets:
            # Execution: estimate reps × avg_rep_duration
            # Parse tempo if available, else use defaults
            tempo_total = _parse_tempo_duration(set_obj.tempo, prescribed_ex.exercise_type)
            set_execution_time = set_obj.reps * tempo_total
            duration_seconds += set_execution_time

            # Rest time (skip after last set of the exercise)
            if set_obj.set_number < len(prescribed_ex.sets):
                rest = set_obj.rest_seconds
                # Supersetted exercises have reduced rest
                if prescribed_ex.superset_group:
                    rest = int(rest * 0.6)
                duration_seconds += rest

    duration_seconds += 3 * 60  # 3 min cooldown
    return math.ceil(duration_seconds / 60)


def _parse_tempo_duration(tempo: Optional[str], exercise_type: ExerciseType) -> float:
    """
    Parse tempo string "eccentric-pause_bottom-concentric-pause_top" into
    total seconds per rep.  "X" means explosive (estimate 1 second).
    If tempo is None, use default based on exercise type.
    """
    if not tempo:
        # Default: heavy/power = 4s, else 3s
        if exercise_type in (ExerciseType.HEAVY_COMPOUND, ExerciseType.POWER):
            return 4.0
        return 3.0

    parts = tempo.split("-")
    total = 0.0
    for part in parts:
        if part.upper() == "X":
            total += 1.0  # Explosive = ~1 second
        else:
            try:
                total += float(part)
            except ValueError:
                total += 1.0  # Default fallback

    return max(total, 2.0)  # Minimum 2s per rep


# ─────────────────────────────────────────────────────────────────────────────
# C) SUPERSET BUILDER
# ─────────────────────────────────────────────────────────────────────────────


def build_supersets(
    exercises: list[PrescribedExercise], goal: str
) -> list[PrescribedExercise]:
    """
    Pair antagonist isolation exercises into supersets for hypertrophy programs.

    Rules:
      - Only apply for hypertrophy goal
      - Never superset two heavy compounds
      - Never superset exercises with the same primary muscle
      - Pair push+pull for same joint (e.g., tricep extension + bicep curl)
      - Assign superset_group labels: "A", "B", etc.
      - Keep pairs adjacent in the list
    """
    if goal != "hypertrophy":
        return exercises

    result = []
    paired_indices = set()
    superset_label_counter = 0

    for i, ex in enumerate(exercises):
        if i in paired_indices:
            continue  # Already paired

        # Don't superset heavy compounds
        if ex.exercise_type == ExerciseType.HEAVY_COMPOUND:
            result.append(ex)
            continue

        # Look for a pairable antagonist
        for j in range(i + 1, len(exercises)):
            if j in paired_indices:
                continue

            candidate = exercises[j]

            # Don't pair heavy compounds
            if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                continue

            # Check for antagonist pairing (push+pull, or different primary muscles)
            if _are_antagonists(ex, candidate):
                # Pair them
                label = chr(ord("A") + superset_label_counter)
                superset_label_counter += 1

                ex.superset_group = label
                candidate.superset_group = label

                result.append(ex)
                result.append(candidate)

                paired_indices.add(i)
                paired_indices.add(j)
                break
        else:
            # No pair found — add unpaired
            result.append(ex)

    return result


def _are_antagonists(ex1: PrescribedExercise, ex2: PrescribedExercise) -> bool:
    """
    Check if two exercises are antagonist pairs suitable for supersets.

    Examples:
      - Bicep curl (isolation_pull) + Tricep extension (isolation_push)
      - Chest press (horizontal_push) + Row (horizontal_pull)
      - Quad extension + Hamstring curl
    """
    # Extract primary muscles
    primaries_1 = {
        muscle
        for muscle, contribution in ex1.muscle_contributions.items()
        if contribution >= 0.8  # Primary if ≥0.8 sets contributed
    }
    primaries_2 = {
        muscle
        for muscle, contribution in ex2.muscle_contributions.items()
        if contribution >= 0.8
    }

    # No overlap in primary muscles
    if primaries_1 & primaries_2:
        return False

    # Check for classic antagonist pairs
    antagonist_pairs = [
        ({"biceps"}, {"triceps"}),
        ({"chest", "upper_chest", "lower_chest"}, {"lats", "upper_back"}),
        ({"quads"}, {"hamstrings"}),
        ({"front_delts", "side_delts"}, {"rear_delts"}),
    ]

    for group_a, group_b in antagonist_pairs:
        if (primaries_1 & group_a and primaries_2 & group_b) or (
            primaries_1 & group_b and primaries_2 & group_a
        ):
            return True

    # Check for push+pull pattern pairing
    push_patterns = {MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH, MovementPattern.ISOLATION_PUSH}
    pull_patterns = {MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PULL, MovementPattern.ISOLATION_PULL}

    if (ex1.movement_pattern in push_patterns and ex2.movement_pattern in pull_patterns) or (
        ex1.movement_pattern in pull_patterns and ex2.movement_pattern in push_patterns
    ):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# D) EXERCISE SORTING
# ─────────────────────────────────────────────────────────────────────────────


def sort_exercises_for_session(
    exercises: list[PrescribedExercise], goal: str
) -> list[PrescribedExercise]:
    """
    Sort exercises within a session for optimal training quality.

    Order:
      1. Power/plyometric (CNS fresh, explosive)
      2. Heavy compounds (most demanding)
      3. Light compounds
      4. Isolations

    Within each tier, larger muscles first.
    Supersetted exercises stay adjacent.
    """
    # Exercise type priority (lower = earlier in session)
    type_priority = {
        ExerciseType.POWER: 0,
        ExerciseType.PLYOMETRIC: 1,
        ExerciseType.HEAVY_COMPOUND: 2,
        ExerciseType.LIGHT_COMPOUND: 3,
        ExerciseType.ISOLATION: 4,
    }

    # Muscle group size priority (for tie-breaking within same type)
    muscle_size_priority = {
        "quads": 0,
        "glutes": 1,
        "hamstrings": 2,
        "chest": 3,
        "lats": 4,
        "upper_back": 5,
        "side_delts": 6,
        "triceps": 7,
        "biceps": 8,
        "calves": 9,
        "abs": 10,
    }

    def _sort_key(ex: PrescribedExercise) -> tuple:
        """
        Returns a tuple for sorting:
          (type_priority, muscle_priority, superset_group_order)
        """
        type_pri = type_priority.get(ex.exercise_type, 5)

        # Find the largest primary muscle
        muscle_pri = 99
        for muscle in ex.muscle_contributions:
            muscle_pri = min(muscle_pri, muscle_size_priority.get(muscle, 99))

        # Superset grouping: keep pairs adjacent by group label
        superset_order = ord(ex.superset_group[0]) if ex.superset_group else 999

        return (type_pri, muscle_pri, superset_order)

    sorted_exercises = sorted(exercises, key=_sort_key)

    # Update order_in_session
    for i, ex in enumerate(sorted_exercises):
        ex.order_in_session = i + 1

    return sorted_exercises


# ─────────────────────────────────────────────────────────────────────────────
# E) PATTERN FILL PRIORITY
# ─────────────────────────────────────────────────────────────────────────────


def get_pattern_fill_priority(goal: str) -> list[MovementPattern]:
    """
    Returns the order in which movement patterns should be filled
    during exercise selection (Layer 4, Phase 1).

    This ensures critical patterns (squat, hip hinge, horizontal push/pull)
    are filled FIRST before isolations consume the exercise budget.
    """
    if goal == "hypertrophy":
        return [
            MovementPattern.SQUAT,
            MovementPattern.HIP_HINGE,
            MovementPattern.HORIZONTAL_PUSH,
            MovementPattern.HORIZONTAL_PULL,
            MovementPattern.VERTICAL_PULL,
            MovementPattern.VERTICAL_PUSH,
            MovementPattern.ISOLATION_PULL,
            MovementPattern.ISOLATION_PUSH,
            MovementPattern.CORE,
        ]
    elif goal == "strength":
        return [
            MovementPattern.SQUAT,
            MovementPattern.HIP_HINGE,
            MovementPattern.HORIZONTAL_PUSH,
            MovementPattern.VERTICAL_PUSH,
            MovementPattern.HORIZONTAL_PULL,
            MovementPattern.VERTICAL_PULL,
            MovementPattern.ISOLATION_PULL,
            MovementPattern.ISOLATION_PUSH,
        ]
    elif goal == "power":
        return [
            MovementPattern.POWER_LOWER,
            MovementPattern.POWER_UPPER,
            MovementPattern.SQUAT,
            MovementPattern.HIP_HINGE,
            MovementPattern.HORIZONTAL_PUSH,
            MovementPattern.HORIZONTAL_PULL,
            MovementPattern.VERTICAL_PULL,
            MovementPattern.VERTICAL_PUSH,
            MovementPattern.ISOLATION_PULL,
            MovementPattern.ISOLATION_PUSH,
        ]
    else:
        # Default fallback
        return [
            MovementPattern.SQUAT,
            MovementPattern.HIP_HINGE,
            MovementPattern.HORIZONTAL_PUSH,
            MovementPattern.HORIZONTAL_PULL,
            MovementPattern.VERTICAL_PULL,
            MovementPattern.VERTICAL_PUSH,
        ]
