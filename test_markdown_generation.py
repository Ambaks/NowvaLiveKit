#!/usr/bin/env python3
"""
Test script to verify markdown generation with VBT support
"""
import sys
sys.path.insert(0, 'src')

from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set, User
from api.services.markdown_generator import generate_program_markdown
from datetime import datetime
import uuid

def create_test_program():
    """Create a minimal test program with VBT data"""
    db = SessionLocal()

    try:
        # Get or create test user
        test_user_id = "ee611076-e172-45c9-8562-c30aeebd037f"
        user = db.query(User).filter(User.id == test_user_id).first()

        if not user:
            print("❌ Test user not found. Please create user first.")
            return None

        print(f"✅ Found user: {user.name}")

        # Create test program
        program = UserGeneratedProgram(
            user_id=test_user_id,
            name="Test VBT Program - Markdown Generation",
            description="A minimal test program to verify VBT markdown generation",
            duration_weeks=1,
            is_public=False,
            created_at=datetime.utcnow()
        )
        db.add(program)
        db.flush()

        print(f"✅ Created test program: {program.name} (ID: {program.id})")

        # Get or create test exercises
        exercises = {
            "Clean Pull": Exercise(
                name="Clean Pull",
                category="Power",
                muscle_group="Full Body",
                description="Olympic lifting movement"
            ),
            "Back Squat": Exercise(
                name="Back Squat",
                category="Strength",
                muscle_group="Legs",
                description="Compound lower body exercise"
            )
        }

        for ex_name, ex_obj in exercises.items():
            existing = db.query(Exercise).filter(Exercise.name == ex_name).first()
            if existing:
                exercises[ex_name] = existing
            else:
                db.add(ex_obj)
                db.flush()

        # Create test workout
        workout = Workout(
            user_generated_program_id=program.id,
            week_number=1,
            day_number=1,
            phase="Build",
            name="Power Day",
            description="Olympic lifting with VBT tracking"
        )
        db.add(workout)
        db.flush()

        print(f"✅ Created test workout: {workout.name}")

        # Add Clean Pull with VBT
        clean_pull_we = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercises["Clean Pull"].id,
            order_number=1,
            notes="Focus on explosive movement"
        )
        db.add(clean_pull_we)
        db.flush()

        # Add sets with VBT data
        for i in range(1, 4):
            set_obj = Set(
                workout_exercise_id=clean_pull_we.id,
                set_number=i,
                reps=3,
                intensity_percent=85.0,
                rpe=2.0,
                rest_seconds=180,
                velocity_threshold=1.0,
                velocity_min=0.95,
                velocity_max=1.2
            )
            db.add(set_obj)

        # Add Back Squat without VBT
        squat_we = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercises["Back Squat"].id,
            order_number=2,
            notes="Focus on depth and control"
        )
        db.add(squat_we)
        db.flush()

        # Add sets without VBT
        for i in range(1, 5):
            set_obj = Set(
                workout_exercise_id=squat_we.id,
                set_number=i,
                reps=5,
                intensity_percent=80.0,
                rpe=2.0,
                rest_seconds=180
            )
            db.add(set_obj)

        db.commit()
        print(f"✅ Added exercises with sets (VBT + non-VBT)")

        return program.id, user.name

    except Exception as e:
        print(f"❌ Error creating test program: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return None
    finally:
        db.close()


def test_markdown_generation(program_id, user_name):
    """Test the markdown generation"""
    db = SessionLocal()

    try:
        print(f"\n{'='*60}")
        print("Testing Markdown Generation")
        print(f"{'='*60}\n")

        # Fetch program
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            print(f"❌ Program {program_id} not found")
            return False

        # Fetch workouts with all relationships
        from sqlalchemy.orm import joinedload
        workouts = db.query(Workout).filter(
            Workout.user_generated_program_id == program_id
        ).options(
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
            joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
        ).all()

        print(f"📄 Generating markdown for program {program_id}...")

        # Generate markdown
        output_path = generate_program_markdown(
            program=program,
            workouts=workouts,
            output_dir="programs",
            user_name=user_name,
            vbt_enabled=True,
            vbt_setup_notes="Use Vitruve or similar VBT device. Attach to barbell.",
            deload_schedule="Week 4 is deload (40% volume reduction)",
            injury_accommodations="None specified"
        )

        print(f"✅ Markdown generated: {output_path}")

        # Display preview
        print(f"\n{'='*60}")
        print("Markdown Preview (first 40 lines)")
        print(f"{'='*60}\n")

        with open(output_path, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines[:40], 1):
                print(f"{i:3d} | {line}", end='')

        if len(lines) > 40:
            print(f"\n... ({len(lines) - 40} more lines)")

        print(f"\n{'='*60}")
        print(f"✅ Test Complete! Check: {output_path}")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"❌ Error testing markdown generation: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("🧪 Markdown Generation Test\n")

    # Create test program
    result = create_test_program()
    if not result:
        sys.exit(1)

    program_id, user_name = result

    # Test markdown generation
    success = test_markdown_generation(program_id, user_name)

    if success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Tests failed")
        sys.exit(1)
