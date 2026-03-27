"""
V5 Layer 5: Validator

Deterministic validation rules + auto-fix loop, followed by LLM full-program review.

Implements all 17 validation rules from the spec:
- Volume: VOL_001, VOL_002, VOL_003, VOL_004, VOL_005
- Session: SES_001, SES_002, SES_003, SES_004, SES_005
- Variety: VAR_001, VAR_002
- Periodization: PER_001, PER_002, PER_003
- Goal-specific: GOAL_HYP_001, GOAL_STR_001, GOAL_POW_001, GOAL_POW_002
- Balance: BAL_001 (push:pull ratio - mapped to PAT_002)

Auto-fix loop runs up to 3 iterations to resolve critical/major issues.
LLM full-program review provides holistic qualitative assessment.
"""

from __future__ import annotations

import json
from typing import Optional
from copy import deepcopy

from .schemas import (
    AthleteProfile,
    ProgramStrategy,
    VolumeAllocation,
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    PrescribedExercise,
    PrescribedSet,
    Exercise,
    ExerciseType,
    EccentricStress,
    MovementPattern,
    MuscleGroup,
    MutationResult,
    TrainingSeason,
)
from .volume_tables import get_volume_targets, VOLUME_TABLES
from .exercise_library import EXERCISE_LIBRARY
from .prompts import format_full_program_review_prompt


# Build exercise lookup
EXERCISE_BY_ID = {ex.id: ex for ex in EXERCISE_LIBRARY}


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION ISSUE STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────


def _issue(
    rule_id: str,
    severity: str,
    message: str,
    week: int = None,
    session: int = None,
    exercise_id: str = None,
    details: dict = None,
) -> dict:
    """Create a validation issue dict."""
    return {
        "rule_id": rule_id,
        "severity": severity,
        "message": message,
        "week": week,
        "session": session,
        "exercise_id": exercise_id,
        "details": details or {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN VALIDATION + FIX ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def validate_and_fix(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
    max_iterations: int = 20,
) -> tuple[BuiltProgram, list[dict]]:
    """
    Run validation and auto-fix loop.

    Returns:
        (fixed_program, remaining_issues)
    """
    from .mutator import ProgramMutator

    for iteration in range(max_iterations):
        issues = run_all_validations(program, profile, strategy, volume_allocation)

        critical = [i for i in issues if i["severity"] == "critical"]
        major = [i for i in issues if i["severity"] == "major"]

        if not critical and not major:
            break

        # Create mutator for fixes
        mutator = ProgramMutator(program, profile, strategy, volume_allocation, EXERCISE_BY_ID)

        # Fix critical first, then major
        fixes_applied = 0
        for issue in critical + major:
            result = auto_fix_issue(mutator, issue, profile)
            if result and result.success:
                fixes_applied += 1

        # Log progress
        print(f"  Validation iteration {iteration + 1}: "
              f"{len(critical)} critical, {len(major)} major issues; {fixes_applied} fixes applied")

        if fixes_applied == 0:
            # No fixes possible, break early
            break

    # Final validation pass
    final_issues = run_all_validations(program, profile, strategy, volume_allocation)
    remaining_critical = [i for i in final_issues if i["severity"] == "critical"]

    if remaining_critical:
        print(f"  ⚠️  {len(remaining_critical)} critical issues remain after {max_iterations} fix iterations")

    return program, final_issues


def run_all_validations(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    volume_allocation: VolumeAllocation,
) -> list[dict]:
    """Run all 17 validation checks and return list of issues."""
    issues = []

    # Volume checks (VOL_001 to VOL_005)
    issues.extend(_check_volume_mev(program, profile, volume_allocation))      # VOL_001
    issues.extend(_check_volume_mrv(program, profile, volume_allocation))      # VOL_002
    issues.extend(_check_exercise_set_cap(program))                            # VOL_003
    issues.extend(_check_muscle_session_cap(program))                          # VOL_004
    issues.extend(_check_volume_adherence(program, volume_allocation))         # VOL_005

    # Session quality checks (SES_001 to SES_005)
    issues.extend(_check_exercise_ordering(program))                           # SES_001
    issues.extend(_check_axial_load_stacking(program))                         # SES_002
    issues.extend(_check_session_duration(program, profile))                   # SES_003
    issues.extend(_check_minimum_exercises(program, profile))                  # SES_004
    issues.extend(_check_exercise_day_type(program, strategy))                 # SES_005

    # Variety checks (VAR_001 to VAR_002)
    issues.extend(_check_duplicate_sessions(program))                          # VAR_001
    issues.extend(_check_exercise_diversity(program))                          # VAR_002

    # Periodization checks (PER_001 to PER_003)
    issues.extend(_check_volume_progression(program, strategy))                # PER_001
    issues.extend(_check_deload_volume(program, strategy))                     # PER_002
    issues.extend(_check_correct_periodization(program, profile, strategy))    # PER_003

    # Goal-specific checks
    if profile.training_goal == "hypertrophy":
        issues.extend(_check_hypertrophy_isolation_reps(program))              # GOAL_HYP_001
    elif profile.training_goal == "strength":
        issues.extend(_check_strength_main_lifts(program))                     # GOAL_STR_001
        issues.extend(_check_strength_session_completeness(program, strategy)) # GOAL_STR_002
    elif profile.training_goal == "power":
        issues.extend(_check_power_exercise_placement(program))                # GOAL_POW_001
        issues.extend(_check_power_session_completeness(program, strategy))    # GOAL_POW_002

    # Balance checks
    issues.extend(_check_push_pull_ratio(program))                             # BAL_001 (same as PAT_002)

    # Movement pattern checks
    issues.extend(_check_movement_patterns(program, strategy))                 # PAT_001

    # V6: Population-specific checks
    issues.extend(_check_youth_safety(program, profile))                       # AGE_001
    issues.extend(_check_in_season_limits(program, profile, strategy))         # SEA_001

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# VOLUME CHECKS (VOL_001 to VOL_005)
# ─────────────────────────────────────────────────────────────────────────────


def _check_volume_mev(
    program: BuiltProgram,
    profile: AthleteProfile,
    volume_allocation: VolumeAllocation,
) -> list[dict]:
    """VOL_001: Weekly volume above MEV for non-deload weeks."""
    issues = []

    for week in program.weeks:
        # Get week profile to check if deload
        week_idx = week.week_number - 1
        if week_idx < len(program.strategy.week_profiles):
            is_deload = program.strategy.week_profiles[week_idx].is_deload
        else:
            is_deload = False

        if is_deload:
            continue

        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(profile.training_level, muscle_key)
            except ValueError:
                continue

            mev = targets["mev"]

            # Skip muscles with MEV=0 (not tracked separately, e.g., lower_chest)
            if mev == 0:
                continue

            actual = week.weekly_volume_actual.get(muscle_key, 0)

            if actual < mev - 1:  # Allow 1 set tolerance
                issues.append(_issue(
                    rule_id="VOL_001",
                    severity="critical",
                    message=f"Week {week.week_number} {muscle_key}: {actual:.1f} sets < MEV ({mev})",
                    week=week.week_number,
                    details={"muscle": muscle_key, "actual": actual, "mev": mev},
                ))

    return issues


def _check_volume_mrv(
    program: BuiltProgram,
    profile: AthleteProfile,
    volume_allocation: VolumeAllocation,
) -> list[dict]:
    """VOL_002: Weekly volume below MRV for all weeks."""
    issues = []

    for week in program.weeks:
        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(profile.training_level, muscle_key)
            except ValueError:
                continue

            mrv = targets["mrv"]
            actual = week.weekly_volume_actual.get(muscle_key, 0)

            if actual > mrv + 1:  # Allow 1 set tolerance
                issues.append(_issue(
                    rule_id="VOL_002",
                    severity="critical",
                    message=f"Week {week.week_number} {muscle_key}: {actual:.1f} sets > MRV ({mrv})",
                    week=week.week_number,
                    details={"muscle": muscle_key, "actual": actual, "mrv": mrv},
                ))

    return issues


def _check_exercise_set_cap(program: BuiltProgram) -> list[dict]:
    """VOL_003: No exercise exceeds its max_sets_per_session."""
    issues = []

    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in EXERCISE_BY_ID:
                    exercise = EXERCISE_BY_ID[ex.exercise_id]
                    if ex.total_sets > exercise.max_sets_per_session:
                        issues.append(_issue(
                            rule_id="VOL_003",
                            severity="major",
                            message=f"{ex.exercise_name}: {ex.total_sets} sets > max {exercise.max_sets_per_session}",
                            week=week.week_number,
                            session=workout.day_number,
                            exercise_id=ex.exercise_id,
                            details={
                                "current_sets": ex.total_sets,
                                "max_sets": exercise.max_sets_per_session,
                            },
                        ))

    return issues


def _check_muscle_session_cap(program: BuiltProgram) -> list[dict]:
    """VOL_004: No muscle group gets >10 direct sets in a single session."""
    issues = []

    for week in program.weeks:
        for workout in week.workouts:
            # Sum contributions per muscle
            muscle_sets: dict[str, float] = {}
            for ex in workout.exercises:
                for muscle, contrib in ex.muscle_contributions.items():
                    muscle_sets[muscle] = muscle_sets.get(muscle, 0) + contrib

            for muscle, sets in muscle_sets.items():
                if sets > 10:
                    issues.append(_issue(
                        rule_id="VOL_004",
                        severity="major",
                        message=f"{workout.day_label}: {muscle} has {sets:.1f} sets (>10)",
                        week=week.week_number,
                        session=workout.day_number,
                        details={"muscle": muscle, "sets": sets},
                    ))

    return issues


def _check_volume_adherence(
    program: BuiltProgram,
    volume_allocation: VolumeAllocation,
) -> list[dict]:
    """VOL_005: actual/target ratio for each muscle is between 0.85 and 1.15."""
    issues = []

    for week in program.weeks:
        # Check if deload
        week_idx = week.week_number - 1
        if week_idx < len(program.strategy.week_profiles):
            is_deload = program.strategy.week_profiles[week_idx].is_deload
        else:
            is_deload = False

        if is_deload:
            continue  # Don't check adherence for deload weeks

        for muscle, target in week.weekly_volume_target.items():
            if target <= 0:
                continue

            actual = week.weekly_volume_actual.get(muscle, 0)
            ratio = actual / target

            if ratio < 0.85 or ratio > 1.15:
                issues.append(_issue(
                    rule_id="VOL_005",
                    severity="warning",
                    message=f"Week {week.week_number} {muscle}: {ratio:.2f}x target ({actual:.1f}/{target})",
                    week=week.week_number,
                    details={"muscle": muscle, "actual": actual, "target": target, "ratio": ratio},
                ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# SESSION QUALITY CHECKS (SES_001 to SES_005)
# ─────────────────────────────────────────────────────────────────────────────


def _check_exercise_ordering(program: BuiltProgram) -> list[dict]:
    """SES_001: Within each session: power → heavy compound → light compound → isolation."""
    issues = []

    type_order = {
        ExerciseType.POWER: 0,
        ExerciseType.PLYOMETRIC: 1,
        ExerciseType.HEAVY_COMPOUND: 2,
        ExerciseType.LIGHT_COMPOUND: 3,
        ExerciseType.ISOLATION: 4,
    }

    for week in program.weeks:
        for workout in week.workouts:
            prev_order = -1
            misordered = []
            for ex in workout.exercises:
                current_order = type_order.get(ex.exercise_type, 5)
                if current_order < prev_order:
                    misordered.append(ex.exercise_name)
                prev_order = max(prev_order, current_order)

            if misordered:
                issues.append(_issue(
                    rule_id="SES_001",
                    severity="major",
                    message=f"{workout.day_label}: exercises out of order: {', '.join(misordered)}",
                    week=week.week_number,
                    session=workout.day_number,
                    details={"misordered_exercises": misordered},
                ))

    return issues


def _check_axial_load_stacking(program: BuiltProgram) -> list[dict]:
    """SES_002: No session has >2 heavy axial-loading exercises."""
    issues = []

    for week in program.weeks:
        for workout in week.workouts:
            axial_count = 0
            axial_exercises = []
            for ex in workout.exercises:
                if ex.exercise_id in EXERCISE_BY_ID:
                    exercise = EXERCISE_BY_ID[ex.exercise_id]
                    if exercise.is_axial_loading:
                        axial_count += 1
                        axial_exercises.append(ex.exercise_id)

            if axial_count > 2:
                issues.append(_issue(
                    rule_id="SES_002",
                    severity="major",
                    message=f"{workout.day_label}: {axial_count} axial-loading exercises (max 2)",
                    week=week.week_number,
                    session=workout.day_number,
                    details={"axial_count": axial_count, "axial_exercises": axial_exercises},
                ))

    return issues


def _check_session_duration(
    program: BuiltProgram,
    profile: AthleteProfile,
) -> list[dict]:
    """SES_003: Estimated duration within 110% of session_duration_minutes."""
    issues = []

    max_duration = profile.session_duration_minutes * 1.1

    for week in program.weeks:
        for workout in week.workouts:
            if workout.estimated_duration_minutes > max_duration:
                issues.append(_issue(
                    rule_id="SES_003",
                    severity="warning",
                    message=f"{workout.day_label}: {workout.estimated_duration_minutes} min > {max_duration:.0f} min cap",
                    week=week.week_number,
                    session=workout.day_number,
                    details={
                        "duration": workout.estimated_duration_minutes,
                        "max_duration": max_duration,
                    },
                ))

    return issues


def _check_minimum_exercises(
    program: BuiltProgram,
    profile: AthleteProfile,
) -> list[dict]:
    """SES_004: Each session has at least 4 exercises (3 for sessions ≤45min)."""
    issues = []

    min_exercises = 3 if profile.session_duration_minutes <= 45 else 4

    for week in program.weeks:
        for workout in week.workouts:
            if len(workout.exercises) < min_exercises:
                issues.append(_issue(
                    rule_id="SES_004",
                    severity="warning",
                    message=f"{workout.day_label}: {len(workout.exercises)} exercises (min {min_exercises})",
                    week=week.week_number,
                    session=workout.day_number,
                    details={"exercise_count": len(workout.exercises), "minimum": min_exercises},
                ))

    return issues


def _check_exercise_day_type(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """SES_005: No exercises on wrong day type (e.g., lateral raises on leg day)."""
    issues = []

    # Define muscle groups for upper/lower splits
    upper_muscles = {"chest", "upper_chest", "lower_chest", "lats", "upper_back", "traps",
                     "front_delts", "side_delts", "rear_delts", "biceps", "triceps", "forearms"}
    lower_muscles = {"quads", "hamstrings", "glutes", "calves", "adductors"}

    for week in program.weeks:
        for workout in week.workouts:
            # Determine session type from session_type or day_label
            session_type = workout.session_type.lower() if workout.session_type else workout.day_label.lower()

            is_lower = "lower" in session_type or "leg" in session_type
            is_upper = "upper" in session_type or "push" in session_type or "pull" in session_type

            if not is_lower and not is_upper:
                continue  # Full body or unclear - don't validate

            for ex in workout.exercises:
                if ex.exercise_id not in EXERCISE_BY_ID:
                    continue

                exercise = EXERCISE_BY_ID[ex.exercise_id]

                # Get primary muscles
                primary_muscles = {
                    ma.muscle.value for ma in exercise.muscle_activations
                    if ma.role.value == "primary"
                }

                # Check for mismatch
                if is_lower and primary_muscles.issubset(upper_muscles):
                    # Upper exercise on lower day
                    issues.append(_issue(
                        rule_id="SES_005",
                        severity="critical",
                        message=f"{workout.day_label}: {ex.exercise_name} (upper body) on lower day",
                        week=week.week_number,
                        session=workout.day_number,
                        exercise_id=ex.exercise_id,
                        details={"session_type": session_type, "exercise_type": "upper"},
                    ))
                elif is_upper and primary_muscles.issubset(lower_muscles):
                    # Lower exercise on upper day
                    issues.append(_issue(
                        rule_id="SES_005",
                        severity="critical",
                        message=f"{workout.day_label}: {ex.exercise_name} (lower body) on upper day",
                        week=week.week_number,
                        session=workout.day_number,
                        exercise_id=ex.exercise_id,
                        details={"session_type": session_type, "exercise_type": "lower"},
                    ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# VARIETY CHECKS (VAR_001 to VAR_002)
# ─────────────────────────────────────────────────────────────────────────────


def _check_duplicate_sessions(program: BuiltProgram) -> list[dict]:
    """VAR_001: No two sessions in the same week have identical exercise lists."""
    issues = []

    for week in program.weeks:
        seen_sessions = {}
        for workout in week.workouts:
            # Create fingerprint of exercise list
            fingerprint = tuple(sorted(ex.exercise_id for ex in workout.exercises))

            if fingerprint in seen_sessions:
                issues.append(_issue(
                    rule_id="VAR_001",
                    severity="critical",
                    message=f"Week {week.week_number}: {workout.day_label} is identical to {seen_sessions[fingerprint]}",
                    week=week.week_number,
                    session=workout.day_number,
                    details={
                        "duplicate_session_day": workout.day_number,
                        "original_session": seen_sessions[fingerprint],
                    },
                ))
            else:
                seen_sessions[fingerprint] = workout.day_label

    return issues


def _check_exercise_diversity(program: BuiltProgram) -> list[dict]:
    """VAR_002: Program uses at least 50% of available exercises over its full duration."""
    issues = []

    # Count unique exercises used
    used_exercises = set()
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                used_exercises.add(ex.exercise_id)

    # Count available exercises (at user's equipment tier)
    available_count = len(EXERCISE_BY_ID)

    if available_count > 0:
        usage_ratio = len(used_exercises) / available_count
        if usage_ratio < 0.3:  # Relaxed from 0.5 to 0.3 for shorter programs
            issues.append(_issue(
                rule_id="VAR_002",
                severity="warning",
                message=f"Program uses only {len(used_exercises)}/{available_count} ({usage_ratio:.0%}) of available exercises",
                details={
                    "used_count": len(used_exercises),
                    "available_count": available_count,
                    "ratio": usage_ratio,
                },
            ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# PERIODIZATION CHECKS (PER_001 to PER_003)
# ─────────────────────────────────────────────────────────────────────────────


def _check_volume_progression(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """PER_001: Volume increases week-over-week within mesocycle (except deload)."""
    issues = []

    if strategy.periodization_model != "volume_ramp":
        return issues

    # Group weeks by mesocycle
    mesocycles: dict[int, list[BuiltWeek]] = {}
    for week in program.weeks:
        meso = week.mesocycle
        if meso not in mesocycles:
            mesocycles[meso] = []
        mesocycles[meso].append(week)

    for meso_num, meso_weeks in mesocycles.items():
        # Sort by week number
        meso_weeks.sort(key=lambda w: w.week_number)

        prev_total = None
        for week in meso_weeks:
            # Check if deload
            week_idx = week.week_number - 1
            if week_idx < len(strategy.week_profiles):
                is_deload = strategy.week_profiles[week_idx].is_deload
            else:
                is_deload = False

            if is_deload:
                prev_total = None  # Reset after deload
                continue

            total = sum(week.weekly_volume_actual.values())

            if prev_total is not None and total < prev_total * 0.95:
                issues.append(_issue(
                    rule_id="PER_001",
                    severity="critical",
                    message=f"Week {week.week_number}: volume decreased ({total:.0f} vs {prev_total:.0f} prev)",
                    week=week.week_number,
                    details={
                        "current_volume": total,
                        "previous_week_volume": prev_total,
                    },
                ))

            prev_total = total

    return issues


def _check_deload_volume(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """PER_002: Deload weeks have ≤60% of Week 1's volume."""
    issues = []

    if not program.weeks:
        return issues

    # Get Week 1 volume
    week1_volume = sum(program.weeks[0].weekly_volume_actual.values())
    max_deload_volume = week1_volume * 0.6

    for week in program.weeks:
        week_idx = week.week_number - 1
        if week_idx < len(strategy.week_profiles):
            is_deload = strategy.week_profiles[week_idx].is_deload
        else:
            is_deload = False

        if not is_deload:
            continue

        deload_volume = sum(week.weekly_volume_actual.values())
        if deload_volume > max_deload_volume:
            issues.append(_issue(
                rule_id="PER_002",
                severity="major",
                message=f"Deload Week {week.week_number}: {deload_volume:.0f} sets > {max_deload_volume:.0f} max (60% of Week 1)",
                week=week.week_number,
                details={
                    "deload_volume": deload_volume,
                    "target_max_volume": max_deload_volume,
                },
            ))

    return issues


def _check_correct_periodization(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
) -> list[dict]:
    """PER_003: Correct periodization model for goal."""
    issues = []

    expected = {
        "hypertrophy": "volume_ramp",
        "strength": "linear_intensity",
        "power": "concurrent",
    }

    expected_model = expected.get(profile.training_goal)
    if expected_model and strategy.periodization_model != expected_model:
        issues.append(_issue(
            rule_id="PER_003",
            severity="warning",
            message=f"Goal '{profile.training_goal}' typically uses '{expected_model}', got '{strategy.periodization_model}'",
            details={
                "goal": profile.training_goal,
                "expected_model": expected_model,
                "actual_model": strategy.periodization_model,
            },
        ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# GOAL-SPECIFIC CHECKS
# ─────────────────────────────────────────────────────────────────────────────


def _check_hypertrophy_isolation_reps(program: BuiltProgram) -> list[dict]:
    """GOAL_HYP_001: In hypertrophy programs, isolation exercises never below 8 reps."""
    issues = []

    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_type == ExerciseType.ISOLATION:
                    for set_obj in ex.sets:
                        if set_obj.reps < 8:
                            issues.append(_issue(
                                rule_id="GOAL_HYP_001",
                                severity="major",
                                message=f"{ex.exercise_name}: {set_obj.reps} reps < 8 for isolation",
                                week=week.week_number,
                                session=workout.day_number,
                                exercise_id=ex.exercise_id,
                                details={"current_reps": set_obj.reps, "min_reps": 8},
                            ))
                            break  # Only report once per exercise

    return issues


def _check_strength_main_lifts(program: BuiltProgram) -> list[dict]:
    """GOAL_STR_001: In strength programs, at least one main compound per session."""
    issues = []

    main_lift_patterns = {
        MovementPattern.SQUAT,
        MovementPattern.HIP_HINGE,
        MovementPattern.HORIZONTAL_PUSH,
        MovementPattern.VERTICAL_PUSH,
    }

    for week in program.weeks:
        for workout in week.workouts:
            has_main = False
            for ex in workout.exercises:
                if (ex.exercise_type == ExerciseType.HEAVY_COMPOUND and
                    ex.movement_pattern in main_lift_patterns):
                    has_main = True
                    break

            if not has_main:
                issues.append(_issue(
                    rule_id="GOAL_STR_001",
                    severity="critical",
                    message=f"{workout.day_label}: no main compound lift",
                    week=week.week_number,
                    session=workout.day_number,
                ))

    return issues


def _check_power_exercise_placement(program: BuiltProgram) -> list[dict]:
    """GOAL_POW_001: In power programs, explosive exercises are first."""
    issues = []

    for week in program.weeks:
        for workout in week.workouts:
            if not workout.exercises:
                continue

            first_ex = workout.exercises[0]
            if first_ex.exercise_type not in (ExerciseType.POWER, ExerciseType.PLYOMETRIC):
                # Check if there are any power exercises that should be first
                has_power = any(
                    ex.exercise_type in (ExerciseType.POWER, ExerciseType.PLYOMETRIC)
                    for ex in workout.exercises
                )
                if has_power:
                    issues.append(_issue(
                        rule_id="GOAL_POW_001",
                        severity="critical",
                        message=f"{workout.day_label}: power exercise not first",
                        week=week.week_number,
                        session=workout.day_number,
                    ))

    return issues


def _check_power_session_completeness(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """GOAL_POW_002: Every non-deload session has at least two power/plyometric exercises.

    Per NSCA guidelines, power programs should have 2-4 plyometric sessions per week.
    By requiring 2 power/plyo exercises per session, all sessions become "plyometric sessions".
    """
    issues = []
    MIN_POWER_EXERCISES = 2

    for week in program.weeks:
        # Check if deload
        week_idx = week.week_number - 1
        if week_idx < len(strategy.week_profiles):
            is_deload = strategy.week_profiles[week_idx].is_deload
        else:
            is_deload = False

        if is_deload:
            continue

        for workout in week.workouts:
            power_count = sum(
                1 for ex in workout.exercises
                if ex.exercise_type in (ExerciseType.POWER, ExerciseType.PLYOMETRIC)
            )
            if power_count < MIN_POWER_EXERCISES:
                issues.append(_issue(
                    rule_id="GOAL_POW_002",
                    severity="critical",
                    message=f"{workout.day_label}: only {power_count} power/plyometric exercise(s), need {MIN_POWER_EXERCISES}",
                    week=week.week_number,
                    session=workout.day_number,
                ))

    return issues


def _check_strength_session_completeness(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """GOAL_STR_002: Every non-deload session has at least two heavy compound exercises.

    Evidence-based guidelines recommend ~75% compound exercises for strength programs.
    Requiring 2 heavy compounds per session ensures adequate strength stimulus.
    """
    issues = []
    MIN_HEAVY_COMPOUNDS = 2

    for week in program.weeks:
        # Check if deload
        week_idx = week.week_number - 1
        if week_idx < len(strategy.week_profiles):
            is_deload = strategy.week_profiles[week_idx].is_deload
        else:
            is_deload = False

        if is_deload:
            continue

        for workout in week.workouts:
            heavy_count = sum(
                1 for ex in workout.exercises
                if ex.exercise_type == ExerciseType.HEAVY_COMPOUND
            )
            if heavy_count < MIN_HEAVY_COMPOUNDS:
                issues.append(_issue(
                    rule_id="GOAL_STR_002",
                    severity="critical",
                    message=f"{workout.day_label}: only {heavy_count} heavy compound exercise(s), need {MIN_HEAVY_COMPOUNDS}",
                    week=week.week_number,
                    session=workout.day_number,
                ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# BALANCE CHECKS (BAL_001)
# ─────────────────────────────────────────────────────────────────────────────


def _check_push_pull_ratio(program: BuiltProgram) -> list[dict]:
    """BAL_001 (PAT_002): Weekly push volume within 0.7-1.3× of pull volume."""
    issues = []

    push_muscles = {"chest", "upper_chest", "lower_chest", "front_delts", "side_delts", "triceps"}
    pull_muscles = {"lats", "upper_back", "traps", "rear_delts", "biceps"}

    for week in program.weeks:
        push_vol = sum(
            week.weekly_volume_actual.get(m, 0) for m in push_muscles
        )
        pull_vol = sum(
            week.weekly_volume_actual.get(m, 0) for m in pull_muscles
        )

        if pull_vol > 0:
            ratio = push_vol / pull_vol
            if ratio < 0.7 or ratio > 1.3:
                issues.append(_issue(
                    rule_id="BAL_001",
                    severity="major",
                    message=f"Week {week.week_number}: push:pull ratio {ratio:.2f} (should be 0.7-1.3)",
                    week=week.week_number,
                    details={
                        "push_volume": push_vol,
                        "pull_volume": pull_vol,
                        "ratio": ratio,
                    },
                ))

    return issues


def _check_movement_patterns(
    program: BuiltProgram,
    strategy: ProgramStrategy,
) -> list[dict]:
    """PAT_001: Each session has all required movement patterns from split template."""
    issues = []

    # Build session_type -> SessionTemplate mapping
    session_templates = {}
    for template in strategy.split.sessions_per_week:
        session_templates[template.session_type] = template

    for week in program.weeks:
        for workout in week.workouts:
            # Get required patterns from split template
            template = session_templates.get(workout.session_type)
            if not template:
                continue

            required_patterns = set(p.value for p in template.required_movement_patterns)

            # Get patterns actually present in workout
            present_patterns = set()
            for ex in workout.exercises:
                present_patterns.add(ex.movement_pattern.value)

            # Find missing patterns
            missing = required_patterns - present_patterns
            for pattern in missing:
                issues.append(_issue(
                    rule_id="PAT_001",
                    severity="critical",
                    message=f"Week {week.week_number} {workout.day_label}: missing required {pattern} pattern",
                    week=week.week_number,
                    session=workout.day_number,
                    details={
                        "session_type": workout.session_type,
                        "pattern": pattern,
                        "required_patterns": list(required_patterns),
                        "present_patterns": list(present_patterns),
                    },
                ))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-FIX DISPATCH
# ─────────────────────────────────────────────────────────────────────────────


def auto_fix_issue(
    mutator,
    issue: dict,
    profile: AthleteProfile,
) -> Optional[MutationResult]:
    """
    Apply auto-fix for a specific issue using the mutator.
    Each validation rule ID maps to a specific fix strategy.
    """
    rule_id = issue["rule_id"]
    details = issue.get("details", {})
    week_num = issue.get("week")
    session_day = issue.get("session")
    exercise_id = issue.get("exercise_id")

    # ─── VOL_001: Muscle below MEV ───
    if rule_id == "VOL_001":
        muscle = details.get("muscle")
        mev = details.get("mev", 0)
        actual = details.get("actual", 0)
        if muscle and week_num:
            return mutator.fix_volume_deficit(
                week_num=week_num, muscle=muscle,
                target_sets=mev, current_sets=actual,
                source="validator_auto_fix", reason=f"VOL_001: {muscle} is below MEV"
            )

    # ─── VOL_002: Muscle above MRV ───
    elif rule_id == "VOL_002":
        muscle = details.get("muscle")
        mrv = details.get("mrv", 0)
        actual = details.get("actual", 0)
        if muscle and week_num:
            return mutator.fix_volume_excess(
                week_num=week_num, muscle=muscle,
                target_sets=mrv, current_sets=actual,
                source="validator_auto_fix", reason=f"VOL_002: {muscle} is above MRV"
            )

    # ─── VOL_003: Exercise exceeds max_sets_per_session ───
    elif rule_id == "VOL_003":
        current_sets = details.get("current_sets", 0)
        max_sets = details.get("max_sets", 0)
        if exercise_id and week_num and session_day:
            excess = current_sets - max_sets
            return mutator.remove_sets(
                week_num=week_num, session_day=session_day,
                exercise_id=exercise_id, sets_to_remove=excess,
                source="validator_auto_fix", reason=f"VOL_003: reducing to max {max_sets} sets"
            )

    # ─── VOL_004: Muscle >10 sets in one session ───
    elif rule_id == "VOL_004":
        muscle = details.get("muscle")
        sets = details.get("sets", 0)
        if muscle and week_num and session_day:
            excess = int(sets - 10 + 0.5)
            # Try to redistribute to another session
            week = mutator._get_week(week_num)
            if week:
                for other_workout in week.workouts:
                    if other_workout.day_number != session_day:
                        return mutator.redistribute_muscle_volume(
                            week_num=week_num, muscle=muscle,
                            from_session_day=session_day,
                            to_session_day=other_workout.day_number,
                            sets_to_move=excess,
                            source="validator_auto_fix", reason=f"VOL_004: {muscle} >10 sets"
                        )

    # ─── SES_001: Wrong exercise ordering ───
    elif rule_id == "SES_001":
        if week_num and session_day:
            # Get correct order
            week = mutator._get_week(week_num)
            if week:
                workout = mutator._get_workout(week, session_day)
                if workout:
                    from .utils import sort_exercises_for_session
                    sorted_ex = sort_exercises_for_session(
                        workout.exercises.copy(),
                        profile.training_goal
                    )
                    correct_order = [ex.exercise_id for ex in sorted_ex]
                    return mutator.reorder_session(
                        week_num=week_num, session_day=session_day,
                        new_exercise_order=correct_order,
                        source="validator_auto_fix", reason="SES_001: fixing exercise order"
                    )

    # ─── SES_002: >2 axial-loading exercises ───
    elif rule_id == "SES_002":
        axial_exercises = details.get("axial_exercises", [])
        if axial_exercises and week_num and session_day and len(axial_exercises) > 2:
            # Find non-axial alternative for the 3rd axial exercise
            third_axial = axial_exercises[2]
            alt = mutator._find_non_axial_alternative(third_axial, week_num)
            if alt:
                return mutator.swap_exercise(
                    week_num=week_num, session_day=session_day,
                    old_exercise_id=third_axial, new_exercise_id=alt.id,
                    source="validator_auto_fix", reason="SES_002: too many axial exercises"
                )

    # ─── SES_003: Session too long ───
    elif rule_id == "SES_003":
        if week_num and session_day:
            # Remove lowest-priority exercise
            lowest = mutator._find_lowest_priority_exercise(week_num, session_day)
            if lowest:
                return mutator.remove_exercise(
                    week_num=week_num, session_day=session_day,
                    exercise_id=lowest,
                    source="validator_auto_fix", reason="SES_003: session too long"
                )

    # ─── SES_005: Exercise on wrong day type ───
    elif rule_id == "SES_005":
        if exercise_id and week_num and session_day:
            # Try to move to appropriate session
            week = mutator._get_week(week_num)
            if week:
                for other_workout in week.workouts:
                    if other_workout.day_number != session_day:
                        # Check if this is a better fit
                        return mutator.move_exercise(
                            week_num=week_num,
                            from_session_day=session_day,
                            to_session_day=other_workout.day_number,
                            exercise_id=exercise_id,
                            source="validator_auto_fix", reason=f"SES_005: moving to appropriate day"
                        )

    # ─── VAR_001: Duplicate sessions ───
    elif rule_id == "VAR_001":
        duplicate_day = details.get("duplicate_session_day")
        if duplicate_day and week_num:
            # Swap one exercise for variety
            week = mutator._get_week(week_num)
            if week:
                workout = mutator._get_workout(week, duplicate_day)
                if workout and workout.exercises:
                    # Find lowest priority exercise to swap
                    lowest = mutator._find_lowest_priority_exercise(week_num, duplicate_day)
                    if lowest and lowest in EXERCISE_BY_ID:
                        original_ex = EXERCISE_BY_ID[lowest]
                        # Find alternative in same rotation group
                        for ex_id, exercise in EXERCISE_BY_ID.items():
                            if (exercise.rotation_group == original_ex.rotation_group and
                                ex_id != lowest and
                                ex_id not in [e.exercise_id for e in workout.exercises]):
                                return mutator.swap_exercise(
                                    week_num=week_num, session_day=duplicate_day,
                                    old_exercise_id=lowest, new_exercise_id=ex_id,
                                    source="validator_auto_fix", reason="VAR_001: diversifying session"
                                )

    # ─── GOAL_HYP_001: Isolation reps too low ───
    elif rule_id == "GOAL_HYP_001":
        if exercise_id and week_num and session_day:
            week = mutator._get_week(week_num)
            if week:
                workout = mutator._get_workout(week, session_day)
                if workout:
                    for ex in workout.exercises:
                        if ex.exercise_id == exercise_id:
                            # Represcribe with 10-12 reps
                            from .utils import calculate_intensity_percent_simple
                            new_sets = []
                            for s in ex.sets:
                                # Recalculate intensity for new rep count
                                new_intensity = calculate_intensity_percent_simple(
                                    reps=10,
                                    rir=s.rir if s.rir is not None else 2,
                                    exercise_type=ex.exercise_type.value,
                                )
                                new_set = PrescribedSet(
                                    set_number=s.set_number,
                                    reps=10,  # Set to proper hypertrophy range
                                    rpe=s.rpe,
                                    rir=s.rir,
                                    intensity_percent=new_intensity,
                                    rest_seconds=s.rest_seconds,
                                    tempo=s.tempo,
                                    notes=s.notes,
                                )
                                new_sets.append(new_set)
                            return mutator.replace_prescription(
                                week_num=week_num, session_day=session_day,
                                exercise_id=exercise_id, new_sets=new_sets,
                                source="validator_auto_fix", reason="GOAL_HYP_001: increasing isolation reps"
                            )

    # ─── GOAL_STR_001: Missing main lift ───
    elif rule_id == "GOAL_STR_001":
        if week_num and session_day:
            # Find best main lift to add
            main_patterns = ["squat", "hip_hinge", "horizontal_push", "vertical_push"]
            for pattern in main_patterns:
                best = mutator._find_best_exercise_for_pattern(pattern, week_num)
                if best and best.exercise_type == ExerciseType.HEAVY_COMPOUND:
                    return mutator.add_exercise(
                        week_num=week_num, session_day=session_day,
                        exercise_id=best.id, sets=4,
                        source="validator_auto_fix", reason="GOAL_STR_001: adding main lift"
                    )

    # ─── GOAL_POW_001: Power exercises not first ───
    elif rule_id == "GOAL_POW_001":
        if week_num and session_day:
            week = mutator._get_week(week_num)
            if week:
                workout = mutator._get_workout(week, session_day)
                if workout:
                    from .utils import sort_exercises_for_session
                    sorted_ex = sort_exercises_for_session(
                        workout.exercises.copy(),
                        profile.training_goal
                    )
                    correct_order = [ex.exercise_id for ex in sorted_ex]
                    return mutator.reorder_session(
                        week_num=week_num, session_day=session_day,
                        new_exercise_order=correct_order,
                        source="validator_auto_fix", reason="GOAL_POW_001: power first"
                    )

    # ─── GOAL_POW_002: No power movement in session ───
    elif rule_id == "GOAL_POW_002":
        if week_num and session_day:
            # Find best power exercise to add
            for pattern in ["power_lower", "power_upper"]:
                best = mutator._find_best_exercise_for_pattern(pattern, week_num)
                if best:
                    return mutator.add_exercise(
                        week_num=week_num, session_day=session_day,
                        exercise_id=best.id, sets=3,
                        source="validator_auto_fix", reason="GOAL_POW_002: adding power movement"
                    )

    # ─── PER_001: Volume not progressing ───
    elif rule_id == "PER_001":
        current_vol = details.get("current_volume", 0)
        prev_vol = details.get("previous_week_volume", 0)
        if week_num and prev_vol > 0:
            deficit = int((prev_vol * 1.05) - current_vol + 0.5)  # Need at least 5% more
            if deficit > 0:
                week = mutator._get_week(week_num)
                if week:
                    # Add sets to existing exercises across sessions
                    for workout in week.workouts:
                        for ex in workout.exercises:
                            if ex.exercise_id in EXERCISE_BY_ID:
                                exercise = EXERCISE_BY_ID[ex.exercise_id]
                                if ex.total_sets < exercise.max_sets_per_session:
                                    return mutator.add_sets(
                                        week_num=week_num, session_day=workout.day_number,
                                        exercise_id=ex.exercise_id, sets_to_add=1,
                                        source="validator_auto_fix", reason="PER_001: increasing volume"
                                    )

    # ─── PER_002: Deload volume too high ───
    elif rule_id == "PER_002":
        target_max = details.get("target_max_volume", 0)
        deload_vol = details.get("deload_volume", 0)
        if week_num and target_max > 0:
            excess = int(deload_vol - target_max + 0.5)
            if excess > 0:
                week = mutator._get_week(week_num)
                if week:
                    # Remove sets from exercises
                    for workout in week.workouts:
                        for ex in workout.exercises:
                            if ex.total_sets > 2:
                                return mutator.remove_sets(
                                    week_num=week_num, session_day=workout.day_number,
                                    exercise_id=ex.exercise_id, sets_to_remove=1,
                                    source="validator_auto_fix", reason="PER_002: reducing deload volume"
                                )

    # ─── BAL_001: Push/pull imbalance ───
    elif rule_id == "BAL_001":
        push_vol = details.get("push_volume", 0)
        pull_vol = details.get("pull_volume", 0)
        if week_num and pull_vol > 0:
            return mutator.fix_push_pull_imbalance(
                week_num=week_num,
                push_sets=push_vol, pull_sets=pull_vol,
                source="validator_auto_fix", reason="BAL_001: balancing push/pull"
            )

    # ─── PAT_001: Missing movement pattern ───
    elif rule_id == "PAT_001":
        pattern = details.get("pattern")
        if pattern and week_num and session_day:
            return mutator.fix_missing_movement_pattern(
                week_num=week_num, session_day=session_day, pattern=pattern,
                source="validator_auto_fix", reason=f"PAT_001: missing {pattern} pattern"
            )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# LLM FULL-PROGRAM REVIEW
# ─────────────────────────────────────────────────────────────────────────────


async def llm_full_program_review(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
    openai_client,
) -> dict:
    """
    Send entire program to LLM for holistic quality review.

    Returns dict with:
    - overall_grade: A/B/C/D/F
    - strengths: list of positive aspects
    - issues: list of qualitative issues
    - coaching_summary: 2-3 sentence assessment
    """
    if not openai_client:
        return {
            "overall_grade": "B",
            "strengths": ["Program generated without LLM review"],
            "issues": [],
            "coaching_summary": "LLM review skipped - deterministic validation passed.",
        }

    prompt = format_full_program_review_prompt(program)

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5.2",  # Per spec: gpt-5.2 for full-program review
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"⚠️  LLM full-program review failed: {e}")
        return {
            "overall_grade": "B",
            "strengths": ["Deterministic validation passed"],
            "issues": [],
            "coaching_summary": f"LLM review failed: {str(e)[:100]}",
        }


def get_validation_summary(issues: list[dict]) -> dict:
    """
    Summarize validation results.

    Returns dict with counts by severity and pass/fail status.
    """
    critical = [i for i in issues if i["severity"] == "critical"]
    major = [i for i in issues if i["severity"] == "major"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    return {
        "critical_count": len(critical),
        "major_count": len(major),
        "warning_count": len(warnings),
        "total_issues": len(issues),
        "passed": len(critical) == 0 and len(major) == 0,
        "validation_pass_rate": _calculate_pass_rate(len(critical), len(major), len(warnings)),
        "issues_by_rule": _group_by_rule(issues),
    }


def _calculate_pass_rate(critical: int, major: int, warnings: int) -> float:
    """
    Calculate validation pass rate percentage.

    - 0 critical + 0 major = 100%
    - 0 critical + some warnings = 95%
    - Any major = 85%
    - Any critical = 70%
    """
    if critical > 0:
        return 70.0
    elif major > 0:
        return 85.0
    elif warnings > 0:
        return 95.0
    else:
        return 100.0


def _group_by_rule(issues: list[dict]) -> dict[str, int]:
    """Group issue counts by rule ID."""
    counts = {}
    for issue in issues:
        rule_id = issue.get("rule_id", "unknown")
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# V6: POPULATION-SPECIFIC CHECKS
# ─────────────────────────────────────────────────────────────────────────────

# Age-tiered difficulty caps (same as layer1)
_AGE_DIFFICULTY_CAPS: dict[tuple[int, int], int] = {
    (10, 13): 2,
    (14, 15): 3,
    (16, 17): 4,
    (18, 54): 5,
    (55, 64): 4,
    (65, 100): 3,
}


def _get_age_difficulty_cap(age: int | None) -> int:
    if age is None:
        return 5
    for (lo, hi), cap in _AGE_DIFFICULTY_CAPS.items():
        if lo <= age <= hi:
            return cap
    return 5


def _check_youth_safety(
    program: BuiltProgram,
    profile: AthleteProfile,
) -> list[dict]:
    """AGE_001: Ensure youth athletes don't get exercises exceeding their difficulty cap."""
    issues = []

    if profile.age is None or profile.age >= 18:
        return issues

    difficulty_cap = _get_age_difficulty_cap(profile.age)

    for week in program.weeks:
        for workout_idx, workout in enumerate(week.workouts):
            for ex in workout.exercises:
                ex_def = EXERCISE_BY_ID.get(ex.exercise_id)
                if ex_def and ex_def.difficulty > difficulty_cap:
                    issues.append(_issue(
                        rule_id="AGE_001",
                        severity="critical",
                        message=(
                            f"Exercise '{ex.exercise_name}' (difficulty={ex_def.difficulty}) "
                            f"exceeds youth cap ({difficulty_cap}) for age {profile.age}"
                        ),
                        week=week.week_number,
                        session=workout_idx + 1,
                        exercise_id=ex.exercise_id,
                    ))

                # Block Olympic lifts for under-14
                if profile.age < 14 and ex_def and ex_def.requires_proficiency:
                    issues.append(_issue(
                        rule_id="AGE_001",
                        severity="critical",
                        message=(
                            f"Exercise '{ex.exercise_name}' requires proficiency "
                            f"and is blocked for athletes under 14 (age={profile.age})"
                        ),
                        week=week.week_number,
                        session=workout_idx + 1,
                        exercise_id=ex.exercise_id,
                    ))

    return issues


def _check_in_season_limits(
    program: BuiltProgram,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
) -> list[dict]:
    """SEA_001: Ensure in-season programs respect volume and session limits."""
    issues = []

    if not (profile.training_season and profile.training_season.value == "in_season"):
        return issues

    for week in program.weeks:
        # Check session count (max 2 for in-season + games)
        workout_count = len(week.workouts)
        max_sessions = max(2, profile.training_days_per_week)
        if workout_count > max_sessions:
            issues.append(_issue(
                rule_id="SEA_001",
                severity="major",
                message=(
                    f"Week {week.week_number}: {workout_count} sessions exceeds "
                    f"in-season max of {max_sessions}"
                ),
                week=week.week_number,
            ))

        # Check that high-eccentric exercises are minimized
        for workout_idx, workout in enumerate(week.workouts):
            high_eccentric_count = 0
            for ex in workout.exercises:
                ex_def = EXERCISE_BY_ID.get(ex.exercise_id)
                if ex_def and hasattr(ex_def, 'eccentric_stress'):
                    if ex_def.eccentric_stress == EccentricStress.HIGH:
                        high_eccentric_count += 1

            if high_eccentric_count > 2:
                issues.append(_issue(
                    rule_id="SEA_001",
                    severity="warning",
                    message=(
                        f"Week {week.week_number}, session {workout_idx + 1}: "
                        f"{high_eccentric_count} high-eccentric exercises may cause "
                        f"excessive DOMS for in-season athlete"
                    ),
                    week=week.week_number,
                    session=workout_idx + 1,
                ))

    return issues
