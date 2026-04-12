from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from db.models import (
    Exercise,
    ProgramArtifactV7Record,
    Set,
    UserGeneratedProgram,
    Workout,
    WorkoutExercise,
)

from .job_manager import update_job_status
from .program_saver_v5 import create_schedule_v5, generate_and_save_pdf_v5


def save_program_to_db_v7(
    db: Session,
    v7_output: Dict[str, Any],
    params: Dict[str, Any],
    job_id: Optional[str] = None,
) -> int:
    overview = v7_output.get("overview", {})
    athlete = v7_output.get("athlete", {})
    artifact_payload = v7_output.get("_artifact_internal", {})

    exercise_cache: dict[str, Exercise] = {}
    canonical_ids = set()
    exercise_names = set()
    for week in v7_output.get("weeks", []):
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", []):
                canonical_id = exercise.get("exercise_id")
                exercise_name = exercise.get("exercise_name")
                if canonical_id:
                    canonical_ids.add(canonical_id)
                if exercise_name:
                    exercise_names.add(exercise_name)

    if canonical_ids:
        existing_by_canonical = db.query(Exercise).filter(Exercise.canonical_id.in_(canonical_ids)).all()
        for exercise in existing_by_canonical:
            if exercise.canonical_id:
                exercise_cache[exercise.canonical_id] = exercise

    if exercise_names:
        existing_by_name = db.query(Exercise).filter(Exercise.name.in_(exercise_names)).all()
        for exercise in existing_by_name:
            key = exercise.canonical_id or exercise.name
            exercise_cache[key] = exercise

    new_exercises = []
    for week in v7_output.get("weeks", []):
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", []):
                canonical_id = exercise.get("exercise_id")
                exercise_name = exercise.get("exercise_name", "")
                lookup_key = canonical_id or exercise_name
                if not lookup_key or lookup_key in exercise_cache:
                    continue

                muscle_contributions = exercise.get("muscle_contributions", {})
                primary_muscle = max(muscle_contributions, key=muscle_contributions.get, default="general")
                new_exercise = Exercise(
                    name=exercise_name,
                    canonical_id=canonical_id,
                    category=exercise.get("exercise_type", "compound"),
                    muscle_group=primary_muscle.replace("_", " ").title(),
                    description=f"V7 exercise: {exercise_name}",
                )
                db.add(new_exercise)
                new_exercises.append(new_exercise)
                exercise_cache[lookup_key] = new_exercise

    if new_exercises:
        db.flush()

    user_program = UserGeneratedProgram(
        user_id=str(params.get("user_id") or athlete.get("user_id", "unknown")),
        name=overview.get("name", "V7 Workout Program"),
        description=overview.get("description", ""),
        duration_weeks=overview.get("duration_weeks", 4),
        is_public=False,
        generator_version="v7",
        artifact_ref={
            "kg_version": overview.get("kg_version"),
            "prompt_version": artifact_payload.get("prompt_version"),
        },
    )
    db.add(user_program)
    db.flush()

    workout_map = []
    for week in v7_output.get("weeks", []):
        for workout in week.get("workouts", []):
            workout_model = Workout(
                user_generated_program_id=user_program.id,
                week_number=week.get("week_number", 1),
                day_number=workout.get("day_number", 1),
                phase=week.get("phase", "Building"),
                name=workout.get("day_label", "Workout"),
                description=f"Estimated duration: {workout.get('estimated_duration_minutes', 60)} min",
            )
            db.add(workout_model)
            workout_map.append((workout_model, workout))
    db.flush()

    workout_exercise_map = []
    for workout_model, workout in workout_map:
        for exercise in workout.get("exercises", []):
            canonical_id = exercise.get("exercise_id")
            exercise_name = exercise.get("exercise_name", "")
            exercise_model = exercise_cache.get(canonical_id) or exercise_cache.get(exercise_name)
            if exercise_model is None:
                continue
            workout_exercise = WorkoutExercise(
                workout_id=workout_model.id,
                exercise_id=exercise_model.id,
                canonical_exercise_id=canonical_id,
                order_number=exercise.get("order", 1),
                notes=exercise.get("rationale", ""),
            )
            db.add(workout_exercise)
            workout_exercise_map.append((workout_exercise, exercise))
    db.flush()

    for workout_exercise, exercise in workout_exercise_map:
        for set_data in exercise.get("sets", []):
            db.add(Set(
                workout_exercise_id=workout_exercise.id,
                set_number=set_data.get("set_number", 1),
                reps=set_data.get("reps", 10),
                intensity_percent=set_data.get("intensity_percent"),
                rpe=set_data.get("rpe"),
                rest_seconds=set_data.get("rest_seconds", 90),
                set_type=set_data.get("set_type", "standard"),
                velocity_threshold=set_data.get("velocity_target"),
                velocity_min=set_data.get("velocity_min"),
                velocity_max=set_data.get("velocity_max"),
            ))

    db.flush()

    artifact_record = ProgramArtifactV7Record(
        user_generated_program_id=user_program.id,
        job_id=job_id,
        directive_json=artifact_payload.get("directive", {}),
        block_plan_json=artifact_payload.get("block_plan", {}),
        assembly_trace_json=artifact_payload.get("assembly_trace", []),
        validation_json={
            "issues": artifact_payload.get("validation", []),
            "repair_log": artifact_payload.get("repair_log", []),
        },
        critic_json=artifact_payload.get("critic"),
        metrics_json=artifact_payload.get("metrics", {}),
        kg_version=artifact_payload.get("kg_version", overview.get("kg_version", "unknown")),
        prompt_version=artifact_payload.get("prompt_version", "v7_prompt_1"),
    )
    db.add(artifact_record)
    db.flush()

    user_program.artifact_ref = {
        "artifact_id": artifact_record.id,
        "kg_version": artifact_record.kg_version,
        "prompt_version": artifact_record.prompt_version,
    }
    db.commit()
    db.refresh(user_program)
    return user_program.id


def save_and_publish_v7_program(
    db: Session,
    v7_output: Dict[str, Any],
    params: Dict[str, Any],
    job_id: str,
    user_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    update_job_status(db, job_id, "in_progress", progress=85)
    print(f"\n[JOB {job_id}] 💾 Saving V7 program to database...")

    try:
        program_id = save_program_to_db_v7(db, v7_output, params, job_id=job_id)
        print(f"[JOB {job_id}] ✅ Program saved! ID: {program_id}")
    except Exception as exc:
        print(f"[JOB {job_id}] ❌ Database save failed: {exc}")
        traceback.print_exc()
        raise

    update_job_status(db, job_id, "in_progress", progress=90)
    print(f"\n[JOB {job_id}] 📅 Creating workout schedule...")
    schedule_entries = []
    try:
        schedule_entries = create_schedule_v5(
            db=db,
            user_id=str(params.get("user_id", "unknown")),
            program_id=program_id,
            days_per_week=params.get("days_per_week", 4),
        )
        print(f"[JOB {job_id}] ✅ Created {len(schedule_entries)} schedule entries")
    except Exception as exc:
        print(f"[JOB {job_id}] ⚠️  Schedule creation failed (non-fatal): {exc}")
        traceback.print_exc()

    update_job_status(db, job_id, "in_progress", progress=95)
    print(f"\n[JOB {job_id}] 📄 Generating PDF...")
    pdf_path = None
    try:
        pdf_path = generate_and_save_pdf_v5(
            v5_output=v7_output,
            program_id=program_id,
            user_id=str(params.get("user_id", "unknown")),
            user_data=user_data,
        )
        print(f"[JOB {job_id}] ✅ PDF generated: {pdf_path}")
    except Exception as exc:
        print(f"[JOB {job_id}] ⚠️  PDF generation failed (non-fatal): {exc}")
        traceback.print_exc()

    return {
        "program_id": program_id,
        "pdf_path": pdf_path,
        "schedule_count": len(schedule_entries),
    }
