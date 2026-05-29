"""
V5 Program Generator — Main Orchestrator

The async entry point for the V5 program generation pipeline.

Pipeline steps:
1. Layer 1: Build profile (structured or NL)
2. Layer 2: Build strategy (rules + optional LLM)
3. Layer 3: Calculate volume (deterministic)
4. Layer 4A: Build program (deterministic)
5. Layer 4B: LLM week review (parallel, if use_llm)
6. Layer 5: Validate + auto-fix + LLM full review (if use_llm)
7. Layer 6: Serialize to output format

Target: 10-20 seconds total with LLM calls, <1 second without.
"""

from __future__ import annotations

import asyncio
import time
import logging

from .layer1_profile_builder import build_profile_from_structured, build_profile_from_natural_language
from .layer2_strategy_engine import build_strategy
from .layer3_volume_engine import calculate_volume
from .layer4_program_builder import build_program, review_and_refine_program
from .layer5_validator import validate_and_fix, llm_full_program_review, get_validation_summary
from .layer6_serializer import serialize_to_v3


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT — ASYNC
# ─────────────────────────────────────────────────────────────────────────────


async def generate_program_v5(
    input_data: dict,
    openai_client=None,
    use_llm: bool = True,
    input_type: str = "structured",
) -> dict:
    """
    V5 Program Generator — Full Pipeline.

    Args:
        input_data: Dict with user/profile data
        openai_client: OpenAI async client (optional)
        use_llm: Whether to use LLM calls (set False for testing)
        input_type: "structured" or "natural_language"

    Returns:
        Serialized program dict ready for API response or storage
    """
    start_time = time.time()
    timings = {}

    # ── Layer 1: Profile Builder ────────────────────────────────────────────
    layer_start = time.time()
    logger.info("[Layer 1] Building athlete profile...")

    if input_type == "natural_language" and openai_client and use_llm:
        text = input_data.get("text", input_data.get("transcript", ""))
        profile = await build_profile_from_natural_language(
            text=text,
            openai_client=openai_client,
            defaults=input_data,
        )
    else:
        profile = build_profile_from_structured(input_data)

    timings["layer1"] = time.time() - layer_start
    logger.info(f"  ✓ Goal: {profile.effective_goal}, Level: {profile.training_level}, Tier: {profile.equipment_tier}")
    logger.info(f"  ✓ Available exercises: {len(profile.available_exercises)}")
    if profile.exercise_coverage_warnings:
        logger.warning(f"  ⚠ Coverage warnings: {profile.exercise_coverage_warnings[:3]}")

    # ── Layer 2: Strategy Engine ────────────────────────────────────────────
    layer_start = time.time()
    logger.info("[Layer 2] Determining program strategy...")

    strategy = build_strategy(
        profile=profile,
        openai_client=openai_client if use_llm else None,
    )

    timings["layer2"] = time.time() - layer_start
    logger.info(f"  ✓ Split: {strategy.split.name}")
    logger.info(f"  ✓ Periodization: {strategy.periodization_model}")
    logger.info(f"  ✓ {strategy.mesocycle_count} mesocycle(s), {len(strategy.week_profiles)} weeks")

    # ── Layer 3: Volume Engine ──────────────────────────────────────────────
    layer_start = time.time()
    logger.info("[Layer 3] Calculating volume allocation...")

    volume_allocation = calculate_volume(profile, strategy)

    timings["layer3"] = time.time() - layer_start
    logger.info(f"  ✓ Volume allocated for {len(volume_allocation.weeks)} weeks")

    # Validate volume allocation
    for week in volume_allocation.weeks:
        if week.below_mev:
            logger.warning(f"  ⚠ Week {week.week_number} below MEV: {week.below_mev[:3]}")
        if week.above_mrv:
            logger.warning(f"  ⚠ Week {week.week_number} above MRV: {week.above_mrv[:3]}")

    # ── Layer 4A: Program Builder (Deterministic) ───────────────────────────
    layer_start = time.time()
    logger.info("[Layer 4A] Building program (deterministic)...")

    program = build_program(profile, strategy, volume_allocation)

    timings["layer4a"] = time.time() - layer_start
    logger.info(f"  ✓ Selected exercises: {program.unique_exercises_used} unique across {program.total_workouts} workouts")
    logger.info(f"  ✓ Total sets: {program.total_sets}")

    # ── Layer 4B: LLM Week Review (Parallel) ────────────────────────────────
    if use_llm and openai_client:
        layer_start = time.time()
        logger.info(f"[Layer 4B] Running LLM coherence review for {len(program.weeks)} weeks (parallel)...")

        program = await review_and_refine_program(
            program=program,
            profile=profile,
            strategy=strategy,
            volume_allocation=volume_allocation,
            openai_client=openai_client,
        )

        timings["layer4b"] = time.time() - layer_start
        logger.info(f"  ✓ LLM review complete ({timings['layer4b']:.1f}s)")
    else:
        timings["layer4b"] = 0.0
        logger.info("[Layer 4B] Skipped (use_llm=False)")

    # ── Layer 5: Validator ──────────────────────────────────────────────────
    layer_start = time.time()
    logger.info("[Layer 5] Validating program...")

    # Stage A: Deterministic validation + auto-fix
    program, validation_issues = validate_and_fix(
        program=program,
        profile=profile,
        strategy=strategy,
        volume_allocation=volume_allocation,
    )

    validation_summary = get_validation_summary(validation_issues)
    logger.info(f"  ✓ Deterministic validation: {validation_summary['critical_count']} critical, "
                f"{validation_summary['major_count']} major, {validation_summary['warning_count']} warnings")

    # Stage B: LLM full-program review
    if use_llm and openai_client:
        logger.info("  🔍 Running LLM full-program review...")
        llm_review = await llm_full_program_review(
            program=program,
            profile=profile,
            strategy=strategy,
            openai_client=openai_client,
        )
        logger.info(f"  ✓ LLM grade: {llm_review.get('overall_grade', 'N/A')}")
        logger.info(f"  ✓ {len(llm_review.get('issues', []))} qualitative issues noted")
    else:
        llm_review = {
            "overall_grade": "B" if validation_summary["passed"] else "C",
            "strengths": ["Program generated without LLM review"],
            "issues": [],
            "coaching_summary": "LLM review skipped.",
        }
        logger.info("  ✓ LLM review skipped (use_llm=False)")

    timings["layer5"] = time.time() - layer_start

    # ── Layer 6: Serializer ─────────────────────────────────────────────────
    layer_start = time.time()
    logger.info("[Layer 6] Serializing to output format...")

    # Update program generation time
    total_time = time.time() - start_time
    program.generation_time_seconds = total_time

    output = serialize_to_v3(
        program=program,
        validation_issues=validation_issues,
        llm_review=llm_review,
    )

    # Add timing breakdown
    output["timings"] = timings
    output["timings"]["total"] = total_time

    timings["layer6"] = time.time() - layer_start

    # ── Final Summary ───────────────────────────────────────────────────────
    logger.info(f"\n✅ V5 Generation Complete!")
    logger.info(f"  Total Time: {total_time:.2f}s")
    logger.info(f"  LLM Grade: {llm_review.get('overall_grade', 'N/A')}")
    if llm_review.get("coaching_summary"):
        logger.info(f"  Coaching Notes: {llm_review['coaching_summary'][:100]}")

    return output


# ─────────────────────────────────────────────────────────────────────────────
# SYNCHRONOUS WRAPPER (FOR TESTING)
# ─────────────────────────────────────────────────────────────────────────────


def generate_program_v5_sync(input_data: dict, use_llm: bool = False) -> dict:
    """
    Synchronous version for testing (no LLM calls by default).

    Wraps the async function in asyncio.run().
    """
    return asyncio.run(generate_program_v5(
        input_data=input_data,
        openai_client=None,
        use_llm=use_llm,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST HELPER
# ─────────────────────────────────────────────────────────────────────────────


def quick_test():
    """
    Quick test of the V5 pipeline without LLM calls.

    Run with: python -m program_generator_v5.main
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    # Test input
    test_input = {
        "user_id": "test_001",
        "name": "Test Athlete",
        "training_goal": "hypertrophy",
        "training_level": "intermediate",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 60,
        "equipment_tier": 1,
    }

    print("\n" + "=" * 60)
    print("V5 PROGRAM GENERATOR — QUICK TEST")
    print("=" * 60 + "\n")

    result = generate_program_v5_sync(test_input, use_llm=False)

    print("\n" + "=" * 60)
    print("PROGRAM SUMMARY")
    print("=" * 60)
    print(f"Program Name: {result['overview']['name']}")
    print(f"Duration: {result['overview']['duration_weeks']} weeks")
    print(f"Split: {result['overview']['split_name']}")
    print(f"Periodization: {result['overview']['periodization_model']}")
    print(f"Total Workouts: {result['stats']['total_workouts']}")
    print(f"Unique Exercises: {result['stats']['unique_exercises']}")
    print(f"Generation Time: {result['stats']['generation_time_seconds']:.2f}s")
    print(f"Validation Pass Rate: {result['stats']['validation_pass_rate']}%")

    print("\n" + "-" * 60)
    print("WEEK 1 PREVIEW")
    print("-" * 60)

    for workout in result["weeks"][0]["workouts"]:
        print(f"\n{workout['day_label']} ({workout['estimated_duration_minutes']} min):")
        for ex in workout["exercises"]:
            print(f"  {ex['order']}. {ex['exercise_name']} — {ex['set_notation']}")

    print("\n" + "=" * 60)
    print("TIMING BREAKDOWN")
    print("=" * 60)
    for layer, duration in result.get("timings", {}).items():
        print(f"  {layer}: {duration:.3f}s")

    return result


if __name__ == "__main__":
    quick_test()
