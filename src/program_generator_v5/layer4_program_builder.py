"""
V5 Layer 4: Program Builder (Stage A - Deterministic)

Builds the actual program using a 3-phase greedy algorithm for exercise selection.

Phase 1: Fill required movement patterns with compounds
Phase 2: Fill remaining volume with isolations/accessories
Phase 3: Validate and patch

Uses scoring.py for exercise scoring and utils.py for prescription.

Algorithm from spec § Layer 4 / Stage A.
"""

from __future__ import annotations

import copy
from typing import Optional

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    VolumeAllocation,
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    PrescribedExercise,
    Exercise,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    MuscleRole,
    WarmUpProtocol,
    WarmUpSet,
    TrainingSeason,
)
from .exercise_library import EXERCISE_LIBRARY
from .scoring import compute_exercise_score
from .volume_tables import VOLUME_TABLES
from .utils import (
    prescribe_exercise,
    estimate_session_duration,
    sort_exercises_for_session,
    build_supersets,
    get_pattern_fill_priority,
)


# ─────────────────────────────────────────────────────────────────────────────
# REDUNDANT EXERCISE PAIRINGS BLOCKLIST
# ─────────────────────────────────────────────────────────────────────────────
# Specific exercise pairings that don't make sense together.
# Key = exercise ID, Value = list of exercise IDs that shouldn't be paired with it
REDUNDANT_PAIRS: dict[str, list[str]] = {
    "barbell_back_squat": ["bodyweight_squat"],
    "barbell_front_squat": ["bodyweight_squat"],
    "barbell_goblet_squat": ["bodyweight_squat"],
    # Note: sumo deadlift + bodyweight squat is OK - different movement patterns (hinge vs squat)
}


def is_blocked_pairing(candidate_id: str, selected_exercises: list) -> bool:
    """Check if candidate is explicitly blocked by an already-selected exercise."""
    for selected_ex, _ in selected_exercises:
        # Check if selected exercise blocks the candidate
        blocked_list = REDUNDANT_PAIRS.get(selected_ex.id, [])
        if candidate_id in blocked_list:
            return True
        # Also check reverse (if candidate blocks selected)
        blocked_list_reverse = REDUNDANT_PAIRS.get(candidate_id, [])
        if selected_ex.id in blocked_list_reverse:
            return True
    return False


def build_program(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
) -> BuiltProgram:
    """
    Build the complete program using deterministic exercise selection.

    Returns BuiltProgram with all weeks populated.
    Validates that weekly volume targets are met within ±2 sets.
    """
    # Filter exercises by equipment tier and avoid list
    available_exercises = _filter_available_exercises(profile)

    # Track recently used exercises across weeks
    recently_used: dict[str, list] = {}  # exercise_id → [(week_num, was_primary)]

    built_weeks = []

    for week_idx, week_profile in enumerate(strategy.week_profiles):
        volume_week = volume_allocation.weeks[week_idx]

        built_week = _build_week(
            profile=profile,
            strategy=strategy,
            week_profile=week_profile,
            volume_week=volume_week,
            available_exercises=available_exercises,
            recently_used=recently_used,
        )

        built_weeks.append(built_week)

        # Update recently_used after the week is built
        _update_recently_used(built_week, recently_used)

        # Between mesocycles: reset primary compound tracking
        # (so new mesocycle gets fresh compounds)
        # But keep general recently_used to avoid too-quick repeats
        if week_profile.week_in_mesocycle == 4:  # End of mesocycle (deload week)
            # Clear "was_primary" flags but keep the exercise usage history
            for ex_id in recently_used:
                recently_used[ex_id] = [
                    (week_num, False) for week_num, _ in recently_used[ex_id]
                ]

    # Calculate program totals
    total_sets = sum(w.weekly_volume_actual.get(m.value, 0) for w in built_weeks for m in MuscleGroup)
    total_workouts = sum(len(w.workouts) for w in built_weeks)
    unique_exercises = len(set(
        ex.exercise_id
        for week in built_weeks
        for workout in week.workouts
        for ex in workout.exercises
    ))

    return BuiltProgram(
        profile=profile,
        strategy=strategy,
        volume_allocation=volume_allocation,
        weeks=built_weeks,
        unique_exercises_used=unique_exercises,
        total_sets=int(total_sets),
        total_workouts=total_workouts,
        generation_time_seconds=0.0,  # Will be filled by caller if needed
    )


def _filter_available_exercises(profile: AthleteProfile) -> list[Exercise]:
    """Filter exercises by equipment tier and avoid list."""
    available = []
    for ex in EXERCISE_LIBRARY:
        # Check equipment tier
        if ex.equipment_tier.value > profile.equipment_tier.value:
            continue

        # Check avoid list
        if ex.id in profile.exercises_to_avoid:
            continue

        available.append(ex)

    return available


def _build_week(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    week_profile,
    volume_week,
    available_exercises: list[Exercise],
    recently_used: dict[str, list],
) -> BuiltWeek:
    """Build a single week of the program."""
    workouts = []

    # FIX 2: Track exercises used within this week for variety
    week_exercises_used: set[str] = set()

    # FIX MRV: Get MRV limits for this training level
    mrv_limits = {muscle: vals["mrv"] for muscle, vals in VOLUME_TABLES[profile.training_level].items()}
    mav_limits = {muscle: vals["mav"] for muscle, vals in VOLUME_TABLES[profile.training_level].items()}

    # Track weekly volume delivered so far (for MRV checking)
    weekly_volume_delivered: dict[str, float] = {}

    for day_idx, session_template in enumerate(strategy.split.sessions_per_week):
        volume_target = volume_week.sessions[day_idx]

        workout = _build_session(
            profile=profile,
            strategy=strategy,
            week_profile=week_profile,
            session_template=session_template,
            volume_target=volume_target,
            available_exercises=available_exercises,
            recently_used=recently_used,
            day_number=day_idx + 1,
            week_exercises_used=week_exercises_used,
            mrv_limits=mrv_limits,
            mav_limits=mav_limits,
            weekly_volume_delivered=weekly_volume_delivered,
        )

        workouts.append(workout)

        # FIX 2: Update week_exercises_used with exercises from this session
        for ex in workout.exercises:
            week_exercises_used.add(ex.exercise_id)

        # FIX MRV: Update weekly volume delivered
        for muscle, vol in workout.volume_delivered.items():
            weekly_volume_delivered[muscle] = weekly_volume_delivered.get(muscle, 0) + vol

    # Calculate weekly volume actual
    weekly_volume_actual = {}
    for muscle in MuscleGroup:
        muscle_key = muscle.value
        total = sum(
            workout.volume_delivered.get(muscle_key, 0)
            for workout in workouts
        )
        weekly_volume_actual[muscle_key] = total

    # Get weekly volume target from volume_week
    weekly_volume_target = volume_week.weekly_totals

    # Calculate volume adherence
    volume_adherence = {}
    for muscle_key in weekly_volume_target:
        target = weekly_volume_target[muscle_key]
        actual = weekly_volume_actual.get(muscle_key, 0)
        if target > 0:
            volume_adherence[muscle_key] = actual / target
        else:
            volume_adherence[muscle_key] = 1.0 if actual == 0 else 0.0

    # Validate volume adherence for non-deload weeks
    if not week_profile.is_deload:
        for muscle_key, actual in weekly_volume_actual.items():
            target = weekly_volume_target.get(muscle_key, 0)
            diff = abs(actual - target)
            if diff > 2 and target > 0:
                print(f"⚠️  Week {week_profile.week_number} {muscle_key}: "
                      f"{actual:.1f} delivered vs {target} target (diff: {diff:+.1f})")

    return BuiltWeek(
        week_number=week_profile.week_number,
        mesocycle=week_profile.mesocycle_number,
        phase=week_profile.phase_name,
        phase_name=week_profile.phase_name,
        workouts=workouts,
        weekly_volume_actual=weekly_volume_actual,
        weekly_volume_target=weekly_volume_target,
        volume_adherence=volume_adherence,
    )


def _build_session(
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    week_profile,
    session_template,
    volume_target,
    available_exercises: list[Exercise],
    recently_used: dict[str, list],
    day_number: int,
    week_exercises_used: set[str] = None,
    mrv_limits: dict[str, int] = None,
    mav_limits: dict[str, int] = None,
    weekly_volume_delivered: dict[str, float] = None,
) -> BuiltWorkout:
    """
    Build a single session using the 3-phase greedy algorithm.

    Phase 1: Fill required movement patterns with compounds
    Phase 2: Fill remaining volume with isolations/accessories
    Phase 2.5: Fill time budget (add exercises/sets to reach 60 min)
    Phase 3: Validate and patch (ensure minimum exercise count)
    """
    selected_exercises = []  # List of (Exercise, sets_count)

    # Initialize optional parameters
    week_exercises_used = week_exercises_used or set()
    mrv_limits = mrv_limits or {}
    mav_limits = mav_limits or {}
    weekly_volume_delivered = weekly_volume_delivered or {}

    # BUG 2 FIX: Initialize remaining_volume with ALL muscles at their target
    # or 0 if not targeted. This ensures secondary contributions are tracked.
    remaining_volume = {}
    for muscle in MuscleGroup:
        muscle_key = muscle.value
        remaining_volume[muscle_key] = float(volume_target.muscle_volumes.get(muscle_key, 0))

    remaining_patterns = copy.deepcopy(volume_target.movement_pattern_requirements)

    # POWER PROGRAM FIX: Inject power patterns for ALL sessions in power programs
    # This ensures every session gets power/plyometric exercises during Phase 1
    if profile.training_goal == "power":
        # Determine which power pattern to add based on session type
        session_type = session_template.session_type.lower()
        if any(x in session_type for x in ["upper", "push", "pull"]):
            # Upper body session - add power_upper if not already present
            if MovementPattern.POWER_UPPER.value not in remaining_patterns:
                remaining_patterns[MovementPattern.POWER_UPPER.value] = 2  # Need 2 power exercises
        if any(x in session_type for x in ["lower", "leg", "full"]):
            # Lower body session - add power_lower if not already present
            if MovementPattern.POWER_LOWER.value not in remaining_patterns:
                remaining_patterns[MovementPattern.POWER_LOWER.value] = 2  # Need 2 power exercises

    axial_count = 0
    grip_count = 0

    # Difficulty cap by training level
    difficulty_cap = {"beginner": 3, "intermediate": 4, "advanced": 5}[profile.training_level]

    # Get session muscle groups as a set for eligibility filtering (BUG 2 FIX)
    session_muscle_groups = set(m.value for m in session_template.muscle_groups)

    # BUG 2 FIX: Helper to check if exercise is eligible for this session
    def is_exercise_eligible_for_session(exercise: Exercise) -> bool:
        """
        An exercise is eligible for a session only if at least one of its
        PRIMARY muscles is in the session template's muscle_groups.
        This prevents upper body exercises on lower days and vice versa.
        """
        exercise_primary_muscles = set(
            ma.muscle.value for ma in exercise.muscle_activations
            if ma.role == MuscleRole.PRIMARY
        )
        return bool(exercise_primary_muscles & session_muscle_groups)

    # FIX MRV: Helper to check if adding sets would exceed MRV
    def would_exceed_mrv(exercise: Exercise, sets: int) -> bool:
        """Check if adding this exercise would cause any muscle to exceed MRV.
        Uses >= to ensure we stay STRICTLY under MRV (not at MRV).
        """
        for ma in exercise.muscle_activations:
            muscle_key = ma.muscle.value
            mrv = mrv_limits.get(muscle_key, 999)
            current_weekly = weekly_volume_delivered.get(muscle_key, 0)
            # Add volume from exercises already selected in this session
            for ex, s in selected_exercises:
                for ma2 in ex.muscle_activations:
                    if ma2.muscle.value == muscle_key:
                        current_weekly += s * ma2.volume_credit
            # Add the proposed volume
            proposed_total = current_weekly + sets * ma.volume_credit
            # Use >= to stay strictly UNDER MRV (MRV is the ceiling, not a target)
            if proposed_total >= mrv:
                return True
        return False

    # FIX 2: Helper to compute variety penalty for same-week exercises
    def get_week_variety_penalty(exercise: Exercise) -> float:
        """Return penalty for exercises already used in other sessions this week."""
        penalty = 0.0
        if exercise.id in week_exercises_used:
            # Strong penalty for exact same exercise in another session this week
            penalty -= 50.0
        # Check rotation group
        for ex in EXERCISE_LIBRARY:
            if ex.id in week_exercises_used and ex.rotation_group == exercise.rotation_group and ex.id != exercise.id:
                # Same rotation group used this week - penalize to encourage variety
                penalty -= 30.0
                break
        return penalty

    # ── PHASE 1: Fill required movement patterns with COMPOUNDS ──

    pattern_priority = get_pattern_fill_priority(profile.training_goal)

    # BUG 3 FIX: Track which patterns are REQUIRED vs optional
    required_patterns_from_template = set(
        p.value for p in session_template.required_movement_patterns
    )

    # POWER PROGRAM FIX: Add injected power patterns as required
    if profile.training_goal == "power":
        session_type = session_template.session_type.lower()
        if any(x in session_type for x in ["upper", "push", "pull"]):
            required_patterns_from_template.add(MovementPattern.POWER_UPPER.value)
        if any(x in session_type for x in ["lower", "leg", "full"]):
            required_patterns_from_template.add(MovementPattern.POWER_LOWER.value)

    patterns_filled: set[str] = set()

    # Wrap pattern filling in a loop to handle patterns needing multiple exercises (e.g., power_lower=2)
    max_exercises = session_template.max_exercises
    made_progress = True
    while made_progress and len(selected_exercises) < max_exercises:
        made_progress = False
        for pattern in pattern_priority:
            pattern_key = pattern.value
            if pattern_key not in remaining_patterns or remaining_patterns[pattern_key] <= 0:
                continue

            # Get candidate exercises for this pattern
            candidates = []

            # Check if this is an isolation pattern - these should allow isolation exercises
            is_isolation_pattern = pattern in [MovementPattern.ISOLATION_PUSH, MovementPattern.ISOLATION_PULL]

            for ex in available_exercises:
                # Must match pattern
                if ex.movement_pattern != pattern:
                    continue

                # For isolation patterns (like ISOLATION_PUSH/PULL), allow ISOLATION exercises
                if is_isolation_pattern:
                    if ex.exercise_type != ExerciseType.ISOLATION:
                        continue
                else:
                    # BUG 1 FIX: Phase 1 ONLY allows heavy_compound and light_compound for non-isolation patterns
                    # No isolations, no bodyweight-only in Phase 1
                    if ex.exercise_type not in [
                        ExerciseType.HEAVY_COMPOUND,
                        ExerciseType.LIGHT_COMPOUND,
                    ]:
                        # Exception: allow POWER and PLYOMETRIC for power patterns
                        if ex.exercise_type in [ExerciseType.POWER, ExerciseType.PLYOMETRIC]:
                            if pattern not in [MovementPattern.POWER_LOWER, MovementPattern.POWER_UPPER]:
                                continue
                        else:
                            continue

                # Not already selected
                if any(s[0].id == ex.id for s in selected_exercises):
                    continue

                # Difficulty check
                if ex.difficulty > difficulty_cap:
                    continue

                # Proficiency check
                if ex.requires_proficiency and profile.training_level == "beginner":
                    continue

                # BUG 2 FIX: Exercise must be eligible for this session type
                if not is_exercise_eligible_for_session(ex):
                    continue

                candidates.append(ex)

            # BUG 3 FIX: Check if this is a REQUIRED pattern
            is_required_pattern = pattern_key in required_patterns_from_template

            if not candidates:
                if is_required_pattern:
                    print(f"⚠️  WARNING: No compound candidates found for REQUIRED pattern {pattern_key} in {session_template.day_label}")
                continue

            # Score all candidates with COMPOUND PRIORITY BONUS (BUG 1 FIX)
            for candidate in candidates:
                base_score = compute_exercise_score(
                    exercise=candidate,
                    remaining_volume=remaining_volume,
                    recently_used=recently_used,
                    mesocycle_number=week_profile.mesocycle_number,
                    week_number=week_profile.week_number,
                    session_axial_count=axial_count,
                    session_grip_count=grip_count,
                    program_goal=profile.training_goal,
                    user_preferences=profile.exercises_to_include,
                    vbt_enabled=strategy.vbt_enabled,
                    training_level=profile.training_level,
                    is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
                )

                # BUG 1 FIX: Add compound priority bonuses for Phase 1
                bonus = 0
                if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                    bonus += 40  # Heavy compounds are king
                elif candidate.exercise_type == ExerciseType.LIGHT_COMPOUND:
                    bonus += 20  # Light compounds are still preferred

                # BUG 1 FIX: Bonus for barbell exercises (foundation of serious programs)
                if "barbell" in candidate.id.lower() or "barbell" in candidate.name.lower():
                    bonus += 25  # Increased from 15

                # BUG 4 FIX: Penalty for bodyweight-only exercises in Phase 1
                # We want barbell/weighted compounds, not bodyweight squats or push-ups
                if "bodyweight" in candidate.id.lower() or "bodyweight" in candidate.name.lower():
                    bonus -= 35  # Strong penalty to deprioritize

                # BUG 4 FIX: Extra bonus for foundation movement patterns
                # These are the "big 4" movements that should anchor any serious program
                if pattern in [MovementPattern.SQUAT, MovementPattern.HIP_HINGE]:
                    # Lower body foundation - prefer barbell squat/deadlift variations
                    if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                        bonus += 20
                elif pattern in [MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL]:
                    # Upper body foundation - prefer bench/row variations
                    if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                        bonus += 15

                # FIX 2: Apply same-week variety penalty
                bonus += get_week_variety_penalty(candidate)

                candidate._score = base_score + bonus

            # Select highest-scoring that doesn't exceed MRV
            candidates.sort(key=lambda x: -x._score)

            best = None
            sets = 0
            for candidate in candidates:
                # Try to find a valid set count for this candidate
                primary_muscles = [
                    ma.muscle.value for ma in candidate.muscle_activations
                    if ma.role == MuscleRole.PRIMARY
                ]
                if primary_muscles:
                    max_needed = max(remaining_volume.get(m, 0) for m in primary_muscles)
                else:
                    max_needed = 3

                # Determine initial set count
                if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                    candidate_sets = min(candidate.max_sets_per_session, max(3, round(max_needed)))
                elif candidate.exercise_type == ExerciseType.LIGHT_COMPOUND:
                    candidate_sets = min(candidate.max_sets_per_session, max(3, round(max_needed)))
                else:
                    candidate_sets = min(candidate.max_sets_per_session, max(candidate.min_sets_per_session, round(max_needed)))

                # Cap at 4 sets per exercise to encourage variety
                candidate_sets = min(candidate_sets, 4)

                # BUG 4 FIX: Determine minimum sets floor based on exercise type
                # Heavy compounds MUST get at least 3 sets to be effective
                if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                    min_sets_floor = 3
                else:
                    min_sets_floor = 2

                # FIX MRV: Reduce sets if they would exceed MRV, but respect floor
                while candidate_sets > min_sets_floor and would_exceed_mrv(candidate, candidate_sets):
                    candidate_sets -= 1

                # BUG 4 FIX: For heavy compounds, accept even if slightly over MRV
                # (the volume is worth the extra fatigue for foundation exercises)
                if candidate.exercise_type == ExerciseType.HEAVY_COMPOUND:
                    # Accept the heavy compound at minimum 3 sets
                    best = candidate
                    sets = max(candidate_sets, 3)
                    break
                elif not would_exceed_mrv(candidate, candidate_sets):
                    best = candidate
                    sets = candidate_sets
                    break

            # BUG 3 FIX: For REQUIRED patterns, we MUST select something even if MRV exceeded
            if best is None:
                if is_required_pattern and candidates:
                    # Force-select the best scoring candidate with minimum sets
                    best = candidates[0]  # Already sorted by score
                    sets = 3  # Minimum viable sets for a compound
                    print(f"⚠️  Force-selecting {best.name} for REQUIRED pattern {pattern_key} (MRV may be exceeded)")
                else:
                    continue  # Skip optional patterns if all candidates exceed MRV

            # Track that we filled this pattern
            patterns_filled.add(pattern_key)

            # BUG 2 FIX: Update remaining volume for ALL muscles (including secondary)
            for ma in best.muscle_activations:
                muscle_key = ma.muscle.value
                credit = sets * ma.volume_credit
                remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit

            # Update counters
            if best.is_axial_loading:
                axial_count += 1
            if best.grip_intensive:
                grip_count += 1

            remaining_patterns[pattern_key] -= 1
            made_progress = True  # We added an exercise, try again for any remaining pattern needs

            selected_exercises.append((best, sets))

    # BUG 3 FIX: Post-Phase-1 assertion - verify all required patterns were filled
    missing_required = required_patterns_from_template - patterns_filled
    if missing_required:
        print(f"⚠️  PHASE 1 WARNING: Missing required patterns {missing_required} in {session_template.day_label}")
        # Note: We don't assert here because some edge cases may legitimately have
        # no eligible exercises (e.g., equipment limitations). The warning is enough.

    # ── PHASE 2: Fill remaining volume with isolations/accessories ──

    max_exercises = session_template.max_exercises
    session_time_cap = session_template.max_duration_minutes
    min_exercises = 5  # BUG 3 FIX: Minimum exercise floor

    while len(selected_exercises) < max_exercises:
        # BUG 2 FIX: Find muscles still needing volume (> 0, not > 1.0)
        # Also skip muscles that are already over-delivered
        muscles_needing_volume = {
            m: v for m, v in remaining_volume.items()
            if v > 0.5  # Allow filling even small deficits
        }

        # BUG 3 FIX: If we haven't hit minimum exercises, keep going even with no deficits
        if not muscles_needing_volume and len(selected_exercises) >= min_exercises:
            break

        # Sort by most deficit first
        sorted_muscles = sorted(
            muscles_needing_volume.keys(),
            key=lambda m: -remaining_volume[m]
        ) if muscles_needing_volume else []

        best_candidate = None
        best_score = -999999
        best_muscle = None

        # BUG 3 FIX: If no volume deficit but need more exercises, expand search
        if not sorted_muscles and len(selected_exercises) < min_exercises:
            # Look for any accessory that adds value
            sorted_muscles = [m for m in remaining_volume.keys()
                             if any(volume_target.muscle_volumes.get(m, 0) > 0
                                   for m in remaining_volume.keys())]

        for muscle in sorted_muscles:
            # Get candidates for this muscle
            candidates = []
            for ex in available_exercises:
                # Must have this muscle as primary
                if not any(
                    ma.muscle.value == muscle and ma.role == MuscleRole.PRIMARY
                    for ma in ex.muscle_activations
                ):
                    continue

                # Phase 2: prefer isolations, also allow light compounds
                if ex.exercise_type not in [
                    ExerciseType.ISOLATION,
                    ExerciseType.LIGHT_COMPOUND,
                ]:
                    continue

                # Not already selected
                if any(s[0].id == ex.id for s in selected_exercises):
                    continue

                # Difficulty check
                if ex.difficulty > difficulty_cap:
                    continue

                # BUG 2 FIX: Exercise must be eligible for this session type
                if not is_exercise_eligible_for_session(ex):
                    continue

                # Redundant pairing check (e.g., bodyweight squat after barbell squat)
                if is_blocked_pairing(ex.id, selected_exercises):
                    continue

                candidates.append(ex)

            if not candidates:
                continue

            # Score candidates (no compound bonus in Phase 2)
            for candidate in candidates:
                score = compute_exercise_score(
                    exercise=candidate,
                    remaining_volume=remaining_volume,
                    recently_used=recently_used,
                    mesocycle_number=week_profile.mesocycle_number,
                    week_number=week_profile.week_number,
                    session_axial_count=axial_count,
                    session_grip_count=grip_count,
                    program_goal=profile.training_goal,
                    user_preferences=profile.exercises_to_include,
                    vbt_enabled=strategy.vbt_enabled,
                    training_level=profile.training_level,
                    is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
                )

                # FIX 2: Apply same-week variety penalty
                score += get_week_variety_penalty(candidate)

                # FIX MRV: Skip candidates that would exceed MRV
                if would_exceed_mrv(candidate, 2):
                    score -= 1000  # Heavy penalty to deprioritize

                if score > best_score:
                    best_score = score
                    best_candidate = candidate
                    best_muscle = muscle

        if not best_candidate:
            break

        # FIX MRV: Skip if best candidate would exceed MRV
        if would_exceed_mrv(best_candidate, 2):
            # Mark this muscle as done and continue
            remaining_volume[best_muscle] = 0
            continue

        # Determine sets for isolations/accessories
        needed = max(remaining_volume.get(best_muscle, 0), 2)  # At least 2 sets
        sets = min(
            best_candidate.max_sets_per_session,
            max(best_candidate.min_sets_per_session, round(needed))
        )
        # Cap isolation sets at 3 to encourage variety
        if best_candidate.exercise_type == ExerciseType.ISOLATION:
            sets = min(sets, 3)

        # FIX MRV: Reduce sets if they would exceed MRV
        while sets > 1 and would_exceed_mrv(best_candidate, sets):
            sets -= 1

        if would_exceed_mrv(best_candidate, sets):
            # Can't add even 1 set without exceeding MRV
            remaining_volume[best_muscle] = 0
            continue

        # BUG 2 FIX: Update remaining volume for ALL muscles
        for ma in best_candidate.muscle_activations:
            muscle_key = ma.muscle.value
            credit = sets * ma.volume_credit
            remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit

        selected_exercises.append((best_candidate, sets))

        # Check if we're approaching time cap (but allow minimum exercises)
        estimated_sets = sum(s for _, s in selected_exercises)
        if estimated_sets * 3.5 > session_time_cap and len(selected_exercises) >= min_exercises:
            break

    # ── PHASE 2 BICEP CHECK: Ensure minimum bicep volume for hypertrophy ──
    # Biceps are essential for hypertrophy programs - enforce a minimum floor
    if profile.training_goal == "hypertrophy" and "biceps" in session_muscle_groups:
        # Calculate bicep volume delivered so far in this session
        session_bicep_volume = 0.0
        for ex, s in selected_exercises:
            for ma in ex.muscle_activations:
                if ma.muscle.value == "biceps":
                    session_bicep_volume += s * ma.volume_credit

        # Weekly bicep volume from previous sessions
        weekly_bicep_volume = weekly_volume_delivered.get("biceps", 0) + session_bicep_volume

        # Minimum bicep sets per week for hypertrophy (4-6 sets)
        MIN_BICEP_SETS_HYPERTROPHY = 6
        num_upper_sessions = sum(1 for sess in strategy.split.sessions_per_week
                                  if "biceps" in [m.value for m in sess.muscle_groups])
        min_bicep_per_session = MIN_BICEP_SETS_HYPERTROPHY / max(num_upper_sessions, 1)

        # If this session is under the per-session floor, force-add a bicep isolation
        if session_bicep_volume < min_bicep_per_session and len(selected_exercises) < max_exercises:
            # Find best bicep isolation
            best_bicep = None
            best_bicep_score = -999999
            for ex in available_exercises:
                if any(s[0].id == ex.id for s in selected_exercises):
                    continue
                if ex.exercise_type != ExerciseType.ISOLATION:
                    continue
                if ex.difficulty > difficulty_cap:
                    continue
                # Must have biceps as primary
                if not any(ma.muscle.value == "biceps" and ma.role == MuscleRole.PRIMARY
                          for ma in ex.muscle_activations):
                    continue
                if not is_exercise_eligible_for_session(ex):
                    continue
                if would_exceed_mrv(ex, 2):
                    continue
                if is_blocked_pairing(ex.id, selected_exercises):
                    continue

                score = compute_exercise_score(
                    exercise=ex,
                    remaining_volume=remaining_volume,
                    recently_used=recently_used,
                    mesocycle_number=week_profile.mesocycle_number,
                    week_number=week_profile.week_number,
                    session_axial_count=axial_count,
                    session_grip_count=grip_count,
                    program_goal=profile.training_goal,
                    user_preferences=profile.exercises_to_include,
                    vbt_enabled=strategy.vbt_enabled,
                    training_level=profile.training_level,
                    is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
                )
                score += get_week_variety_penalty(ex)

                if score > best_bicep_score:
                    best_bicep_score = score
                    best_bicep = ex

            if best_bicep:
                # Add 2-3 sets of the bicep isolation
                bicep_sets = min(3, best_bicep.max_sets_per_session)
                while bicep_sets > 1 and would_exceed_mrv(best_bicep, bicep_sets):
                    bicep_sets -= 1

                if not would_exceed_mrv(best_bicep, bicep_sets):
                    selected_exercises.append((best_bicep, bicep_sets))
                    for ma in best_bicep.muscle_activations:
                        muscle_key = ma.muscle.value
                        credit = bicep_sets * ma.volume_credit
                        remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit

    # ── PHASE 2.6: Goal-specific exercise type enforcement ──
    # Power programs: minimum 2 power/plyometric exercises per session (NSCA guidelines)
    # Strength programs: minimum 2 heavy compound exercises per session
    GOAL_TYPE_MINIMUMS = {
        "power": {
            "types": {ExerciseType.POWER, ExerciseType.PLYOMETRIC},
            "min_per_session": 2,
        },
        "strength": {
            "types": {ExerciseType.HEAVY_COMPOUND},
            "min_per_session": 2,
        },
    }

    if profile.training_goal in GOAL_TYPE_MINIMUMS:
        config = GOAL_TYPE_MINIMUMS[profile.training_goal]
        required_types = config["types"]
        min_required = config["min_per_session"]

        # Count current exercises of required types
        current_type_count = sum(
            1 for ex, _ in selected_exercises
            if ex.exercise_type in required_types
        )

        # Add more exercises of required type if under minimum
        while current_type_count < min_required and len(selected_exercises) < max_exercises:
            best_candidate = None
            best_score = -999999

            for ex in available_exercises:
                # Skip already selected
                if any(s[0].id == ex.id for s in selected_exercises):
                    continue
                # Must be of required type
                if ex.exercise_type not in required_types:
                    continue
                # Check difficulty cap
                if ex.difficulty > difficulty_cap:
                    continue
                # Must be eligible for this session type
                if not is_exercise_eligible_for_session(ex):
                    continue
                # Check MRV limits
                if would_exceed_mrv(ex, 2):
                    continue
                # Check blocked pairings
                if is_blocked_pairing(ex.id, selected_exercises):
                    continue

                score = compute_exercise_score(
                    exercise=ex,
                    remaining_volume=remaining_volume,
                    recently_used=recently_used,
                    mesocycle_number=week_profile.mesocycle_number,
                    week_number=week_profile.week_number,
                    session_axial_count=axial_count,
                    session_grip_count=grip_count,
                    program_goal=profile.training_goal,
                    user_preferences=profile.exercises_to_include,
                    vbt_enabled=strategy.vbt_enabled,
                    training_level=profile.training_level,
                    is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
                )
                score += get_week_variety_penalty(ex)

                if score > best_score:
                    best_score = score
                    best_candidate = ex

            if best_candidate:
                # Add 2-3 sets of the exercise
                add_sets = min(3, best_candidate.max_sets_per_session)
                while add_sets > 1 and would_exceed_mrv(best_candidate, add_sets):
                    add_sets -= 1

                if not would_exceed_mrv(best_candidate, add_sets):
                    selected_exercises.append((best_candidate, add_sets))
                    for ma in best_candidate.muscle_activations:
                        muscle_key = ma.muscle.value
                        credit = add_sets * ma.volume_credit
                        remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit
                    # Update axial/grip counts
                    if best_candidate.is_axial_loading:
                        axial_count += 1
                    if best_candidate.grip_intensive:
                        grip_count += 1
                    current_type_count += 1
            else:
                # No more candidates available
                break

    # ── PHASE 2.5: Fill time budget ──
    # FIX 1: If session duration is under target, add more volume up to MAV
    target_duration = session_template.max_duration_minutes
    min_target_duration = target_duration - 10  # e.g., 50 min for 60 min target

    # Build a temporary prescription to estimate duration
    def estimate_current_duration() -> int:
        temp_exercises = []
        for idx, (exercise, sets) in enumerate(selected_exercises):
            sets_list = prescribe_exercise(
                exercise=exercise,
                total_sets=sets,
                week_profile=week_profile,
                program_goal=profile.training_goal,
                vbt_enabled=strategy.vbt_enabled,
                vbt_protocol=strategy.vbt_protocol,
            )
            muscle_contributions = {}
            for ma in exercise.muscle_activations:
                muscle_contributions[ma.muscle.value] = sets * ma.volume_credit
            temp_ex = PrescribedExercise(
                exercise_id=exercise.id,
                exercise_name=exercise.name,
                exercise_type=exercise.exercise_type,
                movement_pattern=exercise.movement_pattern,
                sets=sets_list,
                total_sets=sets,
                muscle_contributions=muscle_contributions,
                superset_group=None,
                order_in_session=idx + 1,
                rationale="",
                vbt_eligible=exercise.vbt_eligible,
            )
            temp_exercises.append(temp_ex)
        return estimate_session_duration(temp_exercises)

    current_duration = estimate_current_duration()

    # Step 1: Add exercises for muscles below MAV (if under time)
    while current_duration < min_target_duration and len(selected_exercises) < max_exercises:
        # Find muscles below MAV that have room for more volume
        muscles_below_mav = []
        for muscle_key in volume_target.muscle_volumes:
            # Calculate current weekly volume for this muscle
            current_weekly = weekly_volume_delivered.get(muscle_key, 0)
            for ex, s in selected_exercises:
                for ma in ex.muscle_activations:
                    if ma.muscle.value == muscle_key:
                        current_weekly += s * ma.volume_credit
            mav = mav_limits.get(muscle_key, 999)
            mrv = mrv_limits.get(muscle_key, 999)
            if current_weekly < mav and current_weekly < mrv - 2:  # Room to add more
                muscles_below_mav.append((muscle_key, mav - current_weekly))

        if not muscles_below_mav:
            break

        # Sort by most room to grow
        muscles_below_mav.sort(key=lambda x: -x[1])
        target_muscle = muscles_below_mav[0][0]

        # Find best isolation for this muscle
        best_candidate = None
        best_score = -999999
        for ex in available_exercises:
            if any(s[0].id == ex.id for s in selected_exercises):
                continue
            if ex.exercise_type not in [ExerciseType.ISOLATION, ExerciseType.LIGHT_COMPOUND]:
                continue
            if ex.difficulty > difficulty_cap:
                continue
            if not any(ma.muscle.value == target_muscle for ma in ex.muscle_activations):
                continue
            # BUG 2 FIX: Exercise must be eligible for this session type
            if not is_exercise_eligible_for_session(ex):
                continue
            # Check MRV
            if would_exceed_mrv(ex, 2):
                continue
            # Redundant pairing check
            if is_blocked_pairing(ex.id, selected_exercises):
                continue

            score = compute_exercise_score(
                exercise=ex,
                remaining_volume=remaining_volume,
                recently_used=recently_used,
                mesocycle_number=week_profile.mesocycle_number,
                week_number=week_profile.week_number,
                session_axial_count=axial_count,
                session_grip_count=grip_count,
                program_goal=profile.training_goal,
                user_preferences=profile.exercises_to_include,
                vbt_enabled=strategy.vbt_enabled,
                training_level=profile.training_level,
                is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
            )
            score += get_week_variety_penalty(ex)

            if score > best_score:
                best_score = score
                best_candidate = ex

        if not best_candidate:
            break

        # Add with 2-3 sets
        sets = 3 if best_candidate.exercise_type == ExerciseType.ISOLATION else 2
        while sets > 1 and would_exceed_mrv(best_candidate, sets):
            sets -= 1

        if would_exceed_mrv(best_candidate, sets):
            break

        selected_exercises.append((best_candidate, sets))
        for ma in best_candidate.muscle_activations:
            muscle_key = ma.muscle.value
            credit = sets * ma.volume_credit
            remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit

        current_duration = estimate_current_duration()

    # Step 2: If still under time and all muscles are at/above MAV, add sets to existing exercises
    while current_duration < min_target_duration:
        # Find exercises that can have more sets added (prefer high-SFR isolations)
        best_idx = None
        best_score = -999999
        for idx, (ex, sets) in enumerate(selected_exercises):
            if sets >= ex.max_sets_per_session:
                continue
            # Check if adding a set would exceed MRV
            test_selected = selected_exercises.copy()
            test_selected[idx] = (ex, sets + 1)
            would_exceed = False
            for ma in ex.muscle_activations:
                muscle_key = ma.muscle.value
                mrv = mrv_limits.get(muscle_key, 999)
                current_weekly = weekly_volume_delivered.get(muscle_key, 0)
                for tex, ts in test_selected:
                    for tma in tex.muscle_activations:
                        if tma.muscle.value == muscle_key:
                            current_weekly += ts * tma.volume_credit
                if current_weekly > mrv:
                    would_exceed = True
                    break
            if would_exceed:
                continue

            # Score: prefer isolations with high SFR
            score = ex.sfr_rating * 10
            if ex.exercise_type == ExerciseType.ISOLATION:
                score += 20
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is None:
            break

        # Add one set
        ex, sets = selected_exercises[best_idx]
        selected_exercises[best_idx] = (ex, sets + 1)
        current_duration = estimate_current_duration()

    # ── PHASE 3: Validate and patch ──

    # BUG 3 FIX: If still under minimum exercises, force-add more
    while len(selected_exercises) < min_exercises:
        # Find muscle with most remaining volume (even if negative, find least over-delivered)
        best_muscle = max(remaining_volume.keys(),
                         key=lambda m: remaining_volume.get(m, -999))

        # Find any isolation for this muscle
        best_candidate = None
        best_score = -999999
        for ex in available_exercises:
            if any(s[0].id == ex.id for s in selected_exercises):
                continue
            if ex.exercise_type != ExerciseType.ISOLATION:
                continue
            if ex.difficulty > difficulty_cap:
                continue

            # BUG 2 FIX: Exercise must be eligible for this session type
            if not is_exercise_eligible_for_session(ex):
                continue

            # FIX MRV: Skip exercises that would exceed MRV
            if would_exceed_mrv(ex, ex.min_sets_per_session):
                continue

            # Redundant pairing check
            if is_blocked_pairing(ex.id, selected_exercises):
                continue

            # Check if it has the target muscle or any session muscle
            has_target = any(ma.muscle.value == best_muscle for ma in ex.muscle_activations)
            has_session_muscle = any(ma.muscle.value in volume_target.muscle_volumes
                                    for ma in ex.muscle_activations)
            if has_target or has_session_muscle:
                score = compute_exercise_score(
                    exercise=ex,
                    remaining_volume=remaining_volume,
                    recently_used=recently_used,
                    mesocycle_number=week_profile.mesocycle_number,
                    week_number=week_profile.week_number,
                    session_axial_count=axial_count,
                    session_grip_count=grip_count,
                    program_goal=profile.training_goal,
                    user_preferences=profile.exercises_to_include,
                    vbt_enabled=strategy.vbt_enabled,
                    training_level=profile.training_level,
                    is_in_season=profile.training_season is not None and profile.training_season.value == "in_season",
                )
                # FIX 2: Apply same-week variety penalty
                score += get_week_variety_penalty(ex)

                if score > best_score:
                    best_score = score
                    best_candidate = ex

        if not best_candidate:
            break  # Can't find any more exercises

        sets = best_candidate.min_sets_per_session
        # FIX MRV: Double-check and reduce if needed
        while sets > 1 and would_exceed_mrv(best_candidate, sets):
            sets -= 1
        if would_exceed_mrv(best_candidate, sets):
            break  # Can't add without exceeding MRV

        for ma in best_candidate.muscle_activations:
            muscle_key = ma.muscle.value
            credit = sets * ma.volume_credit
            remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit
        selected_exercises.append((best_candidate, sets))

    # Check for muscles still significantly short (>2 sets) and patch
    for muscle, remaining in list(remaining_volume.items()):
        if remaining > 2.0:
            # Try adding sets to an existing exercise that hits this muscle
            for idx, (ex, sets) in enumerate(selected_exercises):
                if any(ma.muscle.value == muscle for ma in ex.muscle_activations):
                    if sets < ex.max_sets_per_session:
                        add = min(
                            ex.max_sets_per_session - sets,
                            round(remaining)
                        )
                        # FIX MRV: Check if adding sets would exceed MRV
                        while add > 0:
                            test_selected = selected_exercises.copy()
                            test_selected[idx] = (ex, sets + add)
                            would_exceed = False
                            for ma in ex.muscle_activations:
                                muscle_key = ma.muscle.value
                                mrv = mrv_limits.get(muscle_key, 999)
                                current_weekly = weekly_volume_delivered.get(muscle_key, 0)
                                for tex, ts in test_selected:
                                    for tma in tex.muscle_activations:
                                        if tma.muscle.value == muscle_key:
                                            current_weekly += ts * tma.volume_credit
                                if current_weekly >= mrv:
                                    would_exceed = True
                                    break
                            if not would_exceed:
                                break
                            add -= 1

                        if add <= 0:
                            continue  # Can't add sets without exceeding MRV

                        selected_exercises[idx] = (ex, sets + add)

                        # Update remaining volume
                        for ma in ex.muscle_activations:
                            muscle_key = ma.muscle.value
                            credit = add * ma.volume_credit
                            remaining_volume[muscle_key] = remaining_volume.get(muscle_key, 0) - credit
                        break

    # Detect if session is time-constrained (for set type selection)
    session_time_limited = (
        profile.session_duration_minutes <= 45
        or (profile.training_season == TrainingSeason.IN_SEASON)
    )

    # Prescribe exercises
    prescribed_exercises = []
    for idx, (exercise, sets) in enumerate(selected_exercises):
        sets_list = prescribe_exercise(
            exercise=exercise,
            total_sets=sets,
            week_profile=week_profile,
            program_goal=profile.training_goal,
            vbt_enabled=strategy.vbt_enabled,
            vbt_protocol=strategy.vbt_protocol,
            training_level=profile.training_level,
            session_duration_limited=session_time_limited,
        )

        # Calculate muscle contributions
        muscle_contributions = {}
        for ma in exercise.muscle_activations:
            muscle_contributions[ma.muscle.value] = sets * ma.volume_credit

        prescribed_ex = PrescribedExercise(
            exercise_id=exercise.id,
            exercise_name=exercise.name,
            exercise_type=exercise.exercise_type,
            movement_pattern=exercise.movement_pattern,
            sets=sets_list,
            total_sets=sets,
            muscle_contributions=muscle_contributions,
            superset_group=None,
            order_in_session=idx + 1,
            rationale="",
            vbt_eligible=exercise.vbt_eligible,
        )

        prescribed_exercises.append(prescribed_ex)

    # Sort exercises
    prescribed_exercises = sort_exercises_for_session(
        prescribed_exercises,
        profile.training_goal,
    )

    # Build supersets for hypertrophy
    if profile.training_goal == "hypertrophy":
        prescribed_exercises = build_supersets(
            prescribed_exercises,
            profile.training_goal,
        )

    # Check time cap and remove exercises if needed
    estimated_duration = estimate_session_duration(prescribed_exercises)
    max_time = session_time_cap * 1.1  # 10% grace

    while estimated_duration > max_time and len(prescribed_exercises) > 4:
        # Remove the last exercise (lowest priority, likely an isolation)
        removed = prescribed_exercises.pop()
        estimated_duration = estimate_session_duration(prescribed_exercises)

    # Calculate total sets and volume delivered
    total_sets = sum(ex.total_sets for ex in prescribed_exercises)

    volume_delivered = {}
    for ex in prescribed_exercises:
        for muscle, contribution in ex.muscle_contributions.items():
            volume_delivered[muscle] = volume_delivered.get(muscle, 0) + contribution

    # V6: Generate structured warm-up protocol
    warmup_protocol = _generate_warmup_protocol(
        prescribed_exercises=prescribed_exercises,
        session_template=session_template,
        profile=profile,
    )

    return BuiltWorkout(
        day_number=day_number,
        day_label=session_template.day_label,
        session_type=session_template.session_type,
        exercises=prescribed_exercises,
        total_sets=total_sets,
        estimated_duration_minutes=estimated_duration,
        volume_check=volume_delivered,
        volume_delivered=volume_delivered,
        warmup_notes=_warmup_protocol_to_notes(warmup_protocol),
        warmup_protocol=warmup_protocol,
    )


# ─────────────────────────────────────────────────────────────────────────────
# V6: WARM-UP PROTOCOL GENERATION
# ─────────────────────────────────────────────────────────────────────────────

# Dynamic stretches mapped by movement pattern
_DYNAMIC_STRETCHES_BY_PATTERN = {
    MovementPattern.SQUAT: [
        "Bodyweight squats × 10",
        "Hip circles × 10 each direction",
        "Walking knee hugs × 8 each leg",
    ],
    MovementPattern.HIP_HINGE: [
        "Hip hinges with dowel × 10",
        "Leg swings (front-back) × 10 each leg",
        "Inchworms × 6",
    ],
    MovementPattern.HORIZONTAL_PUSH: [
        "Arm circles × 10 each direction",
        "Band pull-aparts × 15",
        "Push-up to downward dog × 6",
    ],
    MovementPattern.HORIZONTAL_PULL: [
        "Band pull-aparts × 15",
        "Cat-cow stretches × 8",
        "Scapular push-ups × 10",
    ],
    MovementPattern.VERTICAL_PUSH: [
        "Arm circles × 10 each direction",
        "Wall slides × 10",
        "Band dislocates × 10",
    ],
    MovementPattern.VERTICAL_PULL: [
        "Dead hangs × 15-20 seconds",
        "Scapular pull-ups × 8",
        "Band pull-aparts × 15",
    ],
    MovementPattern.LUNGE: [
        "Walking lunges (bodyweight) × 8 each leg",
        "Lateral lunges × 6 each side",
        "Hip flexor stretch (dynamic) × 8 each leg",
    ],
    MovementPattern.POWER_LOWER: [
        "Pogo hops × 15",
        "Bodyweight squat jumps × 6",
        "Ankle bounces × 15",
    ],
    MovementPattern.POWER_UPPER: [
        "Medicine ball slams (or explosive push-ups) × 6",
        "Arm circles (fast) × 15 each direction",
    ],
    MovementPattern.CORE: [
        "Dead bugs × 8 each side",
        "Bird dogs × 8 each side",
    ],
}

# Activation exercises by muscle group
_ACTIVATION_BY_MUSCLE = {
    MuscleGroup.GLUTES: "Glute bridges × 12",
    MuscleGroup.QUADS: "Bodyweight squats × 10",
    MuscleGroup.HAMSTRINGS: "Single-leg RDL (bodyweight) × 8 each",
    MuscleGroup.LATS: "Band straight-arm pulldown × 12",
    MuscleGroup.UPPER_BACK: "Band face pulls × 15",
    MuscleGroup.CHEST: "Band chest fly × 12",
    MuscleGroup.SIDE_DELTS: "Band lateral raises × 12",
    MuscleGroup.REAR_DELTS: "Band pull-aparts × 15",
    MuscleGroup.ABS: "Dead bugs × 8 each side",
}


def _generate_warmup_protocol(
    prescribed_exercises: list[PrescribedExercise],
    session_template,
    profile: AthleteProfile,
) -> WarmUpProtocol:
    """
    Generate a structured warm-up protocol based on session content and athlete profile.

    Components:
    1. General warm-up (cardio) — 5 min standard, 8-10 min for 40+
    2. Dynamic stretches — based on movement patterns in session
    3. Activation exercises — based on target muscles
    4. Warm-up sets — ramping sets for the first heavy compound
    """
    age = profile.age

    # 1. General warm-up
    general_warmup = ["5 minutes: jump rope, light jog, or rowing"]
    if age is not None and age >= 40:
        general_warmup = ["8-10 minutes: light cardio (bike, row, or brisk walk)"]
        if age >= 55:
            general_warmup.append("Joint mobility: wrist circles, ankle circles, shoulder circles × 10 each")

    # 2. Dynamic stretches — collect unique stretches based on session's movement patterns
    seen_stretches: set[str] = set()
    dynamic_stretches: list[str] = []

    for pattern in session_template.required_movement_patterns:
        for stretch in _DYNAMIC_STRETCHES_BY_PATTERN.get(pattern, []):
            if stretch not in seen_stretches:
                seen_stretches.add(stretch)
                dynamic_stretches.append(stretch)
                if len(dynamic_stretches) >= 5:
                    break
        if len(dynamic_stretches) >= 5:
            break

    # 3. Activation exercises — pick 2-3 based on primary muscles in session
    activation_exercises: list[str] = []
    seen_activations: set[str] = set()
    for muscle in session_template.muscle_groups[:6]:
        activation = _ACTIVATION_BY_MUSCLE.get(muscle)
        if activation and activation not in seen_activations:
            seen_activations.add(activation)
            activation_exercises.append(activation)
            if len(activation_exercises) >= 3:
                break

    # 4. Warm-up sets for the first heavy compound
    warmup_sets: list[WarmUpSet] = []
    first_compound = None
    for ex in prescribed_exercises:
        if ex.exercise_type in (ExerciseType.HEAVY_COMPOUND, ExerciseType.POWER):
            first_compound = ex
            break

    if first_compound:
        # Ramping warm-up: bar → 50% → 65% → 80% → working weight
        warmup_sets = [
            WarmUpSet(
                exercise_name=first_compound.exercise_name,
                percent_of_working=None,
                reps=10,
                notes="Empty bar — focus on movement quality",
            ),
            WarmUpSet(
                exercise_name=first_compound.exercise_name,
                percent_of_working=0.50,
                reps=5,
                notes="50% of working weight",
            ),
            WarmUpSet(
                exercise_name=first_compound.exercise_name,
                percent_of_working=0.65,
                reps=3,
                notes="65% of working weight",
            ),
            WarmUpSet(
                exercise_name=first_compound.exercise_name,
                percent_of_working=0.80,
                reps=1,
                notes="80% of working weight — final warm-up",
            ),
        ]

    return WarmUpProtocol(
        general_warmup=general_warmup,
        dynamic_stretches=dynamic_stretches,
        activation_exercises=activation_exercises,
        warmup_sets=warmup_sets,
    )


def _warmup_protocol_to_notes(protocol: WarmUpProtocol) -> str:
    """Convert a WarmUpProtocol to a human-readable warmup_notes string."""
    parts = []
    if protocol.general_warmup:
        parts.append("General: " + "; ".join(protocol.general_warmup))
    if protocol.dynamic_stretches:
        parts.append("Dynamic stretches: " + ", ".join(protocol.dynamic_stretches[:3]))
    if protocol.activation_exercises:
        parts.append("Activation: " + ", ".join(protocol.activation_exercises[:2]))
    if protocol.warmup_sets:
        compound = protocol.warmup_sets[0].exercise_name
        parts.append(f"Ramp-up sets for {compound}: bar → 50% × 5 → 65% × 3 → 80% × 1")
    return ". ".join(parts) if parts else "5-10 min general warmup"


def _update_recently_used(built_week: BuiltWeek, recently_used: dict[str, list]):
    """Update the recently_used tracker after a week is built."""
    week_number = built_week.week_number

    for workout in built_week.workouts:
        for idx, ex in enumerate(workout.exercises):
            # Determine if this is a primary compound (first 1-2 exercises in session)
            is_primary = (
                idx < 2 and
                ex.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]
            )

            if ex.exercise_id not in recently_used:
                recently_used[ex.exercise_id] = []

            recently_used[ex.exercise_id].append((week_number, is_primary))


# ─────────────────────────────────────────────────────────────────────────────
# STAGE B: LLM WEEK REVIEW (PARALLEL)
# ─────────────────────────────────────────────────────────────────────────────


async def review_and_refine_program(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
    openai_client,
) -> BuiltProgram:
    """
    Stage B: Parallel LLM review of each week + apply suggestions via mutator.

    Runs LLM coherence review for all weeks IN PARALLEL.
    Wall-clock time: ~3-5 seconds regardless of program length.

    Args:
        program: The built program from Stage A
        profile: Athlete profile
        strategy: Program strategy
        volume_allocation: Volume allocation targets
        openai_client: OpenAI async client

    Returns:
        BuiltProgram with LLM suggestions applied (where valid)
    """
    import asyncio
    import json
    from .prompts import format_week_review_prompt
    from .mutator import ProgramMutator

    if not openai_client:
        return program

    # Build exercise library lookup for mutator
    exercise_library = {ex.id: ex for ex in EXERCISE_LIBRARY}

    # Create mutator for applying LLM suggestions
    mutator = ProgramMutator(program, profile, strategy, volume_allocation, exercise_library)

    async def review_single_week(week: BuiltWeek) -> dict:
        """Review a single week and return the LLM response."""
        prompt = format_week_review_prompt(week, profile, strategy)

        try:
            response = await openai_client.chat.completions.create(
                model="gpt-5-mini",  # Per spec: gpt-5-mini for per-week review
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"⚠️  LLM week review failed for week {week.week_number}: {e}")
            return {"issues": [], "overall_quality": "unknown", "coaching_notes": "Review failed"}

    # Fire all week reviews IN PARALLEL
    reviews = await asyncio.gather(*[review_single_week(week) for week in program.weeks])

    # Apply suggestions using the ProgramMutator (respecting hard constraints)
    for week, review in zip(program.weeks, reviews):
        for suggestion in review.get("issues", []):
            if suggestion.get("confidence") == "low":
                continue  # Skip low-confidence suggestions

            mutation = parse_llm_suggestion_to_mutation(suggestion, week.week_number)
            if mutation:
                result = apply_mutation_with_mutator(
                    mutator=mutator,
                    week=week,
                    mutation=mutation,
                    profile=profile,
                )
                if result["applied"]:
                    print(f"  ✓ Applied LLM suggestion: {suggestion.get('issue', 'unknown')[:50]}")
                else:
                    print(f"  ✗ Rejected LLM suggestion: {result.get('reason', 'unknown')[:50]}")

    return program


def parse_llm_suggestion_to_mutation(suggestion: dict, week_number: int) -> dict | None:
    """
    Convert LLM suggestion JSON to a mutation request.

    Suggestion format from LLM:
    {
        "session_day": int,
        "exercise_id": string|null,
        "issue": string,
        "suggestion": string,
        "confidence": "high" | "medium" | "low"
    }

    Returns a mutation dict or None if unparseable.
    """
    if not suggestion:
        return None

    session_day = suggestion.get("session_day")
    exercise_id = suggestion.get("exercise_id")
    suggestion_text = suggestion.get("suggestion", "").lower()

    # Try to parse the suggestion type
    mutation = {
        "week_number": week_number,
        "session_day": session_day,
        "exercise_id": exercise_id,
        "original_suggestion": suggestion,
    }

    # Detect reorder suggestions
    if "reorder" in suggestion_text or "move" in suggestion_text or "after" in suggestion_text:
        mutation["type"] = "reorder"
        return mutation

    # Detect swap suggestions
    if "replace" in suggestion_text or "swap" in suggestion_text or "instead" in suggestion_text:
        mutation["type"] = "swap"
        # Try to extract the replacement exercise ID from the suggestion
        # This is best-effort; real implementations would use structured LLM output
        return mutation

    # Detect remove suggestions
    if "remove" in suggestion_text or "drop" in suggestion_text or "eliminate" in suggestion_text:
        mutation["type"] = "remove"
        return mutation

    # Unknown suggestion type
    return None


def apply_mutation_with_mutator(
    mutator,
    week: BuiltWeek,
    mutation: dict,
    profile: AthleteProfile,
) -> dict:
    """
    Apply a mutation request using ProgramMutator, which validates constraints.

    Returns dict with:
    - applied: bool
    - reason: str (if not applied)
    """
    from .mutator import ProgramMutator

    mutation_type = mutation.get("type")
    session_day = mutation.get("session_day")
    exercise_id = mutation.get("exercise_id")
    week_number = week.week_number
    original_suggestion = mutation.get("original_suggestion", {})

    if not session_day:
        return {"applied": False, "reason": "No session day specified"}

    if mutation_type == "reorder":
        # Use mutator's reorder method with proper ordering
        workout = mutator._get_workout(week, session_day)
        if not workout:
            return {"applied": False, "reason": f"Session day {session_day} not found"}

        # Sort exercises using utility function
        from .utils import sort_exercises_for_session
        sorted_ex = sort_exercises_for_session(workout.exercises.copy(), profile.training_goal)
        correct_order = [ex.exercise_id for ex in sorted_ex]

        result = mutator.reorder_session(
            week_num=week_number,
            session_day=session_day,
            new_exercise_order=correct_order,
            source="llm_week_review",
            reason=original_suggestion.get("issue", "LLM suggested reorder"),
        )
        return {"applied": result.success, "reason": result.description if not result.success else ""}

    elif mutation_type == "swap":
        if not exercise_id:
            return {"applied": False, "reason": "No exercise_id for swap"}

        # Try to extract replacement from suggestion text
        suggestion_text = original_suggestion.get("suggestion", "")
        new_exercise_id = _extract_exercise_id_from_suggestion(suggestion_text)

        if not new_exercise_id:
            # Try to find a better alternative for the same muscle group
            new_exercise = mutator._find_best_exercise_for_muscle(
                _get_primary_muscle_for_exercise(exercise_id, mutator.library),
                week_number,
                exclude_ids=[exercise_id],
            )
            if new_exercise:
                new_exercise_id = new_exercise.id
            else:
                return {"applied": False, "reason": "Could not find replacement exercise"}

        result = mutator.swap_exercise(
            week_num=week_number,
            session_day=session_day,
            old_exercise_id=exercise_id,
            new_exercise_id=new_exercise_id,
            source="llm_week_review",
            reason=original_suggestion.get("issue", "LLM suggested swap"),
        )
        return {"applied": result.success, "reason": result.description if not result.success else ""}

    elif mutation_type == "remove":
        if not exercise_id:
            return {"applied": False, "reason": "No exercise_id for remove"}

        result = mutator.remove_exercise(
            week_num=week_number,
            session_day=session_day,
            exercise_id=exercise_id,
            source="llm_week_review",
            reason=original_suggestion.get("issue", "LLM suggested removal"),
        )
        return {"applied": result.success, "reason": result.description if not result.success else ""}

    return {"applied": False, "reason": f"Unknown mutation type: {mutation_type}"}


def _extract_exercise_id_from_suggestion(suggestion_text: str) -> str | None:
    """
    Try to extract an exercise ID from LLM suggestion text.
    Returns None if no exercise ID can be reliably extracted.
    """
    # This is best-effort parsing. Real implementations would use structured LLM output.
    # For now, we return None and let the mutator find a suitable replacement.
    return None


def _get_primary_muscle_for_exercise(exercise_id: str, library: dict) -> str | None:
    """Get the primary muscle group for an exercise."""
    if exercise_id not in library:
        return None

    exercise = library[exercise_id]
    for ma in exercise.muscle_activations:
        if ma.role.value == "primary":
            return ma.muscle.value
    return None


# Legacy function for backwards compatibility
def apply_mutation_safely(
    program: BuiltProgram,
    week: BuiltWeek,
    mutation: dict,
    profile: AthleteProfile,
    volume_allocation: VolumeAllocation,
) -> dict:
    """
    Legacy wrapper - creates a mutator and delegates to apply_mutation_with_mutator.
    """
    from .mutator import ProgramMutator

    exercise_library = {ex.id: ex for ex in EXERCISE_LIBRARY}
    mutator = ProgramMutator(program, profile, program.strategy, volume_allocation, exercise_library)

    return apply_mutation_with_mutator(mutator, week, mutation, profile)
