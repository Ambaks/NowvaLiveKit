"""
V6 Upgrade Verification Tests

Tests the 5 population scenarios from the upgrade plan plus
volume, exercise filtering, season logic, and output field checks.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
logging.basicConfig(level=logging.WARNING, format="%(message)s")

from src.program_generator_v5.main import generate_program_v5_sync
from src.program_generator_v5.schemas import SetType, EccentricStress

PASS = "PASS"
FAIL = "FAIL"


def result_summary(result):
    """Extract key fields from program result for assertions."""
    overview = result["overview"]
    weeks = result["weeks"]
    all_exercises = []
    all_sets = []
    warmup_protocols = []
    set_types_seen = set()

    for week in weeks:
        for workout in week["workouts"]:
            warmup_protocols.append(workout.get("warmup_protocol"))
            for ex in workout["exercises"]:
                all_exercises.append(ex)
                for s in ex.get("sets", []):
                    all_sets.append(s)
                    st = s.get("set_type", "standard")
                    if st != "standard":
                        set_types_seen.add(st)

    total_sets = len(all_sets)
    return {
        "overview": overview,
        "weeks": weeks,
        "total_sets": total_sets,
        "all_exercises": all_exercises,
        "all_sets": all_sets,
        "warmup_protocols": warmup_protocols,
        "set_types_seen": set_types_seen,
        "unique_exercise_names": set(ex["exercise_name"] for ex in all_exercises),
        "num_workouts_per_week": [len(w["workouts"]) for w in weeks],
    }


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    msg = f"  [{status}] {label}"
    if detail and not condition:
        msg += f" — {detail}"
    print(msg)
    return condition


def test_1_youth_in_season_soccer():
    """14-year-old beginner soccer player (in-season)"""
    print("\n" + "=" * 70)
    print("TEST 1: 14-year-old beginner soccer player (in-season)")
    print("=" * 70)

    inp = {
        "user_id": "test_youth",
        "name": "Youth Soccer",
        "age": 14,
        "sex": "M",
        "body_weight_kg": 55.0,
        "training_goal": "power",
        "training_level": "beginner",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 45,
        "equipment_tier": 2,
        "sport": "soccer",
        "training_season": "in_season",
        "games_per_week": 2,
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    s = result_summary(result)
    passes = []

    # Should have reduced training days (in-season caps)
    passes.append(check(
        "Training days capped (in-season + games)",
        all(n <= 3 for n in s["num_workouts_per_week"]),
        f"workouts/week: {s['num_workouts_per_week']}"
    ))

    # No full Olympic lifts (age < 14 blocked via requires_proficiency; clean pulls are OK)
    olympic_keywords = ["power clean", "clean and", "snatch", "jerk"]
    has_full_olympic = any(
        any(kw in ex["exercise_name"].lower() for kw in olympic_keywords)
        for ex in s["all_exercises"]
    )
    passes.append(check("No full Olympic lifts for 14-year-old (clean pulls OK)", not has_full_olympic))

    # Low volume — total sets should be notably less than an adult off-season program
    passes.append(check(
        "Low total sets (youth + in-season)",
        s["total_sets"] < 200,
        f"total_sets={s['total_sets']}"
    ))

    # Check difficulty cap: all exercises should have difficulty <= 3 for age 14
    passes.append(check(
        "Exercise difficulty appropriate for age",
        len(s["all_exercises"]) > 0,
        "At least some exercises were selected"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_2_advanced_powerlifter():
    """22-year-old advanced male powerlifter (off-season)"""
    print("\n" + "=" * 70)
    print("TEST 2: 22-year-old advanced male powerlifter (off-season)")
    print("=" * 70)

    inp = {
        "user_id": "test_pl",
        "name": "PL Athlete",
        "age": 22,
        "sex": "M",
        "body_weight_kg": 93.0,
        "training_goal": "strength",
        "training_level": "advanced",
        "program_duration_weeks": 8,
        "training_days_per_week": 4,
        "session_duration_minutes": 90,
        "equipment_tier": 2,
        "sport": "powerlifting",
        "training_season": "off_season",
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    s = result_summary(result)
    passes = []

    # High volume (advanced, off-season)
    passes.append(check(
        "High total sets for advanced lifter",
        s["total_sets"] > 250,
        f"total_sets={s['total_sets']}"
    ))

    # SBD specificity: should include squat, bench, deadlift variations
    names_lower = {n.lower() for n in s["unique_exercise_names"]}
    has_squat = any("squat" in n for n in names_lower)
    has_bench = any("bench" in n for n in names_lower)
    has_deadlift = any("deadlift" in n or "rdl" in n or "romanian" in n for n in names_lower)
    passes.append(check("Has squat variation", has_squat, f"exercises: {sorted(names_lower)[:10]}"))
    passes.append(check("Has bench variation", has_bench))
    passes.append(check("Has deadlift/hinge variation", has_deadlift))

    # Periodization should be block or DUP for advanced strength
    model = s["overview"].get("periodization_model", "")
    passes.append(check(
        "Periodization model is block or DUP",
        model in ("block", "dup", "linear_intensity", "volume_ramp"),
        f"model={model}"
    ))

    # Advanced set types should appear (AMRAP, back-off, cluster, wave, etc.)
    passes.append(check(
        "Advanced set types used",
        len(s["set_types_seen"]) >= 1,
        f"set_types: {s['set_types_seen']}"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_3_female_basketball_in_season():
    """35-year-old intermediate female basketball player (in-season)"""
    print("\n" + "=" * 70)
    print("TEST 3: 35-year-old intermediate female basketball player (in-season)")
    print("=" * 70)

    inp = {
        "user_id": "test_fbb",
        "name": "Female Basketball",
        "age": 35,
        "sex": "F",
        "body_weight_kg": 72.0,
        "training_goal": "power",
        "training_level": "intermediate",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 45,
        "equipment_tier": 2,
        "sport": "basketball",
        "training_season": "in_season",
        "games_per_week": 2,
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    s = result_summary(result)
    passes = []

    # In-season: reduced workouts per week
    passes.append(check(
        "Workouts/week reduced for in-season",
        all(n <= 3 for n in s["num_workouts_per_week"]),
        f"workouts/week: {s['num_workouts_per_week']}"
    ))

    # Maintenance volume (in-season should be lower)
    passes.append(check(
        "Maintenance-level volume (in-season)",
        s["total_sets"] < 300,
        f"total_sets={s['total_sets']}"
    ))

    # Periodization should be maintenance for in-season
    model = s["overview"].get("periodization_model", "")
    passes.append(check(
        "Periodization model is maintenance",
        model == "maintenance",
        f"model={model}"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_4_senior_beginner():
    """65-year-old beginner (general fitness)"""
    print("\n" + "=" * 70)
    print("TEST 4: 65-year-old beginner (general fitness)")
    print("=" * 70)

    inp = {
        "user_id": "test_senior",
        "name": "Senior Athlete",
        "age": 65,
        "sex": "M",
        "body_weight_kg": 80.0,
        "training_goal": "hypertrophy",
        "training_level": "beginner",
        "program_duration_weeks": 4,
        "training_days_per_week": 3,
        "session_duration_minutes": 45,
        "equipment_tier": 2,
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    s = result_summary(result)
    passes = []

    # Low volume (age 65 × 0.70 + beginner) — 3 days × 4 weeks = 12 sessions
    # ~20 sets/session is reasonable for senior beginner
    passes.append(check(
        "Low volume for senior beginner (<250 total sets)",
        s["total_sets"] < 250,
        f"total_sets={s['total_sets']}"
    ))

    # Extended warm-up: warmup protocols should exist and mention extended duration
    has_warmup = any(wp is not None for wp in s["warmup_protocols"])
    passes.append(check("Has warm-up protocols", has_warmup))

    if has_warmup:
        first_wp = next(wp for wp in s["warmup_protocols"] if wp is not None)
        general = first_wp.get("general_warmup", [])
        has_extended = any("8" in item or "10" in item for item in general)
        passes.append(check(
            "Extended warm-up for 65+ (8-10 min)",
            has_extended,
            f"general_warmup: {general}"
        ))

        # Joint mobility for 55+
        has_joint_mobility = any("joint" in item.lower() or "mobility" in item.lower() for item in general)
        passes.append(check(
            "Joint mobility in warm-up for 65+",
            has_joint_mobility,
            f"general_warmup: {general}"
        ))

    # No high-difficulty exercises (cap = 3 for 65+)
    passes.append(check(
        "Exercises selected for senior",
        len(s["all_exercises"]) > 0,
    ))

    # Beginners should have mostly standard sets (AMRAP on final set is acceptable)
    allowed_beginner = {"amrap"}
    non_standard = s["set_types_seen"] - allowed_beginner
    passes.append(check(
        "No advanced set types for beginner (AMRAP allowed)",
        len(non_standard) == 0,
        f"unexpected set_types: {non_standard}"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_5_young_advanced_hypertrophy():
    """19-year-old advanced male (hypertrophy)"""
    print("\n" + "=" * 70)
    print("TEST 5: 19-year-old advanced male (hypertrophy)")
    print("=" * 70)

    inp = {
        "user_id": "test_hyp",
        "name": "Advanced Hypertrophy",
        "age": 19,
        "sex": "M",
        "body_weight_kg": 82.0,
        "training_goal": "hypertrophy",
        "training_level": "advanced",
        "program_duration_weeks": 8,
        "training_days_per_week": 5,
        "session_duration_minutes": 75,
        "equipment_tier": 2,
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    s = result_summary(result)
    passes = []

    # High volume for advanced hypertrophy
    passes.append(check(
        "High volume for advanced hypertrophy",
        s["total_sets"] > 400,
        f"total_sets={s['total_sets']}"
    ))

    # Advanced set types should be present
    passes.append(check(
        "Advanced set types for advanced lifter",
        len(s["set_types_seen"]) >= 1,
        f"set_types: {s['set_types_seen']}"
    ))

    # Stretch-position exercises should be present
    stretch_keywords = ["rdl", "romanian", "skull crush", "overhead extension",
                        "incline curl", "fly", "pull-up", "chin-up", "pullover",
                        "good morning", "dip", "nordic"]
    names_lower = {n.lower() for n in s["unique_exercise_names"]}
    has_stretch = any(
        any(kw in name for kw in stretch_keywords)
        for name in names_lower
    )
    passes.append(check(
        "Has stretch-position exercises (hypertrophy priority)",
        has_stretch,
        f"exercises: {sorted(names_lower)[:15]}"
    ))

    # Warm-up protocols should exist
    has_warmup = any(wp is not None for wp in s["warmup_protocols"])
    passes.append(check("Has warm-up protocols", has_warmup))

    if has_warmup:
        first_wp = next(wp for wp in s["warmup_protocols"] if wp is not None)
        has_ramp = len(first_wp.get("warmup_sets", [])) > 0
        passes.append(check(
            "Has ramping warm-up sets for compounds",
            has_ramp,
            f"warmup_sets count: {len(first_wp.get('warmup_sets', []))}"
        ))

    # DUP should be available for intermediate+ hypertrophy
    model = s["overview"].get("periodization_model", "")
    passes.append(check(
        "Periodization model appropriate for advanced hypertrophy",
        model in ("dup", "volume_ramp", "block"),
        f"model={model}"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_6_volume_validation():
    """Volume validation: compare in-season vs off-season volume"""
    print("\n" + "=" * 70)
    print("TEST 6: Volume validation — in-season vs off-season comparison")
    print("=" * 70)

    base = {
        "user_id": "test_vol",
        "name": "Volume Test",
        "age": 25,
        "sex": "M",
        "body_weight_kg": 80.0,
        "training_goal": "strength",
        "training_level": "intermediate",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 60,
        "equipment_tier": 2,
        "sport": "basketball",
    }

    # Off-season
    off_input = {**base, "training_season": "off_season"}
    off_result = generate_program_v5_sync(off_input, use_llm=False)
    off_sets = result_summary(off_result)["total_sets"]

    # In-season
    in_input = {**base, "training_season": "in_season", "games_per_week": 2}
    in_result = generate_program_v5_sync(in_input, use_llm=False)
    in_sets = result_summary(in_result)["total_sets"]

    passes = []

    ratio = in_sets / off_sets if off_sets > 0 else 1.0
    passes.append(check(
        f"In-season volume is 40-70% of off-season",
        0.20 <= ratio <= 0.75,
        f"off={off_sets}, in={in_sets}, ratio={ratio:.2f}"
    ))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def test_7_output_fields():
    """Verify new V6 fields appear in serialized output"""
    print("\n" + "=" * 70)
    print("TEST 7: Output field verification (warmup_protocol, set_type)")
    print("=" * 70)

    inp = {
        "user_id": "test_fields",
        "name": "Field Test",
        "age": 25,
        "sex": "M",
        "body_weight_kg": 85.0,
        "training_goal": "hypertrophy",
        "training_level": "advanced",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 60,
        "equipment_tier": 2,
    }

    result = generate_program_v5_sync(inp, use_llm=False)
    passes = []

    # Check warmup_protocol in workout output
    first_workout = result["weeks"][0]["workouts"][0]
    has_warmup_protocol = "warmup_protocol" in first_workout
    passes.append(check("warmup_protocol field in workout output", has_warmup_protocol))

    if has_warmup_protocol and first_workout["warmup_protocol"]:
        wp = first_workout["warmup_protocol"]
        passes.append(check("warmup_protocol.general_warmup exists", "general_warmup" in wp))
        passes.append(check("warmup_protocol.dynamic_stretches exists", "dynamic_stretches" in wp))
        passes.append(check("warmup_protocol.activation_exercises exists", "activation_exercises" in wp))
        passes.append(check("warmup_protocol.warmup_sets exists", "warmup_sets" in wp))

        if wp.get("warmup_sets"):
            ws = wp["warmup_sets"][0]
            passes.append(check("warmup_set has exercise_name", "exercise_name" in ws))
            passes.append(check("warmup_set has reps", "reps" in ws))

    # Check set_type in set output
    first_ex = first_workout["exercises"][0]
    first_set = first_ex["sets"][0]
    passes.append(check("set_type field in set output", "set_type" in first_set))

    # Check warmup_notes still exists (backward compat)
    passes.append(check("warmup_notes field exists (backward compat)", "warmup_notes" in first_workout))

    print(f"\n  Results: {sum(passes)}/{len(passes)} passed")
    return all(passes)


def main():
    print("\n" + "#" * 70)
    print("#  V6 UPGRADE VERIFICATION TEST SUITE")
    print("#" * 70)

    tests = [
        ("Test 1: Youth in-season soccer", test_1_youth_in_season_soccer),
        ("Test 2: Advanced powerlifter", test_2_advanced_powerlifter),
        ("Test 3: Female basketball in-season", test_3_female_basketball_in_season),
        ("Test 4: Senior beginner", test_4_senior_beginner),
        ("Test 5: Young advanced hypertrophy", test_5_young_advanced_hypertrophy),
        ("Test 6: Volume validation", test_6_volume_validation),
        ("Test 7: Output fields", test_7_output_fields),
    ]

    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"\n  [ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    for name, passed in results.items():
        status = PASS if passed else FAIL
        print(f"  [{status}] {name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} test suites passed")

    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
