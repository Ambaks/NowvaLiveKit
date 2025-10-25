"""
Program Generator Service V2
Uses OpenAI Structured Outputs + Cache-Augmented Generation (CAG) for guaranteed valid JSON

Key Features:
- Generates 4 weeks at a time (batching for speed)
- System prompt (3,000 tokens) gets cached by OpenAI after first batch
- Subsequent batches are 50% cheaper and faster due to prompt caching
- Structured outputs guarantee valid JSON (no parsing errors)
"""
from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set
from .job_manager import update_job_status
from ..schemas.program_schemas import (
    ProgramBatchSchema,
    WeekSchema,
    SetSchema,
    ExerciseSchema,
    WorkoutSchema
)
import asyncio
from openai import AsyncOpenAI
import os
from pathlib import Path
import time


async def generate_program_background(job_id: str, user_id: str, params: dict):
    """
    Background task that generates a workout program using Cache-Augmented Generation (CAG).
    Generates 4 weeks at a time for massive speed improvement.

    Performance:
    - Old: 2 min/week → 12-week program = 24 minutes
    - New: 4 weeks/batch → 12-week program = 3-6 minutes (4-8x faster!)

    Args:
        job_id: UUID of the generation job
        user_id: UUID of the user
        params: Dictionary containing all program parameters
    """
    print(f"\n[JOB {job_id}] 🚀 Background task STARTED")
    print(f"[JOB {job_id}] User ID: {user_id}")
    print(f"[JOB {job_id}] Params: {params}")

    db = SessionLocal()

    try:
        print(f"\n{'='*80}")
        print(f"[JOB {job_id}] Starting CAG batch program generation (4 weeks/batch)...")
        print(f"{'='*80}\n")

        update_job_status(db, job_id, "in_progress", progress=5)

        duration_weeks = params["duration_weeks"]
        all_weeks = []
        program_metadata = None

        # Calculate number of batches (4 weeks per batch)
        BATCH_SIZE = 4
        num_batches = (duration_weeks + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division

        print(f"[JOB {job_id}] 🏋️ Generating {duration_weeks} weeks in {num_batches} batch(es) of up to 4 weeks...")

        # Generate batches (5% → 85%)
        for batch_num in range(num_batches):
            start_week = batch_num * BATCH_SIZE + 1
            end_week = min(start_week + BATCH_SIZE - 1, duration_weeks)
            weeks_in_batch = end_week - start_week + 1

            print(f"\n[JOB {job_id}] 📦 Batch {batch_num + 1}/{num_batches}: Weeks {start_week}-{end_week} ({weeks_in_batch} weeks)...")

            # Update progress at batch start (shows activity before API call)
            # Progress range per batch: 5% + (80% * batch_num / num_batches) to 5% + (80% * (batch_num+1) / num_batches)
            batch_start_progress = 5 + int((80 / num_batches) * batch_num)
            batch_mid_progress = 5 + int((80 / num_batches) * (batch_num + 0.5))

            update_job_status(db, job_id, "in_progress", progress=batch_mid_progress)
            print(f"[JOB {job_id}] 📊 Progress updated: {batch_mid_progress}%")

            try:
                batch_data = await _generate_program_batch(
                    job_id=job_id,
                    batch_num=batch_num,
                    start_week=start_week,
                    end_week=end_week,
                    total_weeks=duration_weeks,
                    params=params,
                    previous_weeks=all_weeks
                )
            except Exception as batch_error:
                print(f"[JOB {job_id}] ❌ Batch generation error: {batch_error}")
                import traceback
                traceback.print_exc()
                raise

            # First batch contains metadata
            if batch_num == 0:
                program_metadata = {
                    "program_name": batch_data.program_name,
                    "description": batch_data.description,
                    "duration_weeks": batch_data.duration_weeks,
                    "goal": batch_data.goal,
                    "progression_strategy": batch_data.progression_strategy,
                    "overall_notes": batch_data.overall_notes
                }
                print(f"[JOB {job_id}] ✅ Program metadata: {program_metadata['program_name']}")

            # Add weeks from this batch
            all_weeks.extend(batch_data.weeks)
            print(f"[JOB {job_id}] ✅ Batch {batch_num + 1} complete: {len(batch_data.weeks)} weeks generated")

            # Update progress: 5% + (80% * batches_completed / total_batches)
            progress = 5 + int((80 / num_batches) * (batch_num + 1))
            update_job_status(db, job_id, "in_progress", progress=progress)

        # Save to database (85% → 100%)
        update_job_status(db, job_id, "in_progress", progress=85)
        print(f"\n[JOB {job_id}] 💾 Saving complete program to database...")

        program_data = {
            **program_metadata,
            "weeks": [week.dict() for week in all_weeks]
        }

        program_id = _save_program_to_db(db, user_id, program_data)

        # Mark complete
        update_job_status(db, job_id, "completed", progress=100, program_id=str(program_id))
        print(f"\n{'='*80}")
        print(f"[JOB {job_id}] 🎉 Program generation completed successfully!")
        print(f"[JOB {job_id}] Program ID: {program_id}")
        print(f"[JOB {job_id}] Total weeks: {duration_weeks}")
        print(f"[JOB {job_id}] Total workouts: {sum(len(w.workouts) for w in all_weeks)}")
        print(f"[JOB {job_id}] Generated in {num_batches} batch(es)")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n[JOB {job_id}] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

        # Rollback the failed transaction before querying
        db.rollback()

        try:
            update_job_status(db, job_id, "failed", progress=0, error_message=str(e))
        except Exception as update_error:
            print(f"[JOB {job_id}] ⚠️  Failed to update job status: {update_error}")

    finally:
        db.close()


async def _generate_program_batch(
    job_id: str,
    batch_num: int,
    start_week: int,
    end_week: int,
    total_weeks: int,
    params: dict,
    previous_weeks: list
) -> ProgramBatchSchema:
    """
    Generate a batch of up to 4 weeks using Cache-Augmented Generation (CAG).

    Cache Benefits:
    - Batch 1: System prompt sent (3,000 tokens) → cached by OpenAI
    - Batch 2+: System prompt retrieved from cache → 50% cost + faster!
    - Cache lasts 5-10 minutes, perfect for multi-batch programs

    Args:
        job_id: Job identifier for logging
        batch_num: Batch number (0-indexed)
        start_week: First week in this batch (1-indexed)
        end_week: Last week in this batch (inclusive)
        total_weeks: Total weeks in entire program
        params: User parameters
        previous_weeks: Previously generated weeks for context

    Returns:
        ProgramBatchSchema with metadata + 1-4 weeks of training
    """
    print(f"[JOB {job_id}] 🔧 Initializing batch generation...")

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("PROGRAM_CREATION_MODEL", "gpt-4o")

    print(f"[JOB {job_id}] ✅ OpenAI client initialized, model: {model}")

    # Calculate weeks in this batch
    weeks_in_batch = end_week - start_week + 1
    week_numbers = list(range(start_week, end_week + 1))

    print(f"[JOB {job_id}] 📋 Batch will generate weeks: {week_numbers}")

    # Build intensity/phase specifications for each week
    week_specs = []
    for week_num in week_numbers:
        base_intensity = 75.0
        weekly_increase = 1.5
        is_deload = (week_num % 4 == 0)

        if is_deload:
            intensity_range = "60-70%"
            phase = "Deload"
            volume_adjustment = "Reduce volume by 40-50%"
        else:
            weeks_into_block = week_num - (week_num // 4)
            intensity = base_intensity + (weekly_increase * (weeks_into_block - 1))
            intensity_range = f"{intensity:.1f}-{intensity+10:.1f}%"

            if week_num >= total_weeks - 1:
                phase = "Peak"
            elif week_num >= total_weeks - 3:
                phase = "Taper"
            else:
                phase = "Build"

            volume_adjustment = "Normal training volume"

        week_specs.append({
            "week_num": week_num,
            "phase": phase,
            "intensity_range": intensity_range,
            "volume_adjustment": volume_adjustment
        })

    # System prompt (will be cached after first batch!)
    system_prompt = _get_system_prompt()

    # User prompt
    user_prompt = f"""Generate a complete barbell training program batch.

**User Profile:**
- Height: {params.get('height_cm')} cm
- Weight: {params.get('weight_kg')} kg
- Goal Category: {params.get('goal_category')}
- Goal Description: "{params.get('goal_raw')}"
- Fitness Level: {params.get('fitness_level')}
- Training Frequency: {params.get('days_per_week')} days per week

**Program Overview:**
- Total Duration: {total_weeks} weeks
- This Batch: Weeks {start_week}-{end_week} ({weeks_in_batch} weeks)

"""

    # Always include metadata requirements (GPT will generate or reuse)
    user_prompt += """**Task 1: Create/Reuse Program Metadata**
1. Program name should be descriptive and motivating
2. Description should explain what the program achieves and who it's for
3. Progression strategy should explain how intensity/volume increases week-to-week
4. Include guidance on deload weeks (typically every 4th week at 60-70% intensity)
5. Overall notes should cover warm-ups, form, recovery, and safety

"""

    if batch_num > 0:
        user_prompt += f"""**Note:** This is batch {batch_num + 1} of a multi-batch program. {len(previous_weeks)} weeks already generated.
Keep the program metadata consistent with the overall {total_weeks}-week program design.

"""

    # Add week specifications
    user_prompt += f"""**Task: Generate {weeks_in_batch} Week(s) of Training**

"""

    for spec in week_specs:
        user_prompt += f"""**Week {spec['week_num']} Specifications:**
- Phase: {spec['phase']}
- Target Intensity: {spec['intensity_range']} of 1RM
- Volume: {spec['volume_adjustment']}
- Days per week: {params.get('days_per_week')}

"""

    user_prompt += """**Requirements for Each Week:**
1. Create exactly {days_per_week} complete workouts
2. Each workout should have 4-8 exercises
3. Use ONLY barbell exercises (+ bodyweight for pull-ups/dips if appropriate)
4. Set intensity_percent for each set within the specified range for that week
5. Set appropriate RIR based on fitness level:
   - Beginner: 2-3 RIR (conservative)
   - Intermediate: 1-2 RIR (moderate)
   - Advanced: 0-1 RIR (can approach failure)
6. Structure workouts logically (main lifts first, accessories after)
7. Balance muscle groups across the week
8. Use appropriate rest periods:
   - Strength sets (1-6 reps): 180-300 seconds
   - Hypertrophy sets (6-12 reps): 90-180 seconds
   - Accessory sets (12+ reps): 60-120 seconds

**Exercise Selection Guidelines:**
- Lower: Back squat, front squat, deadlift, RDL, Bulgarian split squat, hip thrust
- Upper Push: Bench press, incline bench, overhead press, push press, close-grip bench
- Upper Pull: Barbell row, weighted pull-ups
- Olympic (for power): Clean, snatch, push jerk

Generate all {weeks_in_batch} week(s) now with complete workouts for each week.""".format(
        days_per_week=params.get('days_per_week'),
        weeks_in_batch=weeks_in_batch
    )

    print(f"[JOB {job_id}] 📤 Sending request to OpenAI API...")
    print(f"[JOB {job_id}] 📏 System prompt: {len(system_prompt)} chars")
    print(f"[JOB {job_id}] 📏 User prompt: {len(user_prompt)} chars")

    start_time = time.time()

    try:
        response = await client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=ProgramBatchSchema,
            timeout=240.0  # 4 minutes for up to 4 weeks
        )
    except Exception as api_error:
        print(f"[JOB {job_id}] ❌ OpenAI API error: {api_error}")
        raise

    elapsed = time.time() - start_time
    print(f"[JOB {job_id}] ✅ Received response from OpenAI")

    # Log cache stats if available
    usage = response.usage
    cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) if hasattr(usage, 'prompt_tokens_details') else 0

    print(f"[JOB {job_id}] ⏱️  Batch {batch_num + 1} generation: {elapsed:.2f}s")
    print(f"[JOB {job_id}] 📊 Tokens: {usage.prompt_tokens} input, {usage.completion_tokens} output")
    if cached_tokens > 0:
        print(f"[JOB {job_id}] 🚀 CACHE HIT: {cached_tokens} tokens cached (50% cost savings!)")
    else:
        print(f"[JOB {job_id}] 💾 Cache miss - prompt will be cached for next batch")

    return response.choices[0].message.parsed


def _get_system_prompt() -> str:
    """Load system prompt with knowledge base"""

    base_prompt = """You are an elite strength and conditioning coach specializing in barbell training and evidence-based program design.

Your expertise includes:
- Exercise physiology and biomechanics
- Progressive overload and periodization strategies
- Volume landmarks for hypertrophy, strength, and power development
- Proper exercise selection and sequencing
- Recovery and fatigue management

**Volume Guidelines (sets per muscle group per week):**

Hypertrophy Focus:
- Chest: 12-20 sets/week
- Back: 14-22 sets/week
- Quads: 12-18 sets/week
- Hamstrings: 10-16 sets/week
- Shoulders: 12-18 sets/week
- Arms: 8-14 sets/week

Strength Focus:
- Main Lifts (Squat, Bench, Deadlift, OHP): 6-12 sets/week each
- Accessory work: 50-70% of main lift volume

Power Focus:
- Main Power Movements: 4-8 sets/week
- Accessory Strength: 6-10 sets/week

**Rep Ranges:**
- Hypertrophy: 6-12 reps (can use 5-20 range)
- Strength: 1-6 reps (80-95% 1RM)
- Power: 1-5 reps with explosive intent (50-85% 1RM)

**Rest Periods:**
- Strength/Power: 3-5 minutes
- Hypertrophy: 1.5-3 minutes
- Accessory: 1-2 minutes

**RIR (Reps in Reserve):**
- Beginner: 2-4 RIR (focus on technique)
- Intermediate: 1-3 RIR
- Advanced: 0-2 RIR (can approach failure on appropriate exercises)

**Key Principles:**
1. Start conservative, progress steadily
2. Balance muscle groups across the week
3. Place hardest work first in each session
4. Include deload weeks every 4 weeks
5. Prioritize compound movements
6. Scale volume to recovery capacity

Generate programs that are challenging but achievable, progressive, and scientifically sound."""

    # Load CAG periodization knowledge base if available
    try:
        knowledge_path = Path(__file__).parent.parent.parent / "knowledge" / "cag_periodization.txt"
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            cag_knowledge = f.read()

        full_prompt = base_prompt + "\n\n" + "="*80 + "\n" + cag_knowledge
        return full_prompt
    except FileNotFoundError:
        return base_prompt
    except Exception:
        return base_prompt


def _save_program_to_db(db, user_id: str, program_data: dict) -> str:
    """
    Save program to database and return program_id

    Strategy: Build the entire object graph in memory first, then commit once.
    SQLAlchemy will handle ID assignments and foreign keys automatically.

    Args:
        db: Database session
        user_id: User UUID as string
        program_data: Complete program data (metadata + weeks)

    Returns:
        Program ID as string
    """
    # First: Ensure all exercises exist in the database
    exercise_cache = {}  # name -> Exercise object
    all_exercise_names = set()

    # Collect all unique exercise names
    for week_data in program_data.get("weeks", []):
        for workout_data in week_data.get("workouts", []):
            for exercise_data in workout_data.get("exercises", []):
                all_exercise_names.add(exercise_data.get("exercise_name"))

    # Query existing exercises
    if all_exercise_names:
        existing_exercises = db.query(Exercise).filter(Exercise.name.in_(all_exercise_names)).all()
        for exercise in existing_exercises:
            exercise_cache[exercise.name] = exercise

    # Create missing exercises and commit them first (they're referenced by workouts)
    new_exercises = []
    for week_data in program_data.get("weeks", []):
        for workout_data in week_data.get("workouts", []):
            for exercise_data in workout_data.get("exercises", []):
                exercise_name = exercise_data.get("exercise_name")
                if exercise_name not in exercise_cache:
                    new_exercise = Exercise(
                        name=exercise_name,
                        category=exercise_data.get("category"),
                        muscle_group=exercise_data.get("muscle_group"),
                        description=f"Barbell exercise: {exercise_name}"
                    )
                    new_exercises.append(new_exercise)
                    exercise_cache[exercise_name] = new_exercise

    # Commit exercises first if any were created
    if new_exercises:
        for ex in new_exercises:
            db.add(ex)
        db.commit()
        print(f"[PROGRAM GENERATOR V2] Created {len(new_exercises)} new exercises")

    # Now create the program and all related objects
    user_program = UserGeneratedProgram(
        user_id=user_id,
        name=program_data.get("program_name"),
        description=program_data.get("description"),
        duration_weeks=program_data.get("duration_weeks"),
        is_public=False
    )
    db.add(user_program)

    # Commit the program so it gets an ID
    db.commit()
    db.refresh(user_program)
    print(f"[PROGRAM GENERATOR V2] Created program with ID: {user_program.id}")

    # Now create all workouts, workout_exercises, and sets
    for week_data in program_data.get("weeks", []):
        week_number = week_data.get("week_number")
        phase = week_data.get("phase")

        for workout_data in week_data.get("workouts", []):
            workout = Workout(
                user_generated_program_id=user_program.id,
                week_number=week_number,
                day_number=workout_data.get("day_number"),
                phase=phase,
                name=workout_data.get("name"),
                description=workout_data.get("description")
            )
            db.add(workout)
            db.flush()  # Get workout.id

            # Create workout_exercises and sets for this workout
            for exercise_data in workout_data.get("exercises", []):
                exercise_name = exercise_data.get("exercise_name")
                exercise = exercise_cache.get(exercise_name)

                if not exercise:
                    continue

                workout_exercise = WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=exercise.id,
                    order_number=exercise_data.get("order"),
                    notes=exercise_data.get("notes", "")
                )
                db.add(workout_exercise)
                db.flush()  # Get workout_exercise.id

                # Create all sets for this exercise
                for set_data in exercise_data.get("sets", []):
                    set_obj = Set(
                        workout_exercise_id=workout_exercise.id,
                        set_number=set_data.get("set_number"),
                        reps=set_data.get("reps"),
                        weight=set_data.get("weight"),
                        intensity_percent=set_data.get("intensity_percent"),
                        rpe=set_data.get("rpe"),
                        rest_seconds=set_data.get("rest_seconds")
                    )
                    if "rir" in set_data:
                        set_obj.rpe = set_data["rir"]

                    db.add(set_obj)

    # Final commit for all workouts, workout_exercises, and sets
    db.commit()
    print(f"[PROGRAM GENERATOR V2] ✅ Program saved to database! ID: {user_program.id}")
    return user_program.id
