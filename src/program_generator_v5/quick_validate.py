#!/usr/bin/env python3
"""Quick validation script for the 3 test configs."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from schemas import ExerciseType
from volume_tables import VOLUME_TABLES
from layer1_profile_builder import build_profile_from_structured
from layer2_strategy_engine import build_strategy
from layer3_volume_engine import calculate_volume
from layer4_program_builder import build_program

TEST_CONFIGS = [
    {
        "name": "Test 1: Intermediate Hypertrophy 4x",
        "input": {
            "user_id": "t1", "name": "Test", "training_goal": "hypertrophy",
            "training_level": "intermediate", "program_duration_weeks": 4,
            "training_days_per_week": 4, "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
    {
        "name": "Test 2: Beginner Strength 3x",
        "input": {
            "user_id": "t2", "name": "Test", "training_goal": "strength",
            "training_level": "beginner", "program_duration_weeks": 4,
            "training_days_per_week": 3, "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
    {
        "name": "Test 3: Advanced Power 4x",
        "input": {
            "user_id": "t3", "name": "Test", "training_goal": "power",
            "training_level": "advanced", "program_duration_weeks": 4,
            "training_days_per_week": 4, "session_duration_minutes": 60,
            "equipment_tier": 1,
        },
    },
]

def run_test(config):
    print(f"\n{'='*60}")
    print(f"  {config['name']}")
    print(f"{'='*60}")

    inp = config["input"]
    profile = build_profile_from_structured(inp)
    strategy = build_strategy(profile=profile, openai_client=None)
    volume_allocation = calculate_volume(profile, strategy)
    program = build_program(profile, strategy, volume_allocation)

    level = inp["training_level"]

    under_mev = []
    over_mrv = []

    for week in program.weeks:
        week_idx = week.week_number - 1
        is_deload = False
        if week_idx < len(program.strategy.week_profiles):
            is_deload = program.strategy.week_profiles[week_idx].is_deload

        for muscle_key in VOLUME_TABLES[level]:
            targets = VOLUME_TABLES[level][muscle_key]
            mev = targets["mev"]
            mrv = targets["mrv"]

            if mev == 0:
                continue

            actual = week.weekly_volume_actual.get(muscle_key, 0)

            if not is_deload and actual < mev - 1:
                under_mev.append(f"  W{week.week_number} {muscle_key}: {actual:.1f} < MEV({mev})")

            if mrv > 0 and actual > mrv + 1:
                over_mrv.append(f"  W{week.week_number} {muscle_key}: {actual:.1f} > MRV({mrv})")

    # Print week-by-week summary
    for week in program.weeks:
        week_idx = week.week_number - 1
        is_deload = False
        if week_idx < len(program.strategy.week_profiles):
            is_deload = program.strategy.week_profiles[week_idx].is_deload

        if is_deload:
            print(f"\n  Week {week.week_number} (DELOAD):")
        else:
            print(f"\n  Week {week.week_number}:")

        for workout in week.workouts:
            exercises_str = ", ".join(
                f"{ex.exercise_name}({ex.total_sets}s)"
                for ex in workout.exercises
            )
            print(f"    {workout.day_label}: {exercises_str}")

        # Show muscles near boundaries
        problem_muscles = []
        for muscle_key in sorted(VOLUME_TABLES[level].keys()):
            targets = VOLUME_TABLES[level][muscle_key]
            mev = targets["mev"]
            mrv = targets["mrv"]
            if mev == 0:
                continue
            actual = week.weekly_volume_actual.get(muscle_key, 0)
            if not is_deload and actual < mev - 1:
                problem_muscles.append(f"    ❌ {muscle_key}: {actual:.1f} < MEV({mev})")
            elif mrv > 0 and actual > mrv + 1:
                problem_muscles.append(f"    ❌ {muscle_key}: {actual:.1f} > MRV({mrv})")

        if problem_muscles:
            print("    Volume issues:")
            for pm in problem_muscles:
                print(pm)

    print(f"\n  RESULTS:")
    print(f"    Under-MEV violations: {len(under_mev)}")
    if under_mev:
        for v in under_mev:
            print(v)
    print(f"    Over-MRV violations: {len(over_mrv)}")
    if over_mrv:
        for v in over_mrv:
            print(v)

    return len(under_mev), len(over_mrv)


if __name__ == "__main__":
    total_under = 0
    total_over = 0

    for config in TEST_CONFIGS:
        u, o = run_test(config)
        total_under += u
        total_over += o

    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_under} under-MEV, {total_over} over-MRV")
    print(f"{'='*60}")

    if total_under == 0 and total_over == 0:
        print("  ✅ ALL TESTS PASS")
    else:
        print("  ❌ FAILURES DETECTED")
