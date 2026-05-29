"""
Test V5 Program Generation — Basketball Player (Jump Higher)
Advanced level, Dumbbells (Tier 2), VBT enabled, with email delivery.
"""

import asyncio
import os
import sys
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from program_generator_v5 import generate_program_v5
from api.services.v5_adapter import convert_v5_output_to_html_format
from api.services.html_generator import generate_html
from api.services.pdf_generator import generate_pdf_from_html
from services.email_service import send_program_email

logging.basicConfig(level=logging.INFO, format="%(message)s")


async def main():
    # ── 1. Define test input ────────────────────────────────────────────────
    test_input = {
        "user_id": "test_basketball_001",
        "name": "Test Athlete",
        "age": 22,
        "sex": "M",
        "body_weight_kg": 85.0,
        "training_goal": "power",
        "training_level": "advanced",
        "program_duration_weeks": 4,
        "training_days_per_week": 4,
        "session_duration_minutes": 60,
        "equipment_tier": 2,              # Dumbbells
        "sport": "basketball",
        "vbt_capability": True,
        "injuries": [],
        "exercises_to_avoid": [],
        "exercises_to_include": [],
        "recovery_capacity": "normal",
        "weak_points": [],
    }

    print("\n" + "=" * 60)
    print("V5 TEST — Basketball / Jump Higher / Advanced / T2 / VBT")
    print("=" * 60 + "\n")

    # ── 2. Generate program ─────────────────────────────────────────────────
    result = await generate_program_v5(
        input_data=test_input,
        openai_client=None,
        use_llm=False,
        input_type="structured",
    )

    print("\n" + "=" * 60)
    print("PROGRAM SUMMARY")
    print("=" * 60)
    overview = result['overview']
    stats = result['stats']
    print(f"Program Name: {str(overview['name'])}")
    print(f"Duration: {int(overview['duration_weeks'])} weeks")
    print(f"Split: {str(overview['split_name'])}")
    print(f"Periodization: {str(overview['periodization_model'])}")
    print(f"VBT Enabled: {bool(overview.get('vbt_enabled', False))}")
    print(f"Total Workouts: {int(stats['total_workouts'])}")
    print(f"Unique Exercises: {int(stats['unique_exercises'])}")
    print(f"Total Sets: {int(stats['total_sets'])}")
    print(f"Generation Time: {float(stats['generation_time_seconds']):.2f}s")
    print(f"Validation Pass Rate: {float(stats['validation_pass_rate'])}%")

    # Week 1 preview
    print("\n" + "-" * 60)
    print("WEEK 1 PREVIEW")
    print("-" * 60)
    for workout in result["weeks"][0]["workouts"]:
        print(f"\n{str(workout['day_label'])} ({int(workout['estimated_duration_minutes'])} min):")
        for ex in workout["exercises"]:
            vbt_tag = ""
            if ex.get("sets") and ex["sets"][0].get("velocity_target"):
                vbt_tag = f" [VBT: {float(ex['sets'][0]['velocity_target'])} m/s]"
            print(f"  {int(ex['order'])}. {str(ex['exercise_name'])} — {str(ex['set_notation'])}{vbt_tag}")

    # Timing breakdown
    print("\n" + "=" * 60)
    print("TIMING BREAKDOWN")
    print("=" * 60)
    for layer, duration in result.get("timings", {}).items():
        print(f"  {str(layer)}: {float(duration):.3f}s")

    # ── 3. Generate PDF ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("GENERATING PDF...")
    print("=" * 60)

    user_data = {
        "name": "Test Athlete",
        "email": "ambakalgr@gmail.com",
        "age": 22,
        "weight_kg": 85.0,
        "height_cm": 185.0,
        "sex": "M",
        "fitness_level": "advanced",
        "goal": "power",
    }

    program_data, html_user_data = convert_v5_output_to_html_format(result, user_data)
    program_data["id"] = 99999  # Dummy ID for test

    html_content = generate_html(program_data, html_user_data)
    print(f"  HTML generated ({len(html_content)} chars)")

    os.makedirs("programs", exist_ok=True)
    pdf_path = os.path.join("programs", "test_basketball_v5.pdf")

    templates_dir = os.path.abspath(os.path.join("src", "templates"))
    base_url = f"file://{templates_dir}/"

    generate_pdf_from_html(html_content, pdf_path, base_url=base_url)
    pdf_size = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"  PDF generated: {pdf_path} ({pdf_size:.2f} MB)")

    # ── 4. Send email ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SENDING EMAIL...")
    print("=" * 60)

    email_result = send_program_email(
        to_email="ambakalgr@gmail.com",
        user_name="Test Athlete",
        program_id=99999,
        pdf_path=pdf_path,
    )

    if email_result:
        print(f"  Email sent successfully! Response: {email_result}")
    else:
        print("  Email sending failed. Check RESEND_API_KEY and logs.")

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

    return result


if __name__ == "__main__":
    asyncio.run(main())
