"""
Test script for TOON-formatted summary generation
"""
import sys
sys.path.insert(0, 'src')

from api.schemas.program_schemas import WeekSchema, WorkoutSchema, ExerciseSchema, SetSchema
from api.services.program_generator_v2 import _generate_weeks_summary

# Create mock data for 4 weeks of training
def create_mock_weeks():
    weeks = []

    # Week 1 - Build phase
    week1_workouts = [
        WorkoutSchema(
            day_number=1,
            name="Lower Power",
            description="Lower body strength focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Back Squat",
                    category="Strength",
                    muscle_group="Quads",
                    order=1,
                    sets=[
                        SetSchema(set_number=1, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=2, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=3, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=4, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                    ]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Romanian Deadlift",
                    category="Strength",
                    muscle_group="Hamstrings",
                    order=2,
                    sets=[
                        SetSchema(set_number=1, reps=8, intensity_percent=70.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=2, reps=8, intensity_percent=70.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=3, reps=8, intensity_percent=70.0, rir=2, rest_seconds=180),
                    ]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Hip Thrust",
                    category="Hypertrophy",
                    muscle_group="Glutes",
                    order=3,
                    sets=[
                        SetSchema(set_number=1, reps=10, intensity_percent=70.0, rir=2, rest_seconds=120),
                        SetSchema(set_number=2, reps=10, intensity_percent=70.0, rir=2, rest_seconds=120),
                    ]
                ),
            ]
        ),
        WorkoutSchema(
            day_number=2,
            name="Upper Push",
            description="Upper body push focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Bench Press",
                    category="Strength",
                    muscle_group="Chest",
                    order=1,
                    sets=[
                        SetSchema(set_number=1, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=2, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=3, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                        SetSchema(set_number=4, reps=5, intensity_percent=80.0, rir=2, rest_seconds=240),
                    ]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Overhead Press",
                    category="Strength",
                    muscle_group="Shoulders",
                    order=2,
                    sets=[
                        SetSchema(set_number=1, reps=6, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=2, reps=6, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=3, reps=6, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=4, reps=6, intensity_percent=75.0, rir=2, rest_seconds=180),
                    ]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Tricep Extension",
                    category="Hypertrophy",
                    muscle_group="Triceps",
                    order=3,
                    sets=[
                        SetSchema(set_number=1, reps=12, intensity_percent=60.0, rir=2, rest_seconds=90),
                        SetSchema(set_number=2, reps=12, intensity_percent=60.0, rir=2, rest_seconds=90),
                    ]
                ),
            ]
        ),
        WorkoutSchema(
            day_number=3,
            name="Upper Pull",
            description="Upper body pull focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Row",
                    category="Strength",
                    muscle_group="Back",
                    order=1,
                    sets=[
                        SetSchema(set_number=1, reps=8, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=2, reps=8, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=3, reps=8, intensity_percent=75.0, rir=2, rest_seconds=180),
                        SetSchema(set_number=4, reps=8, intensity_percent=75.0, rir=2, rest_seconds=180),
                    ]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Curl",
                    category="Hypertrophy",
                    muscle_group="Biceps",
                    order=2,
                    sets=[
                        SetSchema(set_number=1, reps=12, intensity_percent=60.0, rir=2, rest_seconds=90),
                        SetSchema(set_number=2, reps=12, intensity_percent=60.0, rir=2, rest_seconds=90),
                    ]
                ),
            ]
        ),
    ]

    week1 = WeekSchema(
        week_number=1,
        phase="Build",
        workouts=week1_workouts,
        notes="First week of training cycle"
    )
    weeks.append(week1)

    # Week 2 - Build phase (increased volume)
    week2_workouts = [
        WorkoutSchema(
            day_number=1,
            name="Lower Power",
            description="Lower body strength focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Back Squat",
                    category="Strength",
                    muscle_group="Quads",
                    order=1,
                    sets=[SetSchema(set_number=i, reps=5, intensity_percent=82.0, rir=2, rest_seconds=240) for i in range(1, 6)]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Romanian Deadlift",
                    category="Strength",
                    muscle_group="Hamstrings",
                    order=2,
                    sets=[SetSchema(set_number=i, reps=8, intensity_percent=72.0, rir=2, rest_seconds=180) for i in range(1, 5)]
                ),
            ]
        ),
        WorkoutSchema(
            day_number=2,
            name="Upper Push",
            description="Upper body push focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Bench Press",
                    category="Strength",
                    muscle_group="Chest",
                    order=1,
                    sets=[SetSchema(set_number=i, reps=5, intensity_percent=82.0, rir=2, rest_seconds=240) for i in range(1, 6)]
                ),
                ExerciseSchema(
                    exercise_name="Barbell Incline Bench Press",
                    category="Hypertrophy",
                    muscle_group="Chest",
                    order=2,
                    sets=[SetSchema(set_number=i, reps=8, intensity_percent=70.0, rir=2, rest_seconds=180) for i in range(1, 4)]
                ),
            ]
        ),
        WorkoutSchema(
            day_number=3,
            name="Upper Pull",
            description="Upper body pull focus",
            exercises=[
                ExerciseSchema(
                    exercise_name="Barbell Row",
                    category="Strength",
                    muscle_group="Back",
                    order=1,
                    sets=[SetSchema(set_number=i, reps=8, intensity_percent=77.0, rir=2, rest_seconds=180) for i in range(1, 5)]
                ),
            ]
        ),
    ]

    week2 = WeekSchema(week_number=2, phase="Build", workouts=week2_workouts)
    weeks.append(week2)

    return weeks


def test_summary_generation():
    """Test the TOON summary generation"""
    print("=" * 80)
    print("TESTING TOON SUMMARY GENERATION")
    print("=" * 80)
    print()

    # Create mock data
    weeks = create_mock_weeks()
    params = {"days_per_week": 3}

    # Generate summary
    summary = _generate_weeks_summary(weeks, params)

    # Print results
    print(summary)
    print("=" * 80)
    print(f"Summary length: {len(summary)} chars")
    print(f"Estimated tokens: ~{len(summary) // 4}")
    print("=" * 80)

    # Compare to JSON size
    import json
    json_data = [week.dict() for week in weeks]
    json_str = json.dumps(json_data, indent=2)
    json_tokens = len(json_str) // 4

    print(f"\nComparison:")
    print(f"  JSON format: {len(json_str)} chars (~{json_tokens} tokens)")
    print(f"  TOON format: {len(summary)} chars (~{len(summary) // 4} tokens)")
    print(f"  Token savings: {((json_tokens - len(summary) // 4) / json_tokens * 100):.1f}%")
    print()


if __name__ == "__main__":
    test_summary_generation()
