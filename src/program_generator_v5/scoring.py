"""
V5 Program Generator — Exercise Scoring Function
Drives exercise selection in Layer 4's Stage A.

The scoring function evaluates every candidate exercise against 8 weighted factors
and returns a single float score. Higher = better candidate.
"""

from __future__ import annotations

from typing import Optional

from .schemas import Exercise, ExerciseType, EccentricStress


# ─────────────────────────────────────────────────────────────────────────────
# LAZY IMPORT to avoid circular dependency at module load time
# ─────────────────────────────────────────────────────────────────────────────

_exercise_library_cache: Optional[list] = None


def _get_exercise_library():
    global _exercise_library_cache
    if _exercise_library_cache is None:
        from .exercise_library import EXERCISE_LIBRARY
        _exercise_library_cache = EXERCISE_LIBRARY
    return _exercise_library_cache


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _get_weeks_since_used(
    exercise_id: str,
    recently_used: dict[str, list],
    current_week: int,
) -> Optional[int]:
    """
    Returns the number of weeks since this exercise was last used,
    or None if the exercise has never been used in this mesocycle.

    0 means it was used this week (different session — same-week repeat).
    1 means it was used last week.
    """
    if exercise_id not in recently_used or not recently_used[exercise_id]:
        return None

    uses = recently_used[exercise_id]
    # Each entry is (week_num, was_primary)
    most_recent_week = max(week_num for week_num, _ in uses)
    return current_week - most_recent_week


def _get_rotation_group_usage(
    rotation_group: str,
    recently_used: dict[str, list],
) -> int:
    """
    Count the total number of recent uses by any exercise that belongs
    to this rotation_group.  Higher values → penalise more.
    """
    library = _get_exercise_library()
    count = 0
    for ex in library:
        if ex.rotation_group == rotation_group and ex.id in recently_used:
            count += len(recently_used[ex.id])
    return count


def _was_primary_compound_last_week(
    exercise_id: str,
    recently_used: dict[str, list],
    week_number: int,
) -> bool:
    """
    Returns True if this exercise was flagged as a primary compound
    in week_number - 1.
    """
    if exercise_id not in recently_used:
        return False

    for week_num, was_primary in recently_used[exercise_id]:
        if week_num == week_number - 1 and was_primary:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCORING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def compute_exercise_score(
    exercise: Exercise,
    remaining_volume: dict[str, float],        # muscle → remaining sets needed
    recently_used: dict[str, list],            # exercise_id → [(week_num, was_primary)]
    mesocycle_number: int,
    week_number: int,
    session_axial_count: int,                  # axial exercises already in this session
    session_grip_count: int,                   # grip-intensive exercises already in session
    program_goal: str,                         # "hypertrophy", "strength", "power"
    user_preferences: dict = None,             # exercise_id → preference score (or list of ids)
    vbt_enabled: bool = False,
    training_level: str = "intermediate",
    is_in_season: bool = False,               # V6: penalize high-eccentric exercises in-season
) -> float:
    """
    Compute a composite score for an exercise candidate.  Higher = better.

    8 factors (from spec §Layer 4 / Stage A):
      1. SFR Rating          — stimulus-to-fatigue; weighted higher for hypertrophy
      2. Volume Fill         — how many remaining volume targets does this exercise address?
      3. Variety             — penalise recent use; bonus for never-used-this-meso exercises
      4. Rotation Group Freshness — penalise if same rotation_group was recently overused
      5. Compound Consistency — bonus for keeping primary compounds within a mesocycle;
                                 bonus for switching between mesocycles
      6. Fatigue Management  — penalty for stacking axial/grip-intensive exercises
      7. User Preference     — bonus if exercise_id is in user's preferred list
      8. Stretch Position    — bonus for hypertrophy when exercise loads muscle at length
    """
    score = 0.0
    user_preferences = user_preferences or {}

    # ── 1. SFR Rating ────────────────────────────────────────────────────────
    # Hypertrophy: SFR is the primary driver → weight it higher
    # Strength/Power: SFR matters less; specificity and exercise type drive selection
    if program_goal == "hypertrophy":
        score += exercise.sfr_rating * 12
    else:
        score += exercise.sfr_rating * 6

    # ── 2. Volume Fill ───────────────────────────────────────────────────────
    # Sum of (remaining_volume[muscle] × volume_credit) capped at max_sets_per_session.
    # Primary (credit 1.0) contributes more than secondary (credit 0.5).
    volume_fill = 0.0
    for ma in exercise.muscle_activations:
        muscle_key = ma.muscle.value
        if muscle_key in remaining_volume and remaining_volume[muscle_key] > 0:
            capped = min(remaining_volume[muscle_key], exercise.max_sets_per_session)
            volume_fill += capped * ma.volume_credit

    score += volume_fill * 8

    # ── 3. Variety ───────────────────────────────────────────────────────────
    weeks_since = _get_weeks_since_used(exercise.id, recently_used, week_number)

    if weeks_since == 0:
        # Used this week in a different session — allow (compounds train 2×/week)
        # but discourage redundancy
        score -= 15
    elif weeks_since == 1:
        # Used last week — mild penalty to encourage rotation
        score -= 5
    elif weeks_since is None:
        # Never used in this mesocycle → freshness bonus
        score += 10
    else:
        # Used, but 2+ weeks ago — reward recency proportionally, capped at +10
        score += min(weeks_since * 3, 10)

    # ── 4. Rotation Group Freshness ──────────────────────────────────────────
    # Penalise if another exercise from the same interchangeable group was recently used.
    group_usage = _get_rotation_group_usage(exercise.rotation_group, recently_used)
    score -= group_usage * 3

    # ── 5. Compound Consistency (within meso) / Novelty (between mesos) ─────
    if exercise.exercise_type in (ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND):
        # Within a mesocycle, keep the SAME primary compound so athletes can track
        # progressive overload session-to-session.
        if _was_primary_compound_last_week(exercise.id, recently_used, week_number):
            score += 20  # Strong consistency bonus

        # Between mesocycles (mesocycle_number > 1), favour a DIFFERENT exercise
        # from the rotation group to introduce a fresh stimulus.
        if mesocycle_number > 1:
            # Check if this exercise was a primary in the PREVIOUS mesocycle.
            # A simple heuristic: if it appears many times in recently_used with
            # was_primary=True, it was the meso-primary → penalise to encourage rotation.
            primary_uses = sum(
                1 for _, was_primary in recently_used.get(exercise.id, [])
                if was_primary
            )
            if primary_uses >= 2:
                # Was used as primary ≥2 times — likely the previous meso's primary.
                # Nudge selector toward a fresh rotation-group member.
                score -= 10

    elif exercise.exercise_type == ExerciseType.ISOLATION:
        # Isolations should rotate more; slight nudge if used last week.
        if weeks_since == 1:
            score -= 3

    # ── 6. Fatigue Management ────────────────────────────────────────────────
    # Axial loading (spinal compression): squat + deadlift + OHP + rows
    # Stacking >2 per session risks lower-back fatigue and CNS overreach.
    if exercise.is_axial_loading and session_axial_count >= 2:
        score -= 25  # Strong deterrent (still > 0 if SFR and volume fill are huge)

    # Grip-intensive: deadlifts, rows, farmers carries — hand/forearm fatigue
    if exercise.grip_intensive and session_grip_count >= 2:
        score -= 15

    # General high-systemic-fatigue exercises get a mild penalty to prefer
    # lower-fatigue alternatives when options are otherwise equal.
    if exercise.systemic_fatigue == "high":
        score -= 5

    # ── 7. User Preference ───────────────────────────────────────────────────
    # If the user said they love this exercise or asked to include it, prioritise it.
    # user_preferences can be a dict (exercise_id → score) or a list/set of ids.
    if isinstance(user_preferences, dict):
        if exercise.id in user_preferences:
            score += 20
    elif exercise.id in user_preferences:
        score += 20

    # ── 8. Stretch-Position Bonus (hypertrophy only) ─────────────────────────
    # V6: 2024-2025 research — training muscles at long lengths produces superior
    # hypertrophy. Uses trains_at_long_length attribute (replaces variation_tags check).
    if program_goal == "hypertrophy" and exercise.trains_at_long_length:
        score += 15

    # ── 8b. Eccentric Stress Penalty (in-season) ──────────────────────────
    # V6: In-season athletes must minimize DOMS to maintain game/practice readiness.
    # High eccentric exercises (Bulgarian split squats, RDLs, Nordic curls, walking lunges)
    # are penalized; low eccentric exercises (step-ups, carries, isometrics) are preferred.
    if is_in_season:
        if exercise.eccentric_stress == EccentricStress.HIGH:
            score -= 25  # Strong penalty — prefer lower-eccentric alternatives
        elif exercise.eccentric_stress == EccentricStress.LOW:
            score += 8   # Mild bonus for DOMS-friendly exercises

    # ── 9. Power/Plyometric Bonus (power programs only) ─────────────────────
    # Power programs prioritize explosive movements - Olympic lifts and plyometrics
    # are essential for developing athletic power (NSCA guidelines).
    if program_goal == "power" and exercise.exercise_type in (ExerciseType.POWER, ExerciseType.PLYOMETRIC):
        score += 15

    # ── 9b. Olympic Catch Lift Bonus (advanced/intermediate power programs) ──
    # Olympic lifts with a catch component (power clean, hang clean, snatch) are
    # the gold standard for developing explosive power and vertical jump.
    # Advanced athletes should always have these in a power program.
    if (program_goal == "power"
            and exercise.exercise_type == ExerciseType.POWER
            and "olympic" in exercise.variation_tags
            and training_level in ("advanced", "intermediate")):
        # Catch lifts (clean, snatch) > pulls (no catch) for power transfer
        if "catch" in exercise.variation_tags or "from_floor" in exercise.variation_tags:
            score += 35  # Strong priority — power clean/hang clean are mandatory-tier
        else:
            score += 15  # Pulls are still valuable but secondary to catch lifts

    # ── 10. VBT Bonus ──────────────────────────────────────────────────────
    # When VBT is enabled, prefer exercises that can leverage velocity tracking
    if vbt_enabled and exercise.vbt_eligible:
        score += 5

    return score
