"""
Example usage of the portable database module
"""

from portable_db_module import (
    SessionLocal,
    User,
    Exercise,
    UserGeneratedProgram,
    Workout,
    WorkoutExercise,
    Set,
    init_db
)
import uuid


def example_basic_queries():
    """Example of basic database queries"""
    print("\n=== Basic Queries Example ===\n")

    # Create a session
    db = SessionLocal()

    try:
        # Query all users
        users = db.query(User).all()
        print(f"Found {len(users)} users")

        # Query all exercises
        exercises = db.query(Exercise).all()
        print(f"Found {len(exercises)} exercises")

        # Filter query
        chest_exercises = db.query(Exercise).filter(
            Exercise.muscle_group == "Chest"
        ).all()
        print(f"Found {len(chest_exercises)} chest exercises")

    finally:
        db.close()


def example_create_user():
    """Example of creating a new user"""
    print("\n=== Create User Example ===\n")

    db = SessionLocal()

    try:
        # Create new user
        new_user = User(
            username="john_doe",
            name="John Doe",
            email="john@example.com",
            password_hash="hashed_password_here"  # Use proper password hashing!
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        print(f"Created user: {new_user.username} (ID: {new_user.id})")
        return new_user.id

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def example_create_exercise():
    """Example of creating exercises"""
    print("\n=== Create Exercise Example ===\n")

    db = SessionLocal()

    try:
        exercises = [
            Exercise(
                name="Bench Press",
                category="Strength",
                muscle_group="Chest",
                description="Barbell bench press"
            ),
            Exercise(
                name="Squat",
                category="Strength",
                muscle_group="Legs",
                description="Barbell back squat"
            ),
            Exercise(
                name="Deadlift",
                category="Strength",
                muscle_group="Back",
                description="Conventional deadlift"
            )
        ]

        db.add_all(exercises)
        db.commit()

        print(f"Created {len(exercises)} exercises")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


def example_create_program_with_workout(user_id):
    """Example of creating a program with workouts"""
    print("\n=== Create Program with Workout Example ===\n")

    db = SessionLocal()

    try:
        # Create a user-generated program
        program = UserGeneratedProgram(
            user_id=user_id,
            name="Beginner Strength Program",
            description="A 12-week beginner strength program",
            duration_weeks=12,
            is_public=False
        )
        db.add(program)
        db.flush()  # Get the program ID

        # Create a workout
        workout = Workout(
            user_generated_program_id=program.id,
            day_number=1,
            name="Upper Body Day",
            description="Focus on chest and back"
        )
        db.add(workout)
        db.flush()  # Get the workout ID

        # Get an exercise
        exercise = db.query(Exercise).filter(
            Exercise.name == "Bench Press"
        ).first()

        if exercise:
            # Add exercise to workout
            workout_exercise = WorkoutExercise(
                workout_id=workout.id,
                exercise_id=exercise.id,
                order_number=1,
                notes="Focus on form"
            )
            db.add(workout_exercise)
            db.flush()

            # Add sets
            sets = [
                Set(
                    workout_exercise_id=workout_exercise.id,
                    set_number=1,
                    reps=10,
                    weight=135.0,
                    rpe=7.0,
                    rest_seconds=120
                ),
                Set(
                    workout_exercise_id=workout_exercise.id,
                    set_number=2,
                    reps=8,
                    weight=145.0,
                    rpe=8.0,
                    rest_seconds=120
                )
            ]
            db.add_all(sets)

        db.commit()
        print(f"Created program: {program.name}")
        print(f"  - Workout: {workout.name}")
        print(f"  - With {len(sets)} sets")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


def example_query_with_relationships():
    """Example of querying with relationships"""
    print("\n=== Query with Relationships Example ===\n")

    db = SessionLocal()

    try:
        # Get a program with all related data
        program = db.query(UserGeneratedProgram).first()

        if program:
            print(f"Program: {program.name}")
            print(f"User: {program.user.username}")
            print(f"Workouts: {len(program.workouts)}")

            for workout in program.workouts:
                print(f"\n  Workout: {workout.name} (Day {workout.day_number})")
                for we in workout.workout_exercises:
                    print(f"    - {we.exercise.name}")
                    print(f"      Sets: {len(we.sets)}")

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Portable Database Module - Usage Examples")
    print("=" * 50)

    # Initialize database (creates tables if they don't exist)
    print("\nInitializing database...")
    init_db()

    # Run examples
    example_basic_queries()
    user_id = example_create_user()

    if user_id:
        example_create_exercise()
        example_create_program_with_workout(user_id)
        example_query_with_relationships()

    print("\n" + "=" * 50)
    print("Examples completed!")
    print("=" * 50)
