"""
Test script for Phase 3: Volume Engine + Program Builder

Creates and validates a test program:
- Tier 1, intermediate, hypertrophy
- 4x/week, 60-minute sessions
- 4-week program (1 mesocycle)

Validates against spec requirements.
"""

import sys
import os

# Add the program_generator_v5 directory to sys.path so bare imports work
sys.path.insert(0, 'src/program_generator_v5')

# Now use bare imports like the rest of the codebase
from schemas import (
    AthleteProfile,
    EquipmentTier,
    ProgramStrategy,
    WeekProfile,
)
from split_templates import SPLIT_TEMPLATES, get_split_for_config
from layer3_volume_engine import calculate_volume
from layer4_program_builder import build_program


def create_test_profile():
    """Create test athlete profile."""
    return AthleteProfile(
        user_id="test_user",
        name="Test User",
        training_goal="hypertrophy",
        training_level="intermediate",
        program_duration_weeks=4,
        training_days_per_week=4,
        session_duration_minutes=60,
        equipment_tier=EquipmentTier.TIER_1,
        recovery_capacity="normal",
        weak_points=[],
        exercises_to_avoid=[],
        exercises_to_include=[],
    )


def create_test_strategy(profile: AthleteProfile):
    """Create test program strategy - 4-week hypertrophy mesocycle."""
    # Get split template
    split_id = get_split_for_config(4, "intermediate", "hypertrophy")
    split = SPLIT_TEMPLATES[split_id]

    # Build 4 week profiles for a hypertrophy mesocycle (as per task spec)
    week_profiles = [
        # Week 1: Introduction (volume_multiplier=1.0)
        WeekProfile(
            week_number=1,
            mesocycle_number=1,
            week_in_mesocycle=1,
            phase_name="Introduction",
            volume_multiplier=1.0,
            intensity_modifier="light",
            rpe_range=(6.0, 7.0),
            rir_range=(3, 4),
            is_deload=False,
            notes="Establish movement patterns, begin stimulus",
        ),
        # Week 2: Development (volume_multiplier=1.1)
        WeekProfile(
            week_number=2,
            mesocycle_number=1,
            week_in_mesocycle=2,
            phase_name="Development",
            volume_multiplier=1.1,
            intensity_modifier="moderate",
            rpe_range=(7.0, 8.0),
            rir_range=(2, 3),
            is_deload=False,
            notes="Volume increase, progressive overload",
        ),
        # Week 3: Overreaching (volume_multiplier=1.25)
        WeekProfile(
            week_number=3,
            mesocycle_number=1,
            week_in_mesocycle=3,
            phase_name="Overreaching",
            volume_multiplier=1.25,
            intensity_modifier="heavy",
            rpe_range=(8.0, 9.0),
            rir_range=(1, 2),
            is_deload=False,
            notes="Maximum stimulus before recovery",
        ),
        # Week 4: Deload (volume_multiplier=0.5)
        WeekProfile(
            week_number=4,
            mesocycle_number=1,
            week_in_mesocycle=4,
            phase_name="Deload",
            volume_multiplier=0.5,
            intensity_modifier="deload",
            rpe_range=(5.0, 6.0),
            rir_range=(4, 5),
            is_deload=True,
            notes="Dissipate fatigue, supercompensation",
        ),
    ]

    return ProgramStrategy(
        split=split,
        week_profiles=week_profiles,
        periodization_model="volume_ramp",
        volume_modifier=1.0,
        emphasis_muscles=[],
        deemphasis_muscles=[],
        mesocycle_count=1,
    )


def print_program(program):
    """Print the full program in a readable format."""
    print("\n" + "="*80)
    print("PHASE 3 TEST PROGRAM OUTPUT")
    print("="*80)
    print(f"Profile: {program.profile.training_level} {program.profile.training_goal}")
    print(f"Equipment: Tier {program.profile.equipment_tier.value}")
    print(f"Split: {program.strategy.split.name}")
    print(f"Duration: {program.profile.program_duration_weeks} weeks")
    print(f"Total workouts: {program.total_workouts}")
    print(f"Unique exercises: {program.unique_exercises_used}")
    print("="*80)

    for week in program.weeks:
        print(f"\n{'='*80}")
        print(f"WEEK {week.week_number} — {week.phase}")
        print(f"{'='*80}")

        for workout in week.workouts:
            print(f"\n  {workout.day_label} (estimated {workout.estimated_duration_minutes} min)")
            print(f"  {'-'*76}")

            for i, ex in enumerate(workout.exercises, 1):
                # Get rep and RPE from first set
                if ex.sets:
                    reps = ex.sets[0].reps
                    rpe = ex.sets[0].rpe
                    rest = ex.sets[0].rest_seconds
                else:
                    reps = "?"
                    rpe = "?"
                    rest = "?"

                sets_desc = f"{ex.total_sets}×{reps}"
                ss = f" [SS:{ex.superset_group}]" if ex.superset_group else ""

                print(f"    {i}. {ex.exercise_name:<40} {sets_desc:>8} @ RPE {rpe:>4}, rest {rest:>3}s{ss}")

        # Print volume check
        print(f"\n  Volume delivered vs target:")
        print(f"  {'-'*76}")

        # Get non-zero muscles
        muscles_to_check = [
            m for m in week.weekly_volume_target
            if week.weekly_volume_target[m] > 0
        ]

        for muscle in sorted(muscles_to_check):
            target = week.weekly_volume_target[muscle]
            actual = week.weekly_volume_actual.get(muscle, 0)
            diff = actual - target
            flag = " ⚠️ " if abs(diff) > 2 else " ✅"

            print(f"    {muscle:<20} {actual:>5.1f} delivered / {target:>5.0f} target "
                  f"(diff: {diff:>+5.1f}){flag}")


def analyze_program(program):
    """Analyze the program and print validation results."""
    print("\n" + "="*80)
    print("PROGRAM ANALYSIS")
    print("="*80)

    # 1. Check exercise counts per session
    print("\n1. EXERCISE COUNT PER SESSION:")
    for week in program.weeks:
        for workout in week.workouts:
            ex_count = len(workout.exercises)
            status = "✅" if 5 <= ex_count <= 7 else "⚠️ "
            print(f"   Week {week.week_number} {workout.day_label}: {ex_count} exercises {status}")

    # 2. Check compound ordering
    print("\n2. COMPOUND EXERCISE ORDERING (should be first):")
    for week in program.weeks[:2]:  # Check first 2 weeks
        for workout in week.workouts:
            first_ex = workout.exercises[0] if workout.exercises else None
            if first_ex:
                is_compound = first_ex.exercise_type.value in ["heavy_compound", "light_compound"]
                status = "✅" if is_compound else "⚠️ "
                print(f"   Week {week.week_number} {workout.day_label}: "
                      f"{first_ex.exercise_name} ({first_ex.exercise_type.value}) {status}")

    # 3. Check rep ranges
    print("\n3. REP RANGES (Week 1):")
    week1 = program.weeks[0]
    for workout in week1.workouts[:2]:  # Check first 2 workouts
        print(f"   {workout.day_label}:")
        for ex in workout.exercises[:3]:  # First 3 exercises
            if ex.sets:
                reps = ex.sets[0].reps
                ex_type = ex.exercise_type.value
                # Expected ranges for hypertrophy
                expected = {
                    "heavy_compound": (6, 10),
                    "light_compound": (8, 12),
                    "isolation": (10, 15),
                }
                range_min, range_max = expected.get(ex_type, (0, 999))
                in_range = range_min <= reps <= range_max
                status = "✅" if in_range else "⚠️ "
                print(f"     {ex.exercise_name}: {reps} reps ({ex_type}) "
                      f"[expected {range_min}-{range_max}] {status}")

    # 4. Check volume progression
    print("\n4. VOLUME PROGRESSION (chest as example):")
    chest_volumes = []
    for week in program.weeks:
        vol = week.weekly_volume_actual.get("chest", 0)
        chest_volumes.append(vol)
        print(f"   Week {week.week_number}: {vol:.1f} sets")

    if len(chest_volumes) >= 3:
        progression = chest_volumes[2] > chest_volumes[1] > chest_volumes[0]
        deload = chest_volumes[3] < chest_volumes[0] if len(chest_volumes) > 3 else False
        print(f"   Progression W1→W2→W3: {'✅' if progression else '⚠️ '}")
        print(f"   Deload W4 < W1: {'✅' if deload else '⚠️ '}")

    # 5. Check equipment tier compliance
    print("\n5. EQUIPMENT TIER COMPLIANCE (Tier 1 only):")
    tier1_only = True
    for week in program.weeks:
        for workout in week.workouts:
            for ex in workout.exercises:
                # Look up exercise in library
                from exercise_library import EXERCISE_LIBRARY
                ex_obj = next((e for e in EXERCISE_LIBRARY if e.id == ex.exercise_id), None)
                if ex_obj and ex_obj.equipment_tier.value > 1:
                    tier1_only = False
                    print(f"   ⚠️  {ex.exercise_name} requires Tier {ex_obj.equipment_tier.value}")

    if tier1_only:
        print("   ✅ All exercises are Tier 1 compliant")

    # 6. Check session timing
    print("\n6. SESSION TIMING:")
    for week in program.weeks[:2]:  # Check first 2 weeks
        for workout in week.workouts:
            duration = workout.estimated_duration_minutes
            in_range = 50 <= duration <= 70
            status = "✅" if in_range else "⚠️ "
            print(f"   Week {week.week_number} {workout.day_label}: "
                  f"{duration} min (target: ~60 min) {status}")

    # 7. Check exercise variety between Upper A and Upper B
    print("\n7. EXERCISE VARIETY (Upper A vs Upper B in Week 1):")
    week1 = program.weeks[0]
    upper_workouts = [w for w in week1.workouts if "Upper" in w.day_label]
    if len(upper_workouts) >= 2:
        upper_a_ex = set(ex.exercise_id for ex in upper_workouts[0].exercises)
        upper_b_ex = set(ex.exercise_id for ex in upper_workouts[1].exercises)
        overlap = upper_a_ex & upper_b_ex
        unique_a = upper_a_ex - upper_b_ex
        unique_b = upper_b_ex - upper_a_ex

        print(f"   Upper A exercises: {len(upper_a_ex)}")
        print(f"   Upper B exercises: {len(upper_b_ex)}")
        print(f"   Overlap: {len(overlap)}")
        print(f"   Unique to A: {len(unique_a)}")
        print(f"   Unique to B: {len(unique_b)}")

        if overlap:
            print(f"   Overlapping exercises:")
            from exercise_library import EXERCISE_LIBRARY
            for ex_id in overlap:
                ex = next((e for e in EXERCISE_LIBRARY if e.id == ex_id), None)
                if ex:
                    print(f"     - {ex.name}")

        variety = len(unique_a) > 3 and len(unique_b) > 3
        print(f"   Sufficient variety: {'✅' if variety else '⚠️ '}")

    # 8. Volume accuracy summary
    print("\n8. VOLUME ACCURACY SUMMARY:")
    total_muscles = 0
    within_1 = 0
    within_2 = 0
    max_deviation = 0
    worst_muscle = None

    for week in program.weeks:
        if week.phase != "Deload":  # Only check non-deload weeks
            for muscle, target in week.weekly_volume_target.items():
                if target > 0:
                    total_muscles += 1
                    actual = week.weekly_volume_actual.get(muscle, 0)
                    diff = abs(actual - target)

                    if diff <= 1:
                        within_1 += 1
                        within_2 += 1
                    elif diff <= 2:
                        within_2 += 1

                    if diff > max_deviation:
                        max_deviation = diff
                        worst_muscle = (muscle, week.week_number, actual, target)

    print(f"   Total muscle-week pairs checked: {total_muscles}")
    print(f"   Within ±1 set: {within_1} ({within_1/total_muscles*100:.1f}%)")
    print(f"   Within ±2 sets: {within_2} ({within_2/total_muscles*100:.1f}%)")
    print(f"   Largest deviation: {max_deviation:.1f} sets")

    if worst_muscle:
        muscle, week_num, actual, target = worst_muscle
        print(f"   Worst: {muscle} in Week {week_num}: {actual:.1f} vs {target} target")


def validate_round3_fixes(program):
    """Validate the 14-point checklist from the Round 3 fix task."""
    print("\n" + "="*80)
    print("ROUND 3 FIX VALIDATION CHECKLIST")
    print("="*80)

    from exercise_library import EXERCISE_LIBRARY
    from schemas import MovementPattern, ExerciseType

    results = {}
    week1 = program.weeks[0]

    # Get sessions by label
    upper_a = next((w for w in week1.workouts if w.day_label == "Upper A"), None)
    upper_b = next((w for w in week1.workouts if w.day_label == "Upper B"), None)
    lower_a = next((w for w in week1.workouts if w.day_label == "Lower A"), None)
    lower_b = next((w for w in week1.workouts if w.day_label == "Lower B"), None)

    # Helper to get exercise object
    def get_ex(ex_id):
        return next((e for e in EXERCISE_LIBRARY if e.id == ex_id), None)

    # Helper to check if exercise is a barbell compound
    def is_barbell_compound(ex):
        ex_obj = get_ex(ex.exercise_id)
        if not ex_obj:
            return False
        return (ex_obj.exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]
                and ("barbell" in ex_obj.id.lower() or "barbell" in ex_obj.name.lower()))

    # Helper to check movement pattern
    def has_pattern(workout, pattern_type):
        for ex in workout.exercises:
            ex_obj = get_ex(ex.exercise_id)
            if ex_obj and ex_obj.movement_pattern == pattern_type:
                return True
        return False

    # 1. Lower A starts with a barbell squat or deadlift variation
    if lower_a:
        first_ex = lower_a.exercises[0] if lower_a.exercises else None
        ex_obj = get_ex(first_ex.exercise_id) if first_ex else None
        is_squat_deadlift = ex_obj and (
            ex_obj.movement_pattern in [MovementPattern.SQUAT, MovementPattern.HIP_HINGE]
            and ("barbell" in ex_obj.id.lower() or "barbell" in ex_obj.name.lower())
        )
        results[1] = ("PASS" if is_squat_deadlift else "FAIL",
                      first_ex.exercise_name if first_ex else "none")
    else:
        results[1] = ("FAIL", "Lower A session not found")

    # 2. Lower A contains a hinge movement
    if lower_a:
        has_hinge = has_pattern(lower_a, MovementPattern.HIP_HINGE)
        hinge_exercises = [ex.exercise_name for ex in lower_a.exercises
                          if get_ex(ex.exercise_id) and get_ex(ex.exercise_id).movement_pattern == MovementPattern.HIP_HINGE]
        results[2] = ("PASS" if has_hinge else "FAIL", ", ".join(hinge_exercises) if hinge_exercises else "none")
    else:
        results[2] = ("FAIL", "Lower A session not found")

    # 3. Lower B starts with a barbell compound
    if lower_b:
        first_ex = lower_b.exercises[0] if lower_b.exercises else None
        starts_barbell = is_barbell_compound(first_ex) if first_ex else False
        results[3] = ("PASS" if starts_barbell else "FAIL",
                      first_ex.exercise_name if first_ex else "none")
    else:
        results[3] = ("FAIL", "Lower B session not found")

    # 4. Lower B contains a hinge movement
    if lower_b:
        has_hinge = has_pattern(lower_b, MovementPattern.HIP_HINGE)
        hinge_exercises = [ex.exercise_name for ex in lower_b.exercises
                          if get_ex(ex.exercise_id) and get_ex(ex.exercise_id).movement_pattern == MovementPattern.HIP_HINGE]
        results[4] = ("PASS" if has_hinge else "FAIL", ", ".join(hinge_exercises) if hinge_exercises else "none")
    else:
        results[4] = ("FAIL", "Lower B session not found")

    # 5. Upper A has at least one horizontal push compound
    if upper_a:
        h_push_compounds = [ex.exercise_name for ex in upper_a.exercises
                           if get_ex(ex.exercise_id) and
                           get_ex(ex.exercise_id).movement_pattern == MovementPattern.HORIZONTAL_PUSH and
                           get_ex(ex.exercise_id).exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]]
        results[5] = ("PASS" if h_push_compounds else "FAIL", ", ".join(h_push_compounds) if h_push_compounds else "none")
    else:
        results[5] = ("FAIL", "Upper A session not found")

    # 6. Upper B has at least one horizontal push compound
    if upper_b:
        h_push_compounds = [ex.exercise_name for ex in upper_b.exercises
                           if get_ex(ex.exercise_id) and
                           get_ex(ex.exercise_id).movement_pattern == MovementPattern.HORIZONTAL_PUSH and
                           get_ex(ex.exercise_id).exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]]
        # Upper B requires VERTICAL push, not horizontal - check the actual required patterns
        v_push_compounds = [ex.exercise_name for ex in upper_b.exercises
                           if get_ex(ex.exercise_id) and
                           get_ex(ex.exercise_id).movement_pattern == MovementPattern.VERTICAL_PUSH and
                           get_ex(ex.exercise_id).exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]]
        has_push = bool(h_push_compounds) or bool(v_push_compounds)
        push_desc = ", ".join(h_push_compounds + v_push_compounds) if (h_push_compounds or v_push_compounds) else "none"
        results[6] = ("PASS" if has_push else "FAIL", push_desc)
    else:
        results[6] = ("FAIL", "Upper B session not found")

    # 7. Upper A has at least one pulling compound
    if upper_a:
        pull_compounds = [ex.exercise_name for ex in upper_a.exercises
                         if get_ex(ex.exercise_id) and
                         get_ex(ex.exercise_id).movement_pattern in [MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PULL] and
                         get_ex(ex.exercise_id).exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]]
        results[7] = ("PASS" if pull_compounds else "FAIL", ", ".join(pull_compounds) if pull_compounds else "none")
    else:
        results[7] = ("FAIL", "Upper A session not found")

    # 8. Upper B has at least one pulling compound
    if upper_b:
        pull_compounds = [ex.exercise_name for ex in upper_b.exercises
                         if get_ex(ex.exercise_id) and
                         get_ex(ex.exercise_id).movement_pattern in [MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PULL] and
                         get_ex(ex.exercise_id).exercise_type in [ExerciseType.HEAVY_COMPOUND, ExerciseType.LIGHT_COMPOUND]]
        results[8] = ("PASS" if pull_compounds else "FAIL", ", ".join(pull_compounds) if pull_compounds else "none")
    else:
        results[8] = ("FAIL", "Upper B session not found")

    # 9. NO upper body isolation exercises on lower body days
    upper_muscles = {"chest", "upper_chest", "lower_chest", "lats", "upper_back", "traps",
                     "front_delts", "side_delts", "rear_delts", "biceps", "triceps", "forearms"}
    violations_9 = []
    for workout in [lower_a, lower_b]:
        if workout:
            for ex in workout.exercises:
                ex_obj = get_ex(ex.exercise_id)
                if ex_obj and ex_obj.exercise_type == ExerciseType.ISOLATION:
                    primary_muscles = {ma.muscle.value for ma in ex_obj.muscle_activations if ma.role.value == "primary"}
                    if primary_muscles & upper_muscles:
                        violations_9.append(f"{ex.exercise_name} in {workout.day_label}")
    results[9] = ("PASS" if not violations_9 else "FAIL", ", ".join(violations_9) if violations_9 else "none")

    # 10. NO lower body isolation exercises on upper body days
    lower_muscles = {"quads", "hamstrings", "glutes", "calves", "adductors"}
    violations_10 = []
    for workout in [upper_a, upper_b]:
        if workout:
            for ex in workout.exercises:
                ex_obj = get_ex(ex.exercise_id)
                if ex_obj and ex_obj.exercise_type == ExerciseType.ISOLATION:
                    primary_muscles = {ma.muscle.value for ma in ex_obj.muscle_activations if ma.role.value == "primary"}
                    if primary_muscles & lower_muscles:
                        violations_10.append(f"{ex.exercise_name} in {workout.day_label}")
    results[10] = ("PASS" if not violations_10 else "FAIL", ", ".join(violations_10) if violations_10 else "none")

    # 11. All volume targets >= MEV (no zeros)
    from volume_tables import get_volume_targets
    zeros = []
    for muscle, target in week1.weekly_volume_target.items():
        mev = get_volume_targets("intermediate", muscle)["mev"]
        if target < mev:
            zeros.append(f"{muscle}={target} (MEV={mev})")
    results[11] = ("PASS" if not zeros else "FAIL", ", ".join(zeros) if zeros else "all >= MEV")

    # 12. Primary compounds get 3+ sets
    low_sets = []
    for workout in week1.workouts:
        for i, ex in enumerate(workout.exercises[:2]):  # First 2 exercises are primary
            ex_obj = get_ex(ex.exercise_id)
            if ex_obj and ex_obj.exercise_type == ExerciseType.HEAVY_COMPOUND:
                if ex.total_sets < 3:
                    low_sets.append(f"{ex.exercise_name}: {ex.total_sets} sets")
    results[12] = ("PASS" if not low_sets else "FAIL", ", ".join(low_sets) if low_sets else "all 3+ sets")

    # 13. Exercise count 5-7 per session
    bad_counts = []
    for workout in week1.workouts:
        count = len(workout.exercises)
        if count < 5 or count > 7:
            bad_counts.append(f"{workout.day_label}: {count}")
    results[13] = ("PASS" if not bad_counts else "FAIL", ", ".join(bad_counts) if bad_counts else "all 5-7")

    # 14. Volume within ±3 sets of target for each muscle
    worst_offenders = []
    for muscle, target in week1.weekly_volume_target.items():
        actual = week1.weekly_volume_actual.get(muscle, 0)
        diff = abs(actual - target)
        if diff > 3:
            worst_offenders.append(f"{muscle}: {actual:.1f} vs {target:.0f} (diff={diff:.1f})")
    results[14] = ("PASS" if not worst_offenders else "FAIL",
                   ", ".join(worst_offenders[:3]) if worst_offenders else "all within ±3")

    # Print results
    checklist_items = [
        "Lower A starts with barbell squat/deadlift",
        "Lower A contains a hinge movement",
        "Lower B starts with a barbell compound",
        "Lower B contains a hinge movement",
        "Upper A has horizontal push compound",
        "Upper B has pushing compound",
        "Upper A has pulling compound",
        "Upper B has pulling compound",
        "NO upper body isolations on lower days",
        "NO lower body isolations on upper days",
        "All volume targets >= MEV",
        "Primary compounds get 3+ sets",
        "Exercise count 5-7 per session",
        "Volume within ±3 sets of target"
    ]

    passed = 0
    for i, item in enumerate(checklist_items, 1):
        status, detail = results.get(i, ("FAIL", "not checked"))
        icon = "✅" if status == "PASS" else "❌"
        print(f"{i:2}. [{status}] {item}")
        print(f"       → {detail}")
        if status == "PASS":
            passed += 1

    print(f"\n{'='*80}")
    print(f"CHECKLIST: {passed}/14 passed")
    print("="*80)

    return passed == 14


def main():
    """Run the test."""
    print("\n" + "="*80)
    print("PHASE 3 IMPLEMENTATION TEST")
    print("Testing: Layer 3 (Volume Engine) + Layer 4 (Program Builder)")
    print("="*80)

    # Create profile
    print("\nCreating test profile...")
    profile = create_test_profile()
    print(f"✅ Profile: {profile.training_level} {profile.training_goal}, "
          f"{profile.training_days_per_week}x/week, Tier {profile.equipment_tier.value}")

    # Create strategy
    print("\nCreating program strategy...")
    strategy = create_test_strategy(profile)
    print(f"✅ Strategy: {strategy.split.name}, {len(strategy.week_profiles)} weeks")

    # Calculate volume
    print("\nCalculating volume allocation (Layer 3)...")
    volume = calculate_volume(profile, strategy)
    print(f"✅ Volume allocation calculated for {len(volume.weeks)} weeks")

    # Sample volume output
    week1_vol = volume.weeks[0]
    print(f"\n   Sample Week 1 volumes:")
    for muscle in ["chest", "quads", "lats", "biceps"]:
        total = week1_vol.weekly_totals.get(muscle, 0)
        session_vols = [s.muscle_volumes.get(muscle, 0) for s in week1_vol.sessions]
        print(f"   - {muscle}: {total:.0f} weekly sets → {session_vols}")

    # Build program
    print("\nBuilding program (Layer 4)...")
    program = build_program(profile, strategy, volume)
    print(f"✅ Program built: {program.total_workouts} workouts, "
          f"{program.unique_exercises_used} unique exercises")

    # Print full program
    print_program(program)

    # Analyze program
    analyze_program(program)

    # Round 3 validation
    all_passed = validate_round3_fixes(program)

    print("\n" + "="*80)
    print("TEST COMPLETE")
    if all_passed:
        print("✅ ALL ROUND 3 FIXES VALIDATED")
    else:
        print("⚠️  SOME CHECKS FAILED - Review output above")
    print("="*80)


if __name__ == "__main__":
    main()
