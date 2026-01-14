#!/usr/bin/env python3
"""
Test script to verify PDF generation with color themes.
"""
import sys
import os
sys.path.insert(0, 'src')

from api.services.html_generator import generate_html
from api.services.pdf_generator import generate_pdf_from_html, get_pdf_size_mb
from datetime import datetime

# Sample program data for testing (Power theme)
sample_program = {
    "id": 999,
    "program_name": "Power Development Program",
    "description": "8-week program focused on explosive power and athletic performance",
    "goal": "power development and vertical jump improvement",
    "duration_weeks": 8,
    "vbt_enabled": True,
    "progression_strategy": "Progressive overload with velocity-based training zones",
    "overall_notes": "Focus on explosive movements and adequate rest between sets",
    "weeks": [
        {
            "week_number": 1,
            "phase": "Foundation",
            "notes": "Establish baseline power output and technique",
            "workouts": [
                {
                    "day_number": 1,
                    "name": "Lower Power",
                    "description": "Explosive lower body movements",
                    "exercises": [
                        {
                            "order": 1,
                            "exercise_name": "Box Jump",
                            "category": "Power",
                            "muscle_group": "Legs",
                            "sets": [
                                {"set_number": 1, "reps": 5, "intensity_percent": None, "rir": 3, "velocity_threshold": 1.2, "rest_seconds": 180},
                                {"set_number": 2, "reps": 5, "intensity_percent": None, "rir": 3, "velocity_threshold": 1.2, "rest_seconds": 180},
                                {"set_number": 3, "reps": 5, "intensity_percent": None, "rir": 3, "velocity_threshold": 1.2, "rest_seconds": 180},
                            ],
                            "notes": "Focus on maximum explosion from the bottom position"
                        },
                        {
                            "order": 2,
                            "exercise_name": "Barbell Back Squat",
                            "category": "Strength",
                            "muscle_group": "Quads/Glutes",
                            "sets": [
                                {"set_number": 1, "reps": 3, "intensity_percent": 85, "rir": 2, "velocity_threshold": 0.7, "rest_seconds": 240},
                                {"set_number": 2, "reps": 3, "intensity_percent": 87.5, "rir": 2, "velocity_threshold": 0.7, "rest_seconds": 240},
                                {"set_number": 3, "reps": 3, "intensity_percent": 90, "rir": 1, "velocity_threshold": 0.7, "rest_seconds": 240},
                            ],
                            "notes": None
                        },
                        {
                            "order": 3,
                            "exercise_name": "Romanian Deadlift",
                            "category": "Hypertrophy",
                            "muscle_group": "Hamstrings",
                            "sets": [
                                {"set_number": 1, "reps": 8, "intensity_percent": 70, "rir": 2, "velocity_threshold": None, "rest_seconds": 120},
                                {"set_number": 2, "reps": 8, "intensity_percent": 70, "rir": 2, "velocity_threshold": None, "rest_seconds": 120},
                                {"set_number": 3, "reps": 8, "intensity_percent": 70, "rir": 2, "velocity_threshold": None, "rest_seconds": 120},
                            ],
                            "notes": None
                        }
                    ]
                }
            ]
        }
    ]
}

# Sample user data
sample_user = {
    "name": "Test Athlete",
    "email": "athlete@example.com",
    "age": 25
}

def test_pdf_generation():
    """Test PDF generation with sample data."""
    print("=" * 60)
    print("Testing PDF Generation with Color Themes")
    print("=" * 60)
    print()

    # Generate HTML
    print("📝 Generating HTML from program data...")
    html_content = generate_html(sample_program, sample_user)
    print(f"✅ HTML generated ({len(html_content):,} characters)")
    print()

    # Generate PDF
    pdf_path = "programs/test_power_program.pdf"
    os.makedirs("programs", exist_ok=True)

    print(f"📄 Generating PDF: {pdf_path}")
    generate_pdf_from_html(html_content, pdf_path)

    # Check file size
    file_size_mb = get_pdf_size_mb(pdf_path)
    print(f"✅ PDF generated successfully!")
    print(f"   File: {pdf_path}")
    print(f"   Size: {file_size_mb} MB")
    print()

    print("=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print()
    print("The PDF showcases:")
    print("  ✓ Power color theme (Red/Orange gradient)")
    print("  ✓ Professional cover page with gradient")
    print("  ✓ Color-coded exercise tables")
    print("  ✓ Category badges (Power/Strength/Hypertrophy)")
    print("  ✓ Intensity heat-map indicators")
    print("  ✓ VBT velocity thresholds")
    print("  ✓ Program statistics")
    print()
    print(f"Open the PDF: open {pdf_path}")
    print()

if __name__ == "__main__":
    test_pdf_generation()
