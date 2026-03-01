"""
Program Saver V5

Handles persistence operations for V5 program generation:
- Database save (using existing schema)
- PDF generation
- Schedule creation

Architecture:
    save_and_publish_v5_program() [orchestrator]
        ├─ save_program_to_db_v5() → Database
        ├─ create_schedule_v5() → Schedule entries
        └─ generate_and_save_pdf_v5() → PDF file
"""

from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
import os
import traceback

from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set, Schedule
from db.schedule_utils import create_schedule_for_program, get_next_monday
from .v5_adapter import convert_v5_output_to_html_format, get_user_data_from_request


def save_program_to_db_v5(
    db: Session,
    v5_output: Dict[str, Any],
    params: Dict[str, Any]
) -> int:
    """
    Save V5 program output to database.

    Args:
        db: Database session
        v5_output: Output from V5's serialize_to_v3()
        params: Original request parameters

    Returns:
        program_id (int)
    """
    overview = v5_output.get("overview", {})
    athlete = v5_output.get("athlete", {})

    # Step 1: Create Exercise cache
    exercise_cache = {}  # exercise_name -> Exercise model

    # Collect all unique exercise names from V5 structure
    all_exercise_names = set()
    for week in v5_output.get("weeks", []):
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", []):
                all_exercise_names.add(exercise.get("exercise_name", ""))

    # Query existing exercises
    if all_exercise_names:
        existing_exercises = db.query(Exercise).filter(Exercise.name.in_(all_exercise_names)).all()
        for ex in existing_exercises:
            exercise_cache[ex.name] = ex

    # Create missing exercises
    new_exercises = []
    for week in v5_output.get("weeks", []):
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", []):
                ex_name = exercise.get("exercise_name", "")
                if ex_name and ex_name not in exercise_cache:
                    # Determine muscle group from V5's muscle_contributions
                    muscle_contributions = exercise.get("muscle_contributions", {})
                    primary_muscle = ""
                    max_contribution = 0
                    for muscle, contribution in muscle_contributions.items():
                        if contribution > max_contribution:
                            max_contribution = contribution
                            primary_muscle = muscle

                    new_exercise = Exercise(
                        name=ex_name,
                        category=exercise.get("exercise_type", "compound"),
                        muscle_group=primary_muscle.replace("_", " ").title(),
                        description=f"V5 exercise: {ex_name}"
                    )
                    new_exercises.append(new_exercise)
                    exercise_cache[ex_name] = new_exercise

    # Commit exercises first if any were created
    if new_exercises:
        for ex in new_exercises:
            db.add(ex)
        db.commit()
        print(f"[PROGRAM SAVER V5] Created {len(new_exercises)} new exercises")

    # Step 2: Create UserGeneratedProgram
    user_id = params.get("user_id") or athlete.get("user_id", "unknown")
    user_program = UserGeneratedProgram(
        user_id=str(user_id),
        name=overview.get("name", "V5 Workout Program"),
        description=overview.get("description", ""),
        duration_weeks=overview.get("duration_weeks", 4),
        is_public=False
    )
    db.add(user_program)
    db.commit()
    db.refresh(user_program)
    print(f"[PROGRAM SAVER V5] Created program with ID: {user_program.id}")

    # Step 3: Create Workouts, WorkoutExercises, Sets
    for week in v5_output.get("weeks", []):
        for workout in week.get("workouts", []):
            # Create Workout
            workout_model = Workout(
                user_generated_program_id=user_program.id,
                week_number=week.get("week_number", 1),
                day_number=workout.get("day_number", 1),
                phase=week.get("phase", "Building"),
                name=workout.get("day_label", "Workout"),
                description=f"Estimated duration: {workout.get('estimated_duration_minutes', 60)} min"
            )
            db.add(workout_model)
            db.flush()  # Get workout.id

            # Create WorkoutExercises and Sets
            for exercise in workout.get("exercises", []):
                ex_name = exercise.get("exercise_name", "")
                exercise_model = exercise_cache.get(ex_name)

                if not exercise_model:
                    print(f"[PROGRAM SAVER V5] ⚠️  Exercise '{ex_name}' not in cache, skipping")
                    continue

                workout_exercise = WorkoutExercise(
                    workout_id=workout_model.id,
                    exercise_id=exercise_model.id,
                    order_number=exercise.get("order", 1),
                    notes=exercise.get("rationale", "")
                )
                db.add(workout_exercise)
                db.flush()  # Get workout_exercise.id

                # Create Sets
                for set_data in exercise.get("sets", []):
                    set_model = Set(
                        workout_exercise_id=workout_exercise.id,
                        set_number=set_data.get("set_number", 1),
                        reps=set_data.get("reps", 10),
                        intensity_percent=set_data.get("intensity_percent"),
                        rest_seconds=set_data.get("rest_seconds", 90),
                        velocity_threshold=None,
                        velocity_min=None,
                        velocity_max=None
                    )
                    db.add(set_model)

    # Final commit
    db.commit()
    print(f"[PROGRAM SAVER V5] ✅ Program saved to database! ID: {user_program.id}")
    return user_program.id


def generate_and_save_pdf_v5(
    v5_output: Dict[str, Any],
    program_id: int,
    user_id: str,
    user_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate PDF for V5 program.

    Args:
        v5_output: V5 serialized output
        program_id: Database program ID
        user_id: User UUID as string
        user_data: Optional user data for cover page

    Returns:
        pdf_path (str)

    Raises:
        Exception if PDF generation fails
    """
    from .html_generator import generate_html
    from .pdf_generator import generate_pdf_from_html

    # Convert V5 output to HTML generator format
    program_data, html_user_data = convert_v5_output_to_html_format(v5_output, user_data)
    program_data['id'] = program_id  # Add DB ID

    # Generate HTML
    html_content = generate_html(program_data, html_user_data)
    print(f"[PROGRAM SAVER V5] ✅ HTML generated ({len(html_content)} chars)")

    # Generate PDF
    pdf_filename = f"program_{user_id}_{program_id}.pdf"
    pdf_path = os.path.join("programs", pdf_filename)

    # Ensure programs directory exists
    os.makedirs("programs", exist_ok=True)

    # Set base_url for assets
    templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates"))
    base_url = f"file://{templates_dir}/"

    generate_pdf_from_html(html_content, pdf_path, base_url=base_url)
    print(f"[PROGRAM SAVER V5] ✅ PDF generated: {pdf_path}")

    return pdf_path


def create_schedule_v5(
    db: Session,
    user_id: str,
    program_id: int,
    days_per_week: int
) -> List[Schedule]:
    """
    Create workout schedule for V5 program.

    Args:
        db: Database session
        user_id: User UUID as string
        program_id: Program ID
        days_per_week: Number of training days per week

    Returns:
        List of Schedule entries
    """
    start_date = get_next_monday()

    schedule_entries = create_schedule_for_program(
        db=db,
        user_id=user_id,
        program_id=program_id,
        program_type="user_generated",
        start_date=start_date,
        days_per_week=days_per_week
    )

    return schedule_entries


def save_and_publish_v5_program(
    db: Session,
    v5_output: Dict[str, Any],
    params: Dict[str, Any],
    job_id: str,
    user_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Orchestrate saving V5 program to database, creating PDF, and scheduling.

    This is the main entry point called from celery_tasks.py.

    Args:
        db: Database session
        v5_output: V5 serialized output from serialize_to_v3()
        params: Original request parameters
        job_id: Celery job ID for progress tracking
        user_data: Optional user data for PDF cover page

    Returns:
        {
            'program_id': int,
            'pdf_path': Optional[str],
            'schedule_count': int
        }

    Raises:
        Exception if database save fails (fatal)
    """
    from .job_manager import update_job_status

    # Step 1: Save to database (85% progress)
    update_job_status(db, job_id, "in_progress", progress=85)
    print(f"\n[JOB {job_id}] 💾 Saving V5 program to database...")

    try:
        program_id = save_program_to_db_v5(db, v5_output, params)
        print(f"[JOB {job_id}] ✅ Program saved! ID: {program_id}")
    except Exception as e:
        print(f"[JOB {job_id}] ❌ Database save failed: {e}")
        traceback.print_exc()
        raise  # Fatal error

    # Step 2: Create schedule (90% progress)
    update_job_status(db, job_id, "in_progress", progress=90)
    print(f"\n[JOB {job_id}] 📅 Creating workout schedule...")

    schedule_entries = []
    try:
        user_id = params.get("user_id", "unknown")
        days_per_week = params.get("days_per_week", 4)
        schedule_entries = create_schedule_v5(db, str(user_id), program_id, days_per_week)
        print(f"[JOB {job_id}] ✅ Created {len(schedule_entries)} schedule entries")
    except Exception as e:
        print(f"[JOB {job_id}] ⚠️  Schedule creation failed (non-fatal): {e}")
        traceback.print_exc()

    # Step 3: Generate PDF (95% progress)
    update_job_status(db, job_id, "in_progress", progress=95)
    print(f"\n[JOB {job_id}] 📄 Generating PDF...")

    pdf_path = None
    try:
        user_id = params.get("user_id", "unknown")
        pdf_path = generate_and_save_pdf_v5(
            v5_output, program_id, str(user_id), user_data
        )
        print(f"[JOB {job_id}] ✅ PDF generated: {pdf_path}")
    except Exception as e:
        print(f"[JOB {job_id}] ⚠️  PDF generation failed (non-fatal): {e}")
        traceback.print_exc()

    return {
        'program_id': program_id,
        'pdf_path': pdf_path,
        'schedule_count': len(schedule_entries)
    }
