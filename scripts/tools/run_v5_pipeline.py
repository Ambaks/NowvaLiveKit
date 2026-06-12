#!/usr/bin/env python3
"""
Run V5 Full Pipeline with LLM enabled.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "program_generator"))

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
from main import generate_program_v5


async def run_pipeline():
    """Run the V5 pipeline with LLM."""

    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Test input: Tier 1, beginner, hypertrophy, 3x/week, 45 min, 4 weeks
    test_input = {
        "user_id": "test_tier1_beginner",
        "name": "Tier 1 Beginner Athlete",
        "training_goal": "hypertrophy",
        "training_level": "beginner",
        "program_duration_weeks": 4,
        "training_days_per_week": 3,
        "session_duration_minutes": 45,
        "equipment_tier": 1,
    }

    print("=" * 70)
    print("V5 FULL PIPELINE — WITH LLM")
    print("=" * 70)
    print(f"\nParameters:")
    print(f"  Tier: {test_input['equipment_tier']} (minimal)")
    print(f"  Level: {test_input['training_level']}")
    print(f"  Goal: {test_input['training_goal']}")
    print(f"  Days/Week: {test_input['training_days_per_week']}")
    print(f"  Session: {test_input['session_duration_minutes']} min")
    print(f"  Duration: {test_input['program_duration_weeks']} weeks")
    print(f"  Models: LAYER_5={os.getenv('LAYER_5_MODEL', 'not set')}, LAYER_1_2_4={os.getenv('LAYER_1_2_4_MODEL', 'not set')}")
    print("\n" + "-" * 70)

    start_time = time.time()

    result = await generate_program_v5(
        input_data=test_input,
        openai_client=openai_client,
        use_llm=True,
        input_type="structured",
    )

    total_time = time.time() - start_time

    return result, total_time


def format_program_output(result: dict) -> str:
    """Format the program output for display."""
    lines = []

    lines.append("\n" + "=" * 70)
    lines.append("PROGRAM OVERVIEW")
    lines.append("=" * 70)

    overview = result.get("overview", {})
    lines.append(f"Name: {overview.get('name', 'N/A')}")
    lines.append(f"Duration: {overview.get('duration_weeks', 'N/A')} weeks")
    lines.append(f"Split: {overview.get('split_name', 'N/A')}")
    lines.append(f"Periodization: {overview.get('periodization_model', 'N/A')}")

    stats = result.get("stats", {})
    lines.append(f"\nTotal Workouts: {stats.get('total_workouts', 'N/A')}")
    lines.append(f"Unique Exercises: {stats.get('unique_exercises', 'N/A')}")
    lines.append(f"Validation Pass Rate: {stats.get('validation_pass_rate', 'N/A')}%")

    # LLM Review
    llm_review = result.get("llm_review", {})
    lines.append(f"\nLLM Grade: {llm_review.get('overall_grade', 'N/A')}")
    if llm_review.get("coaching_summary"):
        lines.append(f"Coaching Summary: {llm_review['coaching_summary']}")

    # Timings
    lines.append("\n" + "-" * 70)
    lines.append("TIMING BREAKDOWN")
    lines.append("-" * 70)
    timings = result.get("timings", {})
    for layer, duration in sorted(timings.items()):
        lines.append(f"  {layer}: {duration:.3f}s")

    # Week-by-week breakdown
    lines.append("\n" + "=" * 70)
    lines.append("FULL PROGRAM")
    lines.append("=" * 70)

    for week in result.get("weeks", []):
        lines.append(f"\n{'─' * 70}")
        lines.append(f"WEEK {week['week_number']}")
        lines.append(f"{'─' * 70}")

        for workout in week.get("workouts", []):
            lines.append(f"\n  {workout['day_label']} ({workout.get('estimated_duration_minutes', '?')} min)")
            for ex in workout.get("exercises", []):
                lines.append(f"    {ex['order']}. {ex['exercise_name']} — {ex['set_notation']}")

    return "\n".join(lines)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print(f"\nStarting V5 pipeline at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    result, total_time = asyncio.run(run_pipeline())

    # Format and print output
    output = format_program_output(result)
    print(output)

    print("\n" + "=" * 70)
    print(f"TOTAL TIME: {total_time:.2f} seconds")
    print("=" * 70)

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"programs/v5_tier1_beginner_hypertrophy_{timestamp}.txt"

    with open(output_file, "w") as f:
        f.write(f"V5 Pipeline Results — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Generation Time: {total_time:.2f} seconds\n")
        f.write(output)
        f.write("\n\n" + "=" * 70 + "\n")
        f.write("RAW JSON OUTPUT\n")
        f.write("=" * 70 + "\n")
        f.write(json.dumps(result, indent=2, default=str))

    print(f"\nResults saved to: {output_file}")
