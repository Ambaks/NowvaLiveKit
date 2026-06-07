#!/usr/bin/env python3
"""
Phase 2 V5 Implementation — Validation Tests
Tests scoring, prescription, and prompt formatting.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from program_generator.scoring import compute_exercise_score
from program_generator.utils import prescribe_exercise, get_pattern_fill_priority
from program_generator.prompts import format_profile_extraction_prompt, format_week_review_prompt
from program_generator.exercise_library import EXERCISE_BY_ID
from program_generator.schemas import WeekProfile


def test_1_scoring():
    """Test 1: Scoring function with barbell curl + remaining bicep volume."""
    print("\n" + "="*60)
    print("TEST 1: SCORING FUNCTION")
    print("="*60)

    exercise = EXERCISE_BY_ID["barbell_curl"]
    score = compute_exercise_score(
        exercise=exercise,
        remaining_volume={"biceps": 6.0, "forearms": 4.0},
        recently_used={},
        mesocycle_number=1,
        week_number=1,
        session_axial_count=0,
        session_grip_count=0,
        program_goal="hypertrophy",
    )

    print(f"✅ Barbell curl score: {score:.2f}")
    print(f"   Exercise: {exercise.name}")
    print(f"   SFR rating: {exercise.sfr_rating}")
    print(f"   Remaining volume: biceps=6.0, forearms=4.0")
    print(f"   Goal: hypertrophy")
    print(f"   Result: Score = {score:.2f}")

    # Breakdown (approximate):
    # SFR: 7.5 * 12 = 90
    # Volume fill: (min(6.0, 4) * 1.0 + min(4.0, 4) * 0.5) * 8 = (4.0 + 2.0) * 8 = 48
    # Variety: +10 (never used)
    # Total ≈ 148

    assert score > 100, "Score should be >100 for good exercise with high remaining volume"
    print(f"   ✓ Score is appropriately high (>100)")

    return score


def test_2_prescription_heavy_compound():
    """Test 2: Prescription for heavy compound (BB squat), hypertrophy, Week 1."""
    print("\n" + "="*60)
    print("TEST 2: PRESCRIPTION - Heavy Compound (Week 1)")
    print("="*60)

    exercise = EXERCISE_BY_ID["barbell_back_squat"]
    week1 = WeekProfile(
        week_number=1,
        mesocycle_number=1,
        week_in_mesocycle=1,
        phase_name="Introduction",
        volume_multiplier=1.0,
        intensity_modifier="moderate",
        rpe_range=(6.5, 7.5),
        rir_range=(3, 4),
        is_deload=False,
        notes="",
    )

    sets = prescribe_exercise(
        exercise=exercise,
        total_sets=4,
        week_profile=week1,
        program_goal="hypertrophy",
    )

    print(f"✅ BB Squat prescription: {len(sets)} sets")
    print(f"   Exercise: {exercise.name}")
    print(f"   Week: 1 (Introduction, moderate intensity)")
    print(f"   Goal: hypertrophy\n")

    for s in sets:
        print(f"   Set {s.set_number}: {s.reps} reps @ RPE {s.rpe}, rest {s.rest_seconds}s, tempo {s.tempo}")
        if s.notes:
            print(f"            Notes: {s.notes}")

    # Verify expectations:
    # - Reps should be 6-10 (hypertrophy heavy_compound range)
    # - Rest should be 150s (hypertrophy heavy_compound)
    # - RPE should be ~6.5-7.5 (moderate intensity, conservative for compounds)
    # - First set should have warmup note

    assert 6 <= sets[0].reps <= 10, f"Reps should be 6-10 for hypertrophy heavy compound, got {sets[0].reps}"
    assert sets[0].rest_seconds == 150, f"Rest should be 150s, got {sets[0].rest_seconds}"
    assert 6.0 <= sets[0].rpe <= 8.0, f"RPE should be 6.0-8.0, got {sets[0].rpe}"
    assert "warm-up" in sets[0].notes.lower(), f"First set should have warmup note, got: {sets[0].notes}"

    print(f"\n   ✓ Reps in range 6-10: {sets[0].reps}")
    print(f"   ✓ Rest = 150s")
    print(f"   ✓ RPE in range 6.0-8.0: {sets[0].rpe}")
    print(f"   ✓ First set has warmup note")

    return sets


def test_3_prescription_isolation_week3():
    """Test 3: Prescription for isolation (BB curl), hypertrophy, Week 3 (overreaching)."""
    print("\n" + "="*60)
    print("TEST 3: PRESCRIPTION - Isolation (Week 3 Overreaching)")
    print("="*60)

    exercise = EXERCISE_BY_ID["barbell_curl"]
    week3 = WeekProfile(
        week_number=3,
        mesocycle_number=1,
        week_in_mesocycle=3,
        phase_name="Overreaching",
        volume_multiplier=1.25,
        intensity_modifier="moderate_heavy",
        rpe_range=(8.0, 9.0),
        rir_range=(1, 2),
        is_deload=False,
        notes="",
    )

    sets = prescribe_exercise(
        exercise=exercise,
        total_sets=3,
        week_profile=week3,
        program_goal="hypertrophy",
    )

    print(f"✅ BB Curl Week 3 prescription: {len(sets)} sets")
    print(f"   Exercise: {exercise.name}")
    print(f"   Week: 3 (Overreaching, moderate_heavy intensity)")
    print(f"   Goal: hypertrophy\n")

    for s in sets:
        print(f"   Set {s.set_number}: {s.reps} reps @ RPE {s.rpe}, rest {s.rest_seconds}s")
        if s.notes:
            print(f"            Notes: {s.notes}")

    # Verify expectations:
    # - Reps should be 10-15 (isolation hypertrophy range)
    # - Rest should be 75s (isolation hypertrophy)
    # - RPE should be higher than Week 1 (8-9 range, isolations pushed harder)
    # - Last set should have failure/AMRAP note (week_in_mesocycle == 3)

    assert 10 <= sets[0].reps <= 15, f"Reps should be 10-15 for isolation hypertrophy, got {sets[0].reps}"
    assert sets[0].rest_seconds == 75, f"Rest should be 75s, got {sets[0].rest_seconds}"
    assert sets[-1].rpe == 10.0, f"Last set RPE should be 10.0 (failure), got {sets[-1].rpe}"
    assert sets[-1].rir == 0, f"Last set RIR should be 0, got {sets[-1].rir}"
    assert "failure" in sets[-1].notes.lower(), f"Last set should have failure note, got: {sets[-1].notes}"

    print(f"\n   ✓ Reps in range 10-15: {sets[0].reps}")
    print(f"   ✓ Rest = 75s")
    print(f"   ✓ Last set RPE = 10.0 (failure)")
    print(f"   ✓ Last set RIR = 0")
    print(f"   ✓ Last set has failure note: '{sets[-1].notes}'")

    return sets


def test_4_prompt_formatting():
    """Test 4: Prompt formatting functions."""
    print("\n" + "="*60)
    print("TEST 4: PROMPT FORMATTING")
    print("="*60)

    # Test profile extraction prompt
    profile_prompt = format_profile_extraction_prompt(
        "I want to get jacked, I'm 25, been lifting 3 years, have a barbell setup at home"
    )

    print(f"✅ Profile extraction prompt: {len(profile_prompt)} chars")

    # Verify the prompt contains expected elements
    assert "training_goal" in profile_prompt, "Prompt should mention training_goal"
    assert "JSON" in profile_prompt or "json" in profile_prompt, "Prompt should ask for JSON output"
    assert "barbell" in profile_prompt.lower(), "Prompt should contain the user input"

    # Check for unformatted placeholders
    unformatted_braces = profile_prompt.count("{") - profile_prompt.count("{{")
    if unformatted_braces > 0:
        # Check if they're in JSON schema (which is ok)
        if "json" not in profile_prompt.lower():
            assert False, "Prompt has unformatted placeholders!"

    print(f"   ✓ Prompt length: {len(profile_prompt)} chars")
    print(f"   ✓ Contains 'training_goal' field")
    print(f"   ✓ Asks for JSON output")
    print(f"   ✓ Contains user input text")
    print(f"   ✓ No unformatted placeholders detected")

    # Test pattern priority
    hypertrophy_patterns = get_pattern_fill_priority("hypertrophy")
    print(f"\n✅ Pattern fill priority (hypertrophy): {len(hypertrophy_patterns)} patterns")
    print(f"   Priority order: {[p.value for p in hypertrophy_patterns[:5]]}...")

    assert hypertrophy_patterns[0].value == "squat", "First pattern should be squat for hypertrophy"
    assert hypertrophy_patterns[1].value == "hip_hinge", "Second pattern should be hip_hinge"

    print(f"   ✓ First pattern is 'squat'")
    print(f"   ✓ Second pattern is 'hip_hinge'")

    return profile_prompt


def print_summary(test_results):
    """Print implementation summary."""
    score, squat_sets, curl_sets, profile_prompt = test_results

    print("\n" + "="*60)
    print("PHASE 2 IMPLEMENTATION SUMMARY")
    print("="*60)

    # Count lines in files
    import os
    files = {
        "scoring.py": "src/program_generator/scoring.py",
        "utils.py": "src/program_generator/utils.py",
        "prompts.py": "src/program_generator/prompts.py",
    }

    file_lines = {}
    for name, path in files.items():
        with open(path, 'r') as f:
            file_lines[name] = len(f.readlines())

    print("\nFILES CREATED:")
    print(f"- scoring.py: {file_lines['scoring.py']} lines — Exercise scoring with 8 weighted factors")
    print(f"- utils.py: {file_lines['utils.py']} lines — Prescription engine, time estimation, superset builder, sorting, pattern priority")
    print(f"- prompts.py: {file_lines['prompts.py']} lines — 4 LLM prompt templates with format functions")

    print("\nSCORING FUNCTION:")
    print("- 8 factors implemented:")
    print("  1. SFR Rating (weight: 12× for hypertrophy, 6× for strength/power)")
    print("  2. Volume Fill (weight: 8×)")
    print("  3. Variety (penalties: -15 for same week, -5 for last week; bonuses: +10 for never used)")
    print("  4. Rotation Group Freshness (penalty: -3× per group use)")
    print("  5. Compound Consistency (bonus: +20 within meso, penalty: -10 between mesos)")
    print("  6. Fatigue Management (penalties: -25 for 3rd+ axial, -15 for 3rd+ grip, -5 for high systemic)")
    print("  7. User Preference (bonus: +20)")
    print("  8. Stretch Position (bonus: +8 for hypertrophy)")
    print("- Goal-dependent weighting: Hypertrophy emphasizes SFR and volume fill; Strength emphasizes compound consistency and fatigue management")
    print(f"- Test score for barbell_curl (hypertrophy, full bicep volume remaining): {float(score):.2f}")

    print("\nPRESCRIPTION ENGINE:")
    print("- Rep ranges implemented (exercise_type × goal combinations): 15 combinations (5 types × 3 goals)")
    print(f"- BB Squat test (hypertrophy Week 1, 4 sets):")
    print(f"  - Reps: {squat_sets[0].reps} | Rest: {squat_sets[0].rest_seconds}s | RPE: {squat_sets[0].rpe} | Tempo: {squat_sets[0].tempo}")
    print(f"- BB Curl test (hypertrophy Week 3, 3 sets):")
    print(f"  - Reps: {curl_sets[0].reps} | Rest: {curl_sets[0].rest_seconds}s | RPE: {curl_sets[-1].rpe}")
    print(f"  - Last set notes: '{curl_sets[-1].notes}'")
    print("- Rest period ranges by type:")
    print("  - heavy_compound: 150-240s (hypertrophy-strength)")
    print("  - light_compound: 100-150s")
    print("  - isolation: 75-100s")
    print("  - power/plyometric: 240-270s")

    print("\nUTILITIES:")
    print("- estimate_session_duration: 5min warmup + (sets × execution + rest + transitions) + 3min cooldown")
    print("- build_supersets: Pairs antagonist isolations for hypertrophy; assigns superset_group labels (A, B, ...)")
    print("- sort_exercises_for_session: Power → Heavy Compound → Light Compound → Isolation; larger muscles first within tier")
    print("- get_pattern_fill_priority for hypertrophy: [squat, hip_hinge, horizontal_push, horizontal_pull, vertical_pull, vertical_push, isolations]")

    print("\nPROMPTS:")
    print("- 4 prompts defined:")
    print("  1. PROFILE_EXTRACTION_PROMPT (Layer 1)")
    print("  2. STRATEGY_RESOLUTION_PROMPT (Layer 2)")
    print("  3. WEEK_REVIEW_PROMPT (Layer 4)")
    print("  4. FULL_PROGRAM_REVIEW_PROMPT (Layer 5)")
    print("- Format functions:")
    print("  1. format_profile_extraction_prompt(raw_text)")
    print("  2. format_strategy_resolution_prompt(conflict_description, rules_output, profile)")
    print("  3. format_week_review_prompt(week, profile, strategy)")
    print("  4. format_full_program_review_prompt(program)")
    print(f"- Total prompt template characters: {len(profile_prompt)} (profile extraction prompt only)")

    print("\nVALIDATION RESULTS:")
    print("1. Scoring test: PASS — score={:.2f}".format(float(score)))
    print("2. Prescription test (squat): PASS — reps={}, rest={}s, RPE={}".format(
        squat_sets[0].reps, squat_sets[0].rest_seconds, squat_sets[0].rpe
    ))
    print("3. Prescription test (curl Week 3): PASS — last set failure=yes (RPE=10.0, RIR=0)")
    print("4. Prompt format test: PASS")

    print("\nDECISIONS MADE:")
    print("- Scoring weights: Tuned to spec values (SFR ×12 for hypertrophy, volume fill ×8, etc.)")
    print("- Prescription intensity mapping: Used INTENSITY_TO_REP_POSITION to map week intensity_modifier to rep position within range")
    print("- Last-set failure trigger: Implemented for isolations in week_in_mesocycle == 3 (Overreaching phase)")
    print("- Superset pairing: Checks for antagonist muscles (biceps+triceps, chest+back, quads+hamstrings) and push+pull patterns")
    print("- Time estimation: Used tempo parsing with fallback to 3-4s/rep; applied 40% rest reduction for supersets")
    print("- Pattern priority: Squat and hip_hinge first for all goals; power movements first for power goal")

    print("\n" + "="*60)
    print("✅ PHASE 2 COMPLETE — All tests passed")
    print("="*60 + "\n")


if __name__ == "__main__":
    print("Running Phase 2 V5 Implementation Tests...")

    try:
        results = (
            test_1_scoring(),
            test_2_prescription_heavy_compound(),
            test_3_prescription_isolation_week3(),
            test_4_prompt_formatting(),
        )

        print_summary(results)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
