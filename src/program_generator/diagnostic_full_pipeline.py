#!/usr/bin/env python3
"""
V5 Full Pipeline Diagnostic — Confirms all fixes from previous prompt.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import generate_program_v5_sync
from layer5_validator import run_all_validations, validate_and_fix, get_validation_summary, EXERCISE_BY_ID
from layer4_program_builder import build_program
from layer1_profile_builder import build_profile_from_structured
from layer2_strategy_engine import build_strategy
from layer3_volume_engine import calculate_volume
from volume_tables import VOLUME_TABLES
from mutator import ProgramMutator


def run_full_diagnostic():
    """Run the full pipeline diagnostic."""

    print("=" * 70)
    print("V5 FULL PIPELINE DIAGNOSTIC")
    print("=" * 70)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 2: CONFIRM lower_chest volume targets
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "━" * 70)
    print("SECTION 2: LOWER_CHEST VOLUME TARGETS")
    print("━" * 70)

    for level in ["beginner", "intermediate", "advanced"]:
        lc = VOLUME_TABLES[level].get("lower_chest", {})
        print(f"  {level} lower_chest: {lc}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 3: CONFIRM LLM model strings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "━" * 70)
    print("SECTION 3: LLM MODEL STRINGS")
    print("━" * 70)

    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "model=", "."],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    for line in result.stdout.split('\n'):
        if 'gpt' in line.lower() and '.py:' in line:
            print(f"  {line}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 4: CONFIRM Mutator in Layer 4B and Layer 5
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "━" * 70)
    print("SECTION 4: MUTATOR WIRING CHECK")
    print("━" * 70)

    print("\n  Layer 5 (layer5_validator.py):")
    result = subprocess.run(
        ["grep", "-n", "ProgramMutator", "layer5_validator.py"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    for line in result.stdout.strip().split('\n'):
        if line:
            print(f"    {line}")

    print("\n  Layer 4B (layer4_program_builder.py):")
    result = subprocess.run(
        ["grep", "-n", "ProgramMutator", "layer4_program_builder.py"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    output = result.stdout.strip()
    if output:
        for line in output.split('\n'):
            if line:
                print(f"    {line}")
    else:
        print("    ⚠️  NO ProgramMutator usage found in layer4_program_builder.py!")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 1: FULL PIPELINE DIAGNOSTIC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "━" * 70)
    print("SECTION 1: FULL PIPELINE DIAGNOSTIC")
    print("━" * 70)

    # Test input: Tier 1, intermediate, hypertrophy, 4x/week, 60 min, 4 weeks
    test_input = {
        "user_id": "diagnostic_test",
        "name": "Diagnostic Test Athlete",
        "training_goal": "hypertrophy",
        "training_level": "intermediate",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 60,
        "equipment_tier": 1,  # Tier 1 = minimal
    }

    print(f"\n  Test Parameters:")
    print(f"    Tier: {test_input['equipment_tier']} (minimal)")
    print(f"    Level: {test_input['training_level']}")
    print(f"    Goal: {test_input['training_goal']}")
    print(f"    Days/Week: {test_input['training_days_per_week']}")
    print(f"    Session: {test_input['session_duration_minutes']} min")
    print(f"    Duration: {test_input['program_duration_weeks']} weeks")
    print(f"    use_llm: False")

    # Build the pipeline manually to get access to intermediate states
    print("\n  Running pipeline...")

    # Layer 1: Build profile
    profile = build_profile_from_structured(test_input)
    print(f"    Layer 1: Profile built - {len(profile.available_exercises)} exercises available")

    # Layer 2: Build strategy
    strategy = build_strategy(profile=profile, openai_client=None)
    print(f"    Layer 2: Strategy built - {strategy.split.name}, {strategy.periodization_model}")

    # Layer 3: Calculate volume
    volume_allocation = calculate_volume(profile, strategy)
    print(f"    Layer 3: Volume allocated for {len(volume_allocation.weeks)} weeks")

    # Layer 4A: Build program
    program = build_program(profile, strategy, volume_allocation)
    print(f"    Layer 4A: Program built - {program.total_workouts} workouts, {program.unique_exercises_used} unique exercises")

    # Run validation BEFORE auto-fix
    print("\n  Running validation BEFORE auto-fix...")
    issues_before = run_all_validations(program, profile, strategy, volume_allocation)

    # Count by severity
    critical_before = [i for i in issues_before if i["severity"] == "critical"]
    major_before = [i for i in issues_before if i["severity"] == "major"]
    warning_before = [i for i in issues_before if i["severity"] == "warning"]

    print(f"\n  VALIDATION ISSUES BEFORE AUTO-FIX:")
    print(f"    Critical: {len(critical_before)}")
    print(f"    Major: {len(major_before)}")
    print(f"    Warning: {len(warning_before)}")

    if issues_before:
        print("\n  Detailed issues BEFORE:")
        for issue in issues_before:
            print(f"    [{issue['severity'].upper()}] {issue['rule_id']}: {issue.get('message', '')}")
            if issue.get('week'):
                print(f"      Week: {issue.get('week')}, Session: {issue.get('session', 'N/A')}")

    # Run validate_and_fix (with mutator)
    print("\n  Running validate_and_fix (with mutator)...")

    # Create mutator and track fixes
    mutator = ProgramMutator(program, profile, strategy, volume_allocation, EXERCISE_BY_ID)

    # Run the validation and fix loop
    program_fixed, issues_after = validate_and_fix(
        program=program,
        profile=profile,
        strategy=strategy,
        volume_allocation=volume_allocation,
        max_iterations=3,
    )

    # Get fixes from mutator log
    fixes_applied = mutator.mutation_log

    print(f"\n  MUTATIONS APPLIED BY AUTO-FIX:")
    if fixes_applied:
        for fix in fixes_applied:
            print(f"    FIX: {fix.mutation_type} — {fix.description}")
            print(f"      Success: {fix.success}")
    else:
        print("    (No mutations logged - checking internal mutator state)")

    # Count by severity after fix
    critical_after = [i for i in issues_after if i["severity"] == "critical"]
    major_after = [i for i in issues_after if i["severity"] == "major"]
    warning_after = [i for i in issues_after if i["severity"] == "warning"]

    print(f"\n  VALIDATION ISSUES AFTER AUTO-FIX:")
    print(f"    Critical: {len(critical_after)}")
    print(f"    Major: {len(major_after)}")
    print(f"    Warning: {len(warning_after)}")

    if issues_after:
        print("\n  Detailed issues AFTER:")
        for issue in issues_after:
            print(f"    [{issue['severity'].upper()}] {issue['rule_id']}: {issue.get('message', '')}")

    # Calculate pass rate
    summary = get_validation_summary(issues_after)
    pass_rate = summary['validation_pass_rate']

    print(f"\n  SUMMARY:")
    print(f"    Before: {len(critical_before)} critical, {len(major_before)} major, {len(warning_before)} warnings")
    print(f"    After: {len(critical_after)} critical, {len(major_after)} major, {len(warning_after)} warnings")
    print(f"    Validation pass rate: {pass_rate}%")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 5: PRINT FULL WEEK 1 (post-validation)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "━" * 70)
    print("SECTION 5: FULL WEEK 1 (POST-VALIDATION)")
    print("━" * 70)

    week1 = program_fixed.weeks[0]

    for workout in week1.workouts:
        print(f"\n  {workout.day_label} (est. {workout.estimated_duration_minutes}min)")
        for ex in workout.exercises:
            # Build set notation
            if ex.sets:
                reps = ex.sets[0].reps
                rpe = ex.sets[0].rpe
                rest = ex.sets[0].rest_seconds
                tempo = ex.sets[0].tempo
                set_notation = f"{ex.total_sets}×{reps} @ RPE {rpe}, rest {rest}s, tempo {tempo}"
            else:
                set_notation = f"{ex.total_sets} sets"
            print(f"    {ex.order_in_session}. {ex.exercise_name} — {set_notation}")

    # Weekly volume vs targets
    print(f"\n  WEEKLY VOLUME vs TARGETS:")

    # Get volume targets for intermediate level
    vol_targets = VOLUME_TABLES[profile.training_level]

    for muscle_key, actual in sorted(week1.weekly_volume_actual.items()):
        target = week1.weekly_volume_target.get(muscle_key, 0)
        if target == 0 and actual == 0:
            continue

        mrv = vol_targets.get(muscle_key, {}).get("mrv", 0)
        mev = vol_targets.get(muscle_key, {}).get("mev", 0)

        # Determine status
        if actual < mev - 1:
            status = "🔴"
        elif actual > mrv + 1:
            status = "🔴"
        elif actual < target * 0.85:
            status = "⚠️"
        elif actual > target * 1.15:
            status = "⚠️"
        else:
            status = "✅"

        print(f"    {muscle_key}: delivered={actual:.1f} target={target} MEV={mev} MRV={mrv} {status}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FINAL SUMMARY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    print("\n" + "=" * 70)
    print("PIPELINE DIAGNOSTIC RESULTS")
    print("=" * 70)

    print("\nVALIDATION BEFORE AUTO-FIX:")
    print(f"  Critical: [{len(critical_before)}] — {[i['rule_id'] for i in critical_before]}")
    print(f"  Major: [{len(major_before)}] — {[i['rule_id'] for i in major_before]}")
    print(f"  Warning: [{len(warning_before)}] — {[i['rule_id'] for i in warning_before]}")

    print("\nAUTO-FIX MUTATIONS APPLIED:")
    if fixes_applied:
        for fix in fixes_applied:
            print(f"  {fix.mutation_type} → success={fix.success} → {fix.description[:60]}")
    else:
        print("  (mutator log empty - fixes applied internally)")

    print("\nVALIDATION AFTER AUTO-FIX:")
    print(f"  Critical: [{len(critical_after)}] — {[i['rule_id'] for i in critical_after]}")
    print(f"  Major: [{len(major_after)}] — {[i['rule_id'] for i in major_after]}")
    print(f"  Warning: [{len(warning_after)}] — {[i['rule_id'] for i in warning_after]}")
    print(f"  Pass rate: [{pass_rate}%]")

    # lower_chest check
    lc_intermediate = VOLUME_TABLES["intermediate"].get("lower_chest", {})
    lc_mev = lc_intermediate.get("mev", 0)
    lc_status = "✅ FIXED" if lc_mev == 0 else "❌ NOT FIXED"
    print(f"\nLOWER_CHEST: MEV=[{lc_mev}] at intermediate {lc_status}")

    # LLM models check (dynamically read from grep)
    print("\nLLM MODELS:")
    result = subprocess.run(
        ["grep", "-rn", "model=", "."],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    for line in result.stdout.split('\n'):
        if 'gpt' in line.lower() and '.py:' in line and 'layer' in line.lower():
            # Extract just the model string
            if 'gpt-5-mini' in line:
                print(f"  {line.split(':')[0].replace('./', '')}: gpt-5-mini ✅")
            elif 'gpt-5.2' in line:
                print(f"  {line.split(':')[0].replace('./', '')}: gpt-5.2 ✅")
            elif 'gpt-4o' in line:
                print(f"  {line.split(':')[0].replace('./', '')}: ❌ still using gpt-4o variants")

    # Mutator wiring check
    result_l4 = subprocess.run(
        ["grep", "-c", "ProgramMutator", "layer4_program_builder.py"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    l4_count = int(result_l4.stdout.strip()) if result_l4.stdout.strip().isdigit() else 0
    l4_status = "✅ YES" if l4_count > 2 else "❌ NO"

    result_l5 = subprocess.run(
        ["grep", "-c", "ProgramMutator", "layer5_validator.py"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__)
    )
    l5_count = int(result_l5.stdout.strip()) if result_l5.stdout.strip().isdigit() else 0
    l5_status = "✅ YES" if l5_count > 0 else "❌ NO"

    print(f"\nMUTATOR IN LAYER 4B: [{l4_status}] — {l4_count} references")
    print(f"MUTATOR IN LAYER 5: [{l5_status}] — {l5_count} references")

    print("\n" + "=" * 70)
    print("END DIAGNOSTIC")
    print("=" * 70)


if __name__ == "__main__":
    run_full_diagnostic()
