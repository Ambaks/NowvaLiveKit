"""
Generate HTML program files for all 5 V6 verification scenarios.

These are the same styled documents that would be converted to PDF via WeasyPrint.
Open them in a browser to preview the rendered program output.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
logging.basicConfig(level=logging.WARNING, format="%(message)s")

from src.program_generator.main import generate_program_v5_sync
from src.api.services.v5_adapter import convert_v5_output_to_html_format, get_user_data_from_request
from src.api.services.html_generator import generate_html

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


SCENARIOS = [
    {
        "filename": "01_youth_soccer_in_season",
        "label": "14-year-old beginner soccer player (in-season)",
        "input": {
            "user_id": "test_youth",
            "name": "Marcus Rivera",
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
        },
    },
    {
        "filename": "02_advanced_powerlifter",
        "label": "22-year-old advanced male powerlifter (off-season)",
        "input": {
            "user_id": "test_pl",
            "name": "Jake Thompson",
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
        },
    },
    {
        "filename": "03_female_basketball_in_season",
        "label": "35-year-old intermediate female basketball player (in-season)",
        "input": {
            "user_id": "test_fbb",
            "name": "Aisha Johnson",
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
        },
    },
    {
        "filename": "04_senior_beginner",
        "label": "65-year-old beginner (general fitness)",
        "input": {
            "user_id": "test_senior",
            "name": "Robert Chen",
            "age": 65,
            "sex": "M",
            "body_weight_kg": 80.0,
            "training_goal": "hypertrophy",
            "training_level": "beginner",
            "program_duration_weeks": 4,
            "training_days_per_week": 3,
            "session_duration_minutes": 45,
            "equipment_tier": 2,
        },
    },
    {
        "filename": "05_advanced_hypertrophy",
        "label": "19-year-old advanced male (hypertrophy)",
        "input": {
            "user_id": "test_hyp",
            "name": "Tyler Brooks",
            "age": 19,
            "sex": "M",
            "body_weight_kg": 82.0,
            "training_goal": "hypertrophy",
            "training_level": "advanced",
            "program_duration_weeks": 8,
            "training_days_per_week": 5,
            "session_duration_minutes": 75,
            "equipment_tier": 2,
        },
    },
]


def main():
    print(f"\nGenerating HTML program files in: {OUTPUT_DIR}\n")

    for scenario in SCENARIOS:
        label = scenario["label"]
        filename = scenario["filename"]
        inp = scenario["input"]

        print(f"  Generating: {label}...")

        # 1. Run the program generator
        v5_output = generate_program_v5_sync(inp, use_llm=False)

        # 2. Convert to HTML format
        program_data, user_data = convert_v5_output_to_html_format(v5_output)

        # Supplement user_data with input fields
        user_data.update({
            "name": inp.get("name", "Athlete"),
            "age": inp.get("age"),
            "weight_kg": inp.get("body_weight_kg"),
            "training_level": inp.get("training_level", "intermediate"),
        })

        # 3. Render HTML
        html_content = generate_html(program_data, user_data)

        # 4. Save
        html_path = os.path.join(OUTPUT_DIR, f"{filename}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Stats
        overview = v5_output.get("overview", {})
        stats = v5_output.get("stats", {})
        print(f"    Split: {overview.get('split_name', 'N/A')}")
        print(f"    Periodization: {overview.get('periodization_model', 'N/A')}")
        print(f"    Workouts: {stats.get('total_workouts', 'N/A')}, "
              f"Sets: {stats.get('total_sets', 'N/A')}, "
              f"Exercises: {stats.get('unique_exercises', 'N/A')}")
        print(f"    Saved: {html_path}")
        print()

    print(f"Done! Open any .html file in {OUTPUT_DIR} to preview.\n")


if __name__ == "__main__":
    main()
