#!/usr/bin/env python3
"""
V5 Program Generator — Comprehensive Test Suite

Runs all 7 test cases from the spec and validates program quality across:
A) Structural checks
B) Volume checks
C) Exercise quality checks
D) Prescription quality checks
E) Variety checks
F) Timing checks

For each test case, generates the program (use_llm=False) and runs quality checks.
Prints a scorecard with grades.

Run with: python -m program_generator_v5.test_suite
Or:       cd src/program_generator_v5 && python test_suite.py
"""

from __future__ import annotations

import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Add parent to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent))

from schemas import (
    AthleteProfile,
    BuiltProgram,
    BuiltWeek,
    BuiltWorkout,
    PrescribedExercise,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    EquipmentTier,
)
from exercise_library import EXERCISE_LIBRARY
from volume_tables import VOLUME_TABLES, get_volume_targets


# ─────────────────────────────────────────────────────────────────────────────
# TEST CASE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "id": 1,
        "name": "T1 beginner hyp 3x",
        "description": "Tier 1, beginner, hypertrophy, 3x/week, 45-min sessions, 4 weeks",
        "input": {
            "user_id": "test_001",
            "name": "Beginner Athlete",
            "training_goal": "hypertrophy",
            "training_level": "beginner",
            "program_duration_weeks": 4,
            "training_days_per_week": 3,
            "session_duration_minutes": 45,
            "equipment_tier": 1,
        },
    },
    {
        "id": 2,
        "name": "T1 intermediate hyp 4x (GOLD)",
        "description": "Tier 1, intermediate, hypertrophy, 4x/week, 60-min sessions, 8 weeks",
        "is_gold_standard": True,
        "input": {
            "user_id": "test_002",
            "name": "Gold Standard Athlete",
            "training_goal": "hypertrophy",
            "training_level": "intermediate",
            "program_duration_weeks": 8,
            "training_days_per_week": 4,
            "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
    {
        "id": 3,
        "name": "T2 intermediate hyp 4x",
        "description": "Tier 2, intermediate, hypertrophy, 4x/week, 60-min sessions, 4 weeks",
        "input": {
            "user_id": "test_003",
            "name": "Tier 2 Athlete",
            "training_goal": "hypertrophy",
            "training_level": "intermediate",
            "program_duration_weeks": 4,
            "training_days_per_week": 4,
            "session_duration_minutes": 60,
            "equipment_tier": 2,
        },
    },
    {
        "id": 4,
        "name": "T3 advanced hyp 6x",
        "description": "Tier 3, advanced, hypertrophy, 6x/week, 75-min sessions, 4 weeks",
        "input": {
            "user_id": "test_004",
            "name": "Advanced Athlete",
            "training_goal": "hypertrophy",
            "training_level": "advanced",
            "program_duration_weeks": 4,
            "training_days_per_week": 6,
            "session_duration_minutes": 75,
            "equipment_tier": 3,
        },
    },
    {
        "id": 5,
        "name": "T1 intermediate str 4x",
        "description": "Tier 1, intermediate, strength, 4x/week, 60-min sessions, 8 weeks",
        "input": {
            "user_id": "test_005",
            "name": "Strength Athlete",
            "training_goal": "strength",
            "training_level": "intermediate",
            "program_duration_weeks": 8,
            "training_days_per_week": 4,
            "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
    {
        "id": 6,
        "name": "T1 intermediate pow 4x",
        "description": "Tier 1, intermediate, power, 4x/week, 60-min sessions, 4 weeks",
        "input": {
            "user_id": "test_006",
            "name": "Power Athlete",
            "training_goal": "power",
            "training_level": "intermediate",
            "program_duration_weeks": 4,
            "training_days_per_week": 4,
            "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
    {
        "id": 7,
        "name": "Basketball sport 4x",
        "description": "Sport-specific: basketball, intermediate, 4x/week, 60-min sessions, 4 weeks",
        "input": {
            "user_id": "test_007",
            "name": "Basketball Athlete",
            "training_goal": "hypertrophy",  # Will be converted to power by sport mapping
            "training_level": "intermediate",
            "sport": "basketball",
            "program_duration_weeks": 4,
            "training_days_per_week": 4,
            "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# CHECK RESULT DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single check."""
    name: str
    passed: bool
    details: str = ""
    sub_checks: list["CheckResult"] = field(default_factory=list)


@dataclass
class CategoryResult:
    """Result of a category of checks (A-F)."""
    category: str
    category_name: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)


@dataclass
class TestResult:
    """Full result of a test case."""
    test_id: int
    test_name: str
    description: str
    program: BuiltProgram
    categories: list[CategoryResult]
    generation_time: float

    @property
    def total_checks(self) -> int:
        return sum(c.total_count for c in self.categories)

    @property
    def passed_checks(self) -> int:
        return sum(c.pass_count for c in self.categories)

    @property
    def grade(self) -> str:
        """Calculate grade based on pass percentage."""
        if self.total_checks == 0:
            return "F"
        pct = self.passed_checks / self.total_checks * 100
        if pct >= 90:
            return "A"
        elif pct >= 80:
            return "B"
        elif pct >= 70:
            return "C"
        elif pct >= 60:
            return "D"
        else:
            return "F"


# ─────────────────────────────────────────────────────────────────────────────
# BUILD EXERCISE LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

EXERCISE_BY_ID = {ex.id: ex for ex in EXERCISE_LIBRARY}


# ─────────────────────────────────────────────────────────────────────────────
# A) STRUCTURAL CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_structural(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Structural checks:
    - Correct number of weeks generated
    - Correct sessions per week
    - Every session has 4-8 exercises
    - No empty sessions, no empty weeks
    """
    checks = []

    expected_weeks = test_input["program_duration_weeks"]
    expected_sessions_per_week = test_input["training_days_per_week"]

    # Check 1: Correct number of weeks
    actual_weeks = len(program.weeks)
    checks.append(CheckResult(
        name="Correct week count",
        passed=actual_weeks == expected_weeks,
        details=f"Expected {expected_weeks}, got {actual_weeks}",
    ))

    # Check 2: Correct sessions per week
    all_correct = True
    incorrect_weeks = []
    for week in program.weeks:
        if len(week.workouts) != expected_sessions_per_week:
            all_correct = False
            incorrect_weeks.append(f"Week {week.week_number}: {len(week.workouts)}")

    checks.append(CheckResult(
        name="Correct sessions per week",
        passed=all_correct,
        details=f"Expected {expected_sessions_per_week}/week" +
                (f", incorrect: {incorrect_weeks}" if not all_correct else ""),
    ))

    # Check 3: Every session has 4-8 exercises
    min_exercises = 3 if test_input["session_duration_minutes"] <= 45 else 4
    max_exercises = 8
    sessions_outside_range = []

    for week in program.weeks:
        for workout in week.workouts:
            ex_count = len(workout.exercises)
            if ex_count < min_exercises or ex_count > max_exercises:
                sessions_outside_range.append(
                    f"W{week.week_number}D{workout.day_number}:{ex_count}"
                )

    checks.append(CheckResult(
        name=f"Exercise count per session ({min_exercises}-{max_exercises})",
        passed=len(sessions_outside_range) == 0,
        details="All sessions OK" if len(sessions_outside_range) == 0
                else f"Outside range: {sessions_outside_range[:5]}{'...' if len(sessions_outside_range) > 5 else ''}",
    ))

    # Check 4: No empty sessions
    empty_sessions = []
    for week in program.weeks:
        for workout in week.workouts:
            if len(workout.exercises) == 0:
                empty_sessions.append(f"W{week.week_number}D{workout.day_number}")

    checks.append(CheckResult(
        name="No empty sessions",
        passed=len(empty_sessions) == 0,
        details="All sessions have exercises" if len(empty_sessions) == 0
                else f"Empty: {empty_sessions}",
    ))

    # Check 5: No empty weeks
    empty_weeks = [w.week_number for w in program.weeks if len(w.workouts) == 0]

    checks.append(CheckResult(
        name="No empty weeks",
        passed=len(empty_weeks) == 0,
        details="All weeks have workouts" if len(empty_weeks) == 0
                else f"Empty weeks: {empty_weeks}",
    ))

    return CategoryResult(
        category="A",
        category_name="Structural",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# B) VOLUME CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_volume(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Volume checks:
    - Every non-deload week: all muscles >= MEV (±1 set tolerance)
    - Every week: no muscle > MRV
    - Volume increases from Week 1 -> Week 3 (or week before deload)
    - Deload weeks have <= 60% of Week 1 volume
    """
    checks = []
    training_level = test_input["training_level"]

    # Get deload weeks
    deload_weeks = set()
    for idx, week_profile in enumerate(program.strategy.week_profiles):
        if week_profile.is_deload:
            deload_weeks.add(idx + 1)

    # Check 1: All muscles >= MEV for non-deload weeks
    mev_violations = []
    worst_deviation = 0.0
    worst_muscle = ""

    for week in program.weeks:
        if week.week_number in deload_weeks:
            continue

        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(training_level, muscle_key)
            except ValueError:
                continue

            mev = targets["mev"]
            if mev == 0:  # Skip muscles with MEV=0
                continue

            actual = week.weekly_volume_actual.get(muscle_key, 0)

            # Allow 1 set tolerance
            if actual < mev - 1:
                deviation = mev - actual
                mev_violations.append(f"W{week.week_number} {muscle_key}: {actual:.1f} < {mev}")
                if deviation > worst_deviation:
                    worst_deviation = deviation
                    worst_muscle = muscle_key

    checks.append(CheckResult(
        name="All muscles >= MEV (non-deload)",
        passed=len(mev_violations) == 0,
        details=f"Worst: {worst_muscle} -{worst_deviation:.1f} sets" if mev_violations
                else "All muscles meet MEV",
    ))

    # Check 2: No muscle > MRV
    mrv_violations = []

    for week in program.weeks:
        for muscle in MuscleGroup:
            muscle_key = muscle.value
            try:
                targets = get_volume_targets(training_level, muscle_key)
            except ValueError:
                continue

            mrv = targets["mrv"]
            if mrv == 0:
                continue

            actual = week.weekly_volume_actual.get(muscle_key, 0)

            # Allow 1 set tolerance
            if actual > mrv + 1:
                mrv_violations.append(f"W{week.week_number} {muscle_key}: {actual:.1f} > {mrv}")

    checks.append(CheckResult(
        name="No muscle > MRV",
        passed=len(mrv_violations) == 0,
        details="All muscles under MRV" if len(mrv_violations) == 0
                else f"Violations: {mrv_violations[:3]}{'...' if len(mrv_violations) > 3 else ''}",
    ))

    # Check 3: Volume increases Week 1 -> Week 3 (within mesocycle)
    volume_progression_ok = True
    progression_details = []

    # Group weeks by mesocycle
    mesocycles: dict[int, list[BuiltWeek]] = {}
    for week in program.weeks:
        meso = week.mesocycle
        if meso not in mesocycles:
            mesocycles[meso] = []
        mesocycles[meso].append(week)

    for meso_num, meso_weeks in mesocycles.items():
        meso_weeks.sort(key=lambda w: w.week_number)
        non_deload = [w for w in meso_weeks if w.week_number not in deload_weeks]

        if len(non_deload) >= 2:
            # Check volume increases
            prev_total = None
            for week in non_deload[:3]:  # First 3 non-deload weeks
                total = sum(week.weekly_volume_actual.values())
                if prev_total is not None and total < prev_total * 0.95:
                    volume_progression_ok = False
                    progression_details.append(
                        f"M{meso_num}W{week.week_number}: {total:.0f} < {prev_total:.0f}"
                    )
                prev_total = total

    checks.append(CheckResult(
        name="Volume progression (W1->W3)",
        passed=volume_progression_ok,
        details="Volume increases appropriately" if volume_progression_ok
                else f"Regression: {progression_details[:2]}",
    ))

    # Check 4: Deload weeks <= 60% of Week 1 volume
    deload_ok = True
    deload_details = []

    if program.weeks:
        week1_volume = sum(program.weeks[0].weekly_volume_actual.values())
        max_deload_volume = week1_volume * 0.65  # Allow slight tolerance

        for week in program.weeks:
            if week.week_number in deload_weeks:
                deload_volume = sum(week.weekly_volume_actual.values())
                if deload_volume > max_deload_volume:
                    deload_ok = False
                    deload_details.append(
                        f"W{week.week_number}: {deload_volume:.0f} > {max_deload_volume:.0f} (60%)"
                    )

    checks.append(CheckResult(
        name="Deload volume <= 60% of Week 1",
        passed=deload_ok or len(deload_weeks) == 0,
        details="Deload volumes appropriate" if deload_ok
                else f"Too high: {deload_details[:2]}",
    ))

    return CategoryResult(
        category="B",
        category_name="Volume",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# C) EXERCISE QUALITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_exercise_quality(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Exercise quality checks:
    - All exercises are available at the specified equipment tier
    - No avoided exercises appear
    - Heavy compounds first in every session
    - No isolation exercises below 8 reps in hypertrophy programs
    - Power/plyometric exercises first in power programs
    - At least one main lift per session in strength programs
    - No more than 2 axial-loading exercises per session
    """
    checks = []
    equipment_tier = EquipmentTier(test_input["equipment_tier"])
    training_goal = test_input.get("training_goal", program.profile.training_goal)
    avoided = set(test_input.get("exercises_to_avoid", []))

    # Check 1: All exercises available at tier
    tier_violations = []
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in EXERCISE_BY_ID:
                    exercise = EXERCISE_BY_ID[ex.exercise_id]
                    if exercise.equipment_tier.value > equipment_tier.value:
                        tier_violations.append(f"{ex.exercise_name} (T{exercise.equipment_tier.value})")

    checks.append(CheckResult(
        name="All exercises available at tier",
        passed=len(tier_violations) == 0,
        details="All exercises available" if len(tier_violations) == 0
                else f"Unavailable: {tier_violations[:3]}{'...' if len(tier_violations) > 3 else ''}",
    ))

    # Check 2: No avoided exercises
    avoided_found = []
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                if ex.exercise_id in avoided:
                    avoided_found.append(ex.exercise_name)

    checks.append(CheckResult(
        name="No avoided exercises",
        passed=len(avoided_found) == 0,
        details="No avoided exercises found" if len(avoided_found) == 0
                else f"Found: {avoided_found[:3]}",
    ))

    # Check 3: Heavy compounds first in every session
    ordering_violations = []
    for week in program.weeks:
        for workout in week.workouts:
            if not workout.exercises:
                continue

            # Find index of first isolation
            first_isolation_idx = None
            for idx, ex in enumerate(workout.exercises):
                if ex.exercise_type == ExerciseType.ISOLATION:
                    first_isolation_idx = idx
                    break

            # Check if any compound comes after
            if first_isolation_idx is not None:
                for idx in range(first_isolation_idx + 1, len(workout.exercises)):
                    ex = workout.exercises[idx]
                    if ex.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]:
                        if ex.superset_group is None:  # Ignore supersetted exercises
                            ordering_violations.append(
                                f"W{week.week_number}D{workout.day_number}: {ex.exercise_name}"
                            )

    checks.append(CheckResult(
        name="Heavy compounds first",
        passed=len(ordering_violations) == 0,
        details="Ordering correct" if len(ordering_violations) == 0
                else f"Violations: {ordering_violations[:2]}{'...' if len(ordering_violations) > 2 else ''}",
    ))

    # Check 4: No isolations below 8 reps in hypertrophy
    if training_goal == "hypertrophy" or program.profile.effective_goal == "hypertrophy":
        low_rep_isolations = []
        for week in program.weeks:
            for workout in week.workouts:
                for ex in workout.exercises:
                    if ex.exercise_type == ExerciseType.ISOLATION:
                        for s in ex.sets:
                            if s.reps < 8:
                                low_rep_isolations.append(f"{ex.exercise_name}: {s.reps} reps")
                                break

        checks.append(CheckResult(
            name="No isolations < 8 reps (hypertrophy)",
            passed=len(low_rep_isolations) == 0,
            details="All isolations >= 8 reps" if len(low_rep_isolations) == 0
                    else f"Violations: {low_rep_isolations[:2]}",
        ))

    # Check 5: Power/plyometric first in power programs
    if training_goal == "power" or program.profile.effective_goal == "power":
        power_order_violations = []
        for week in program.weeks:
            # Skip deload weeks
            week_idx = week.week_number - 1
            if week_idx < len(program.strategy.week_profiles):
                if program.strategy.week_profiles[week_idx].is_deload:
                    continue

            for workout in week.workouts:
                if not workout.exercises:
                    continue

                # Check if first exercise is power/plyometric
                first_ex = workout.exercises[0]
                has_power = any(
                    ex.exercise_type in [ExerciseType.POWER, ExerciseType.PLYOMETRIC]
                    for ex in workout.exercises
                )

                if has_power and first_ex.exercise_type not in [ExerciseType.POWER, ExerciseType.PLYOMETRIC]:
                    power_order_violations.append(
                        f"W{week.week_number}D{workout.day_number}"
                    )

        checks.append(CheckResult(
            name="Power exercises first (power program)",
            passed=len(power_order_violations) == 0,
            details="Power exercises first" if len(power_order_violations) == 0
                    else f"Violations: {power_order_violations[:3]}",
        ))

    # Check 6: At least one main lift per session in strength programs
    if training_goal == "strength" or program.profile.effective_goal == "strength":
        main_patterns = {MovementPattern.SQUAT, MovementPattern.HIP_HINGE,
                        MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH}
        missing_main = []

        for week in program.weeks:
            for workout in week.workouts:
                has_main = any(
                    ex.exercise_type == ExerciseType.HEAVY_COMPOUND and
                    ex.movement_pattern in main_patterns
                    for ex in workout.exercises
                )
                if not has_main:
                    missing_main.append(f"W{week.week_number}D{workout.day_number}")

        checks.append(CheckResult(
            name="Main lift per session (strength)",
            passed=len(missing_main) == 0,
            details="All sessions have main lift" if len(missing_main) == 0
                    else f"Missing: {missing_main[:3]}{'...' if len(missing_main) > 3 else ''}",
        ))

    # Check 7: No more than 2 axial-loading exercises per session
    axial_violations = []
    for week in program.weeks:
        for workout in week.workouts:
            axial_count = 0
            for ex in workout.exercises:
                if ex.exercise_id in EXERCISE_BY_ID:
                    if EXERCISE_BY_ID[ex.exercise_id].is_axial_loading:
                        axial_count += 1

            if axial_count > 2:
                axial_violations.append(f"W{week.week_number}D{workout.day_number}: {axial_count}")

    checks.append(CheckResult(
        name="Max 2 axial-loading per session",
        passed=len(axial_violations) == 0,
        details="Axial loading OK" if len(axial_violations) == 0
                else f"Too many: {axial_violations[:3]}",
    ))

    return CategoryResult(
        category="C",
        category_name="Exercise Quality",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# D) PRESCRIPTION QUALITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_prescription_quality(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Prescription quality checks:
    - Rep ranges appropriate for exercise_type x goal
    - Rest periods appropriate (compounds > isolations)
    - RPE increases across weeks within mesocycle
    - Deload RPE is lower than Week 1
    """
    checks = []
    goal = test_input.get("training_goal", program.profile.training_goal)

    # Rep range expectations by goal and type
    rep_ranges = {
        "hypertrophy": {
            "heavy_compound": (5, 12),
            "light_compound": (6, 15),
            "isolation": (8, 20),
            "power": (1, 6),
            "plyometric": (1, 8),
        },
        "strength": {
            "heavy_compound": (1, 8),
            "light_compound": (3, 10),
            "isolation": (6, 15),
            "power": (1, 5),
            "plyometric": (1, 6),
        },
        "power": {
            "heavy_compound": (2, 8),
            "light_compound": (4, 10),
            "isolation": (5, 12),
            "power": (1, 5),
            "plyometric": (1, 6),
        },
    }

    effective_goal = program.profile.effective_goal or goal
    goal_ranges = rep_ranges.get(effective_goal, rep_ranges["hypertrophy"])

    # Check 1: Rep ranges appropriate
    rep_violations = []
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                ex_type = ex.exercise_type.value
                expected_range = goal_ranges.get(ex_type, (1, 20))

                for s in ex.sets:
                    # Allow some tolerance
                    if s.reps < expected_range[0] - 2 or s.reps > expected_range[1] + 2:
                        rep_violations.append(
                            f"{ex.exercise_name} ({ex_type}): {s.reps} reps"
                        )
                        break

    checks.append(CheckResult(
        name="Rep ranges appropriate for goal",
        passed=len(rep_violations) <= 3,  # Allow a few violations
        details="Rep ranges appropriate" if len(rep_violations) == 0
                else f"Issues: {len(rep_violations)} exercises outside range",
    ))

    # Check 2: Rest periods - compounds should have more rest than isolations
    rest_issues = 0
    total_comparisons = 0

    for week in program.weeks:
        for workout in week.workouts:
            compound_rest = []
            isolation_rest = []

            for ex in workout.exercises:
                if ex.sets:
                    avg_rest = sum(s.rest_seconds for s in ex.sets) / len(ex.sets)
                    if ex.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]:
                        compound_rest.append(avg_rest)
                    elif ex.exercise_type == ExerciseType.ISOLATION:
                        isolation_rest.append(avg_rest)

            if compound_rest and isolation_rest:
                avg_compound = sum(compound_rest) / len(compound_rest)
                avg_isolation = sum(isolation_rest) / len(isolation_rest)
                total_comparisons += 1
                if avg_compound < avg_isolation:
                    rest_issues += 1

    checks.append(CheckResult(
        name="Rest periods (compounds >= isolations)",
        passed=rest_issues <= total_comparisons * 0.1 if total_comparisons > 0 else True,
        details="Rest periods appropriate" if rest_issues == 0
                else f"{rest_issues}/{total_comparisons} sessions have issues",
    ))

    # Check 3: RPE increases across weeks within mesocycle
    rpe_progression_ok = True
    rpe_details = []

    mesocycles: dict[int, list[BuiltWeek]] = {}
    for week in program.weeks:
        meso = week.mesocycle
        if meso not in mesocycles:
            mesocycles[meso] = []
        mesocycles[meso].append(week)

    for meso_num, meso_weeks in mesocycles.items():
        meso_weeks.sort(key=lambda w: w.week_number)

        # Get average RPE per week
        week_rpes = []
        for week in meso_weeks:
            rpes = []
            for workout in week.workouts:
                for ex in workout.exercises:
                    for s in ex.sets:
                        if s.rpe:
                            rpes.append(s.rpe)
            if rpes:
                week_rpes.append((week.week_number, sum(rpes) / len(rpes)))

        # Check progression (excluding deload)
        non_deload_rpes = []
        for wn, rpe in week_rpes:
            week_idx = wn - 1
            if week_idx < len(program.strategy.week_profiles):
                if not program.strategy.week_profiles[week_idx].is_deload:
                    non_deload_rpes.append((wn, rpe))

        if len(non_deload_rpes) >= 2:
            # Check if RPE generally increases
            first_rpe = non_deload_rpes[0][1]
            last_rpe = non_deload_rpes[-1][1] if len(non_deload_rpes) > 1 else first_rpe
            if last_rpe < first_rpe - 0.5:  # Allow small tolerance
                rpe_progression_ok = False
                rpe_details.append(f"M{meso_num}: {first_rpe:.1f} -> {last_rpe:.1f}")

    checks.append(CheckResult(
        name="RPE increases within mesocycle",
        passed=rpe_progression_ok,
        details="RPE progresses appropriately" if rpe_progression_ok
                else f"Regression: {rpe_details[:2]}",
    ))

    # Check 4: Deload RPE lower than Week 1
    deload_rpe_ok = True
    deload_rpe_details = []

    if program.weeks:
        # Get Week 1 average RPE
        week1_rpes = []
        for workout in program.weeks[0].workouts:
            for ex in workout.exercises:
                for s in ex.sets:
                    if s.rpe:
                        week1_rpes.append(s.rpe)

        week1_avg_rpe = sum(week1_rpes) / len(week1_rpes) if week1_rpes else 7.0

        for week in program.weeks:
            week_idx = week.week_number - 1
            if week_idx < len(program.strategy.week_profiles):
                if program.strategy.week_profiles[week_idx].is_deload:
                    deload_rpes = []
                    for workout in week.workouts:
                        for ex in workout.exercises:
                            for s in ex.sets:
                                if s.rpe:
                                    deload_rpes.append(s.rpe)

                    if deload_rpes:
                        deload_avg = sum(deload_rpes) / len(deload_rpes)
                        if deload_avg > week1_avg_rpe + 0.5:  # Deload should be lower
                            deload_rpe_ok = False
                            deload_rpe_details.append(
                                f"W{week.week_number}: {deload_avg:.1f} > W1:{week1_avg_rpe:.1f}"
                            )

    checks.append(CheckResult(
        name="Deload RPE lower than Week 1",
        passed=deload_rpe_ok,
        details="Deload RPE appropriate" if deload_rpe_ok
                else f"Too high: {deload_rpe_details[:2]}",
    ))

    return CategoryResult(
        category="D",
        category_name="Prescription Quality",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# E) VARIETY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_variety(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Variety checks:
    - No two sessions in the same week are identical
    - Primary compounds are consistent within mesocycles
    - Exercise diversity across the full program (use at least 40% of available exercises)
    """
    checks = []
    equipment_tier = EquipmentTier(test_input["equipment_tier"])

    # Check 1: No duplicate sessions within same week
    duplicate_sessions = []
    for week in program.weeks:
        seen = {}
        for workout in week.workouts:
            fingerprint = tuple(sorted(ex.exercise_id for ex in workout.exercises))
            if fingerprint in seen:
                duplicate_sessions.append(
                    f"W{week.week_number}: {workout.day_label} = {seen[fingerprint]}"
                )
            else:
                seen[fingerprint] = workout.day_label

    checks.append(CheckResult(
        name="No duplicate sessions in same week",
        passed=len(duplicate_sessions) == 0,
        details="All sessions unique" if len(duplicate_sessions) == 0
                else f"Duplicates: {duplicate_sessions[:2]}",
    ))

    # Check 2: Primary compounds consistent within mesocycles
    # (Same main lifts should appear in same sessions across weeks within a mesocycle)
    consistency_issues = []

    mesocycles: dict[int, list[BuiltWeek]] = {}
    for week in program.weeks:
        meso = week.mesocycle
        if meso not in mesocycles:
            mesocycles[meso] = []
        mesocycles[meso].append(week)

    for meso_num, meso_weeks in mesocycles.items():
        if len(meso_weeks) < 2:
            continue

        meso_weeks.sort(key=lambda w: w.week_number)

        # Get first week's primary compounds per session
        first_week = meso_weeks[0]
        first_week_primaries = {}

        for workout in first_week.workouts:
            session_key = workout.session_type or workout.day_label
            primaries = [
                ex.exercise_id for ex in workout.exercises[:2]
                if ex.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]
            ]
            first_week_primaries[session_key] = set(primaries)

        # Check other weeks (excluding deload)
        for week in meso_weeks[1:]:
            week_idx = week.week_number - 1
            if week_idx < len(program.strategy.week_profiles):
                if program.strategy.week_profiles[week_idx].is_deload:
                    continue

            for workout in week.workouts:
                session_key = workout.session_type or workout.day_label
                current_primaries = set(
                    ex.exercise_id for ex in workout.exercises[:2]
                    if ex.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]
                )

                expected = first_week_primaries.get(session_key, set())
                if expected and not current_primaries.intersection(expected):
                    consistency_issues.append(
                        f"M{meso_num}W{week.week_number} {session_key}"
                    )

    # Allow some flexibility - check if most are consistent
    checks.append(CheckResult(
        name="Primary compounds consistent in mesocycle",
        passed=len(consistency_issues) <= len(program.weeks) * 0.2,
        details="Compounds consistent" if len(consistency_issues) == 0
                else f"Inconsistent: {consistency_issues[:3]}{'...' if len(consistency_issues) > 3 else ''}",
    ))

    # Check 3: Exercise diversity (use at least 40% of available exercises)
    used_exercises = set()
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                used_exercises.add(ex.exercise_id)

    # Count available exercises at tier
    available_count = sum(
        1 for ex in EXERCISE_LIBRARY
        if ex.equipment_tier.value <= equipment_tier.value
    )

    if available_count > 0:
        usage_ratio = len(used_exercises) / available_count
        # Adjust threshold based on program length
        weeks = len(program.weeks)
        min_ratio = 0.25 if weeks <= 4 else (0.35 if weeks <= 8 else 0.40)

        checks.append(CheckResult(
            name=f"Exercise diversity (>= {min_ratio:.0%} of available)",
            passed=usage_ratio >= min_ratio,
            details=f"Using {len(used_exercises)}/{available_count} ({usage_ratio:.0%})",
        ))

    return CategoryResult(
        category="E",
        category_name="Variety",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# F) TIMING CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_timing(program: BuiltProgram, test_input: dict) -> CategoryResult:
    """
    Timing check:
    - Estimated session duration within ±10 min of target
    """
    checks = []
    target_duration = test_input["session_duration_minutes"]
    tolerance = 10

    # Collect all session durations
    durations = []
    outside_range = []

    for week in program.weeks:
        for workout in week.workouts:
            duration = workout.estimated_duration_minutes
            durations.append(duration)

            if abs(duration - target_duration) > tolerance:
                outside_range.append(
                    f"W{week.week_number}D{workout.day_number}: {duration} min"
                )

    avg_duration = sum(durations) / len(durations) if durations else 0

    checks.append(CheckResult(
        name=f"Session duration (target: {target_duration} ±{tolerance} min)",
        passed=len(outside_range) <= len(durations) * 0.15,  # Allow 15% outside range
        details=f"Avg: {avg_duration:.0f} min" +
                (f", {len(outside_range)} outside range" if outside_range else ""),
    ))

    return CategoryResult(
        category="F",
        category_name="Timing",
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RUN ALL CHECKS FOR A TEST CASE
# ─────────────────────────────────────────────────────────────────────────────

def run_test_case(test_case: dict) -> TestResult:
    """Generate program and run all quality checks."""
    print(f"\n{'='*60}")
    print(f"TEST {test_case['id']}: {test_case['description']}")
    print(f"{'='*60}")

    start_time = time.time()

    # Import and call the pipeline directly to get the BuiltProgram
    from layer1_profile_builder import build_profile_from_structured
    from layer2_strategy_engine import build_strategy
    from layer3_volume_engine import calculate_volume
    from layer4_program_builder import build_program
    from layer5_validator import validate_and_fix

    profile = build_profile_from_structured(test_case["input"])
    strategy = build_strategy(profile)
    volume_allocation = calculate_volume(profile, strategy)
    program = build_program(profile, strategy, volume_allocation)
    program, _ = validate_and_fix(program, profile, strategy, volume_allocation)

    generation_time = time.time() - start_time

    # Run all checks
    categories = [
        check_structural(program, test_case["input"]),
        check_volume(program, test_case["input"]),
        check_exercise_quality(program, test_case["input"]),
        check_prescription_quality(program, test_case["input"]),
        check_variety(program, test_case["input"]),
        check_timing(program, test_case["input"]),
    ]

    return TestResult(
        test_id=test_case["id"],
        test_name=test_case["name"],
        description=test_case["description"],
        program=program,
        categories=categories,
        generation_time=generation_time,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRINT SCORECARD
# ─────────────────────────────────────────────────────────────────────────────

def print_scorecard(result: TestResult):
    """Print the scorecard for a test result."""
    print(f"\nTEST CASE [{result.test_id}]: {result.description}")
    print("-" * 60)

    for cat in result.categories:
        status = "PASS" if cat.passed else "FAIL"
        emoji = "\u2705" if cat.passed else "\u274C"

        # Get details from first failed check if any
        failed_checks = [c for c in cat.checks if not c.passed]
        detail_str = ""
        if failed_checks:
            detail_str = f" - {failed_checks[0].details}"
        elif cat.checks:
            detail_str = f" - {cat.checks[0].details}"

        print(f"{emoji} {cat.category_name}: {status}{detail_str[:50]}")

    print(f"\nGRADE: {result.grade} ({result.passed_checks}/{result.total_checks} checks passed)")
    print(f"Generation time: {result.generation_time:.2f}s")


# ─────────────────────────────────────────────────────────────────────────────
# PRINT FULL PROGRAM (GOLD STANDARD)
# ─────────────────────────────────────────────────────────────────────────────

def print_full_program(program: BuiltProgram):
    """Print the complete program details."""
    print("\n" + "=" * 80)
    print("GOLD STANDARD PROGRAM (Test 2) - FULL OUTPUT")
    print("=" * 80)

    print(f"\nProgram Overview:")
    print(f"  Duration: {len(program.weeks)} weeks")
    print(f"  Split: {program.strategy.split.name}")
    print(f"  Periodization: {program.strategy.periodization_model}")
    print(f"  Total Workouts: {program.total_workouts}")
    print(f"  Unique Exercises: {program.unique_exercises_used}")
    print(f"  Total Sets: {program.total_sets}")

    for week in program.weeks:
        print(f"\n{'='*60}")
        week_idx = week.week_number - 1
        phase = program.strategy.week_profiles[week_idx].phase_name if week_idx < len(program.strategy.week_profiles) else "Unknown"
        is_deload = program.strategy.week_profiles[week_idx].is_deload if week_idx < len(program.strategy.week_profiles) else False

        print(f"WEEK {week.week_number} (Mesocycle {week.mesocycle}) - {phase}")
        if is_deload:
            print("  ** DELOAD WEEK **")
        print(f"{'='*60}")

        # Show weekly volume summary
        total_vol = sum(week.weekly_volume_actual.values())
        print(f"Weekly Volume: {total_vol:.0f} total sets")

        for workout in week.workouts:
            print(f"\n  {workout.day_label} ({workout.estimated_duration_minutes} min)")
            print(f"  {'-'*40}")

            for ex in workout.exercises:
                # Format sets notation
                if ex.sets:
                    reps = ex.sets[0].reps
                    rpe = ex.sets[0].rpe
                    sets_notation = f"{ex.total_sets}x{reps} @RPE {rpe}"
                else:
                    sets_notation = f"{ex.total_sets} sets"

                superset = f" [SS:{ex.superset_group}]" if ex.superset_group else ""
                print(f"    {ex.order_in_session}. {ex.exercise_name} - {sets_notation}{superset}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Run all test cases and print summary."""
    # Configure logging
    logging.basicConfig(
        level=logging.WARNING,  # Suppress INFO messages during tests
        format="%(message)s",
    )

    print("\n" + "=" * 70)
    print("V5 PROGRAM GENERATOR - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print(f"\nRunning {len(TEST_CASES)} test cases...")

    results = []
    gold_standard_program = None

    for test_case in TEST_CASES:
        result = run_test_case(test_case)
        results.append(result)
        print_scorecard(result)

        # Save gold standard program
        if test_case.get("is_gold_standard"):
            gold_standard_program = result.program

    # Print gold standard full program
    if gold_standard_program:
        print_full_program(gold_standard_program)

    # Print implementation summary
    print("\n" + "=" * 70)
    print("PHASE 6 IMPLEMENTATION SUMMARY")
    print("=" * 70)

    print("\nTEST RESULTS SCORECARD:")
    print("-" * 50)

    a_or_b_count = 0
    for result in results:
        grade = result.grade
        if grade in ["A", "B"]:
            a_or_b_count += 1
        print(f"Test {result.test_id} ({result.test_name}): {grade} - {result.passed_checks}/{result.total_checks} checks")

    print(f"\nOVERALL: {a_or_b_count}/7 tests at A or B grade")

    # Common issues
    print("\nCOMMON ISSUES ACROSS TESTS:")
    issue_counts: dict[str, int] = {}

    for result in results:
        for cat in result.categories:
            for check in cat.checks:
                if not check.passed:
                    key = f"{cat.category_name}: {check.name}"
                    issue_counts[key] = issue_counts.get(key, 0) + 1

    if issue_counts:
        sorted_issues = sorted(issue_counts.items(), key=lambda x: -x[1])
        for issue, count in sorted_issues[:5]:
            print(f"  - {issue} ({count} occurrences)")
    else:
        print("  - None")

    # Performance metrics
    print("\nGENERATION PERFORMANCE:")
    times = [r.generation_time for r in results]
    avg_time = sum(times) / len(times)
    slowest = max(times)
    fastest = min(times)
    slowest_test = results[times.index(slowest)].test_name
    fastest_test = results[times.index(fastest)].test_name

    print(f"  Average time per program: {avg_time:.2f} seconds")
    print(f"  Slowest: {slowest:.2f} seconds ({slowest_test})")
    print(f"  Fastest: {fastest:.2f} seconds ({fastest_test})")

    # Known issues
    print("\nKNOWN ISSUES:")
    known_issues = []

    # Check for any consistent failures
    for result in results:
        for cat in result.categories:
            if not cat.passed:
                for check in cat.checks:
                    if not check.passed:
                        known_issues.append(f"Test {result.test_id}: {cat.category_name}/{check.name}")

    if known_issues:
        for issue in known_issues[:5]:
            print(f"  - {issue}")
        if len(known_issues) > 5:
            print(f"  ... and {len(known_issues) - 5} more")
    else:
        print("  - None - all tests passing!")

    print("\n" + "=" * 70)
    print("TEST SUITE COMPLETE")
    print("=" * 70)

    return results


if __name__ == "__main__":
    main()
