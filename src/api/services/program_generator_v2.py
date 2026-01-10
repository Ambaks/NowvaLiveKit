"""
Program Generator Service V2
Uses OpenAI Structured Outputs + Knowledge Retrieval for guaranteed valid JSON

Key Features:
- Generates 4 weeks at a time (batching for speed)
- System prompt gets cached by OpenAI after first batch
- Subsequent batches are 50% cheaper and faster due to prompt caching
- Structured outputs guarantee valid JSON (no parsing errors)
- Supports both CAG (static) and RAG (dynamic retrieval)
"""
from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set
from .job_manager import update_job_status
from .markdown_generator import generate_program_markdown
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

# RAG integration
try:
    from contextual_rag.query_interface import retrieve_for_program_generation
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️  RAG module not available. Using CAG only.")


def _save_prompt_log(
    job_id: str,
    batch_num: int,
    system_prompt: str,
    user_prompt: str,
    rag_context: str = None,
    rag_query: str = None
):
    """
    Save prompts to disk for debugging and analysis

    Args:
        job_id: Generation job ID
        batch_num: Batch number (1, 2, 3...)
        system_prompt: Full system prompt
        user_prompt: User prompt
        rag_context: RAG retrieved context (if using RAG)
        rag_query: RAG search query (if using RAG)
    """
    # Check if logging is enabled
    if os.getenv("ENABLE_PROMPT_LOGGING", "false").lower() != "true":
        return

    # Create logs directory
    log_dir = Path("program_generation_logs")
    log_dir.mkdir(exist_ok=True)

    # Create filename with job_id and batch number
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"prompts_{job_id}_batch{batch_num}_{timestamp}.txt"

    # Build log content
    log_content = []
    log_content.append("=" * 80)
    log_content.append(f"PROGRAM GENERATION PROMPT LOG")
    log_content.append("=" * 80)
    log_content.append(f"Job ID: {job_id}")
    log_content.append(f"Batch: {batch_num}")
    log_content.append(f"Timestamp: {timestamp}")
    log_content.append("=" * 80)
    log_content.append("")

    # RAG info if available
    if rag_query or rag_context:
        log_content.append("=" * 80)
        log_content.append("RAG RETRIEVAL")
        log_content.append("=" * 80)
        if rag_query:
            log_content.append(f"Query: {rag_query}")
            log_content.append("")
        if rag_context:
            log_content.append(f"Retrieved Context ({len(rag_context)} chars, ~{len(rag_context)//4} tokens):")
            log_content.append("-" * 80)
            log_content.append(rag_context)
            log_content.append("-" * 80)
        log_content.append("")

    # System prompt
    log_content.append("=" * 80)
    log_content.append("SYSTEM PROMPT")
    log_content.append("=" * 80)
    log_content.append(f"Length: {len(system_prompt)} chars (~{len(system_prompt)//4} tokens)")
    log_content.append("-" * 80)
    log_content.append(system_prompt)
    log_content.append("-" * 80)
    log_content.append("")

    # User prompt
    log_content.append("=" * 80)
    log_content.append("USER PROMPT")
    log_content.append("=" * 80)
    log_content.append(f"Length: {len(user_prompt)} chars (~{len(user_prompt)//4} tokens)")
    log_content.append("-" * 80)
    log_content.append(user_prompt)
    log_content.append("-" * 80)
    log_content.append("")

    # Total
    total_chars = len(system_prompt) + len(user_prompt)
    log_content.append("=" * 80)
    log_content.append(f"TOTAL: {total_chars} chars (~{total_chars//4} tokens)")
    log_content.append("=" * 80)

    # Write to file
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_content))

    print(f"[JOB {job_id}] 📝 Saved prompt log to: {log_file}")


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
    # Start overall timing
    total_start_time = time.time()

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
        first_batch_data = None  # Store first batch for markdown generation

        # Calculate number of batches with smart batch sizing based on total workouts
        # This prevents hitting the 16,384 token output limit on gpt-4o
        workouts_per_week = params["days_per_week"]
        total_workouts = duration_weeks * workouts_per_week

        if total_workouts <= 6:      # 1-2 weeks at any frequency
            BATCH_SIZE = duration_weeks  # Generate all at once
        elif total_workouts <= 20:   # ~3-7 weeks at 3-5 days/week
            BATCH_SIZE = 3
        elif total_workouts <= 40:   # ~8-13 weeks at 3 days or ~8-10 weeks at 4-5 days
            BATCH_SIZE = 3
        else:                        # 12+ weeks at 5 days/week (60+ workouts)
            BATCH_SIZE = 2           # Smaller batches to avoid 16K token limit

        num_batches = (duration_weeks + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division

        print(f"[JOB {job_id}] 🏋️ Generating {duration_weeks} weeks in {num_batches} batch(es) of up to {BATCH_SIZE} weeks...")
        print(f"[JOB {job_id}] 📦 Batch size: {BATCH_SIZE} (optimized for {total_workouts} total workouts: {duration_weeks} weeks × {workouts_per_week} days/week)")

        # =====================================================================
        # ONE-TIME RAG RETRIEVAL (before all batches for caching efficiency)
        # =====================================================================
        # Feature flag: Use RAG (dynamic retrieval) or CAG (static knowledge)
        use_rag = os.getenv("USE_RAG", "false").lower() == "true" and RAG_AVAILABLE

        system_prompt = None
        rag_context = None
        rag_query = None

        if use_rag:
            # Build RAG query from overall program parameters (NOT batch-specific)
            rag_query = _build_rag_query(params, [])  # Empty week_specs for consistency
            print(f"[JOB {job_id}] 🔍 RAG MODE: One-time retrieval for query: {rag_query}")

            try:
                rag_context = await retrieve_for_program_generation(
                    query=rag_query,
                    top_k=10,
                    use_reranker=True,
                    max_tokens=2000
                )
                print(f"[JOB {job_id}] ✅ RAG retrieval successful (~{len(rag_context)//4} tokens)")
                print(f"[JOB {job_id}] 🔒 This RAG context will be reused for all {num_batches} batches (enables caching)")
                system_prompt = _build_system_prompt_with_rag(rag_context)
            except Exception as e:
                print(f"[JOB {job_id}] ⚠️  RAG retrieval failed: {e}")
                print(f"[JOB {job_id}] ↩️  Falling back to CAG")
                system_prompt = _get_system_prompt(duration_weeks)
                rag_query = None
        else:
            # Use traditional CAG approach
            print(f"[JOB {job_id}] 📚 CAG MODE: Using static knowledge base")
            system_prompt = _get_system_prompt(duration_weeks)

        # Timing tracking
        batch_times = []
        generation_start_time = time.time()

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

            print(f"[JOB {job_id}] 📊 Updating progress to {batch_mid_progress}%...")
            update_job_status(db, job_id, "in_progress", progress=batch_mid_progress)
            print(f"[JOB {job_id}] ✅ Progress updated: {batch_mid_progress}%")

            try:
                batch_start = time.time()
                print(f"[JOB {job_id}] 🚀 Starting batch generation for weeks {start_week}-{end_week}...")
                batch_data = await _generate_program_batch(
                    job_id=job_id,
                    batch_num=batch_num,
                    start_week=start_week,
                    end_week=end_week,
                    total_weeks=duration_weeks,
                    params=params,
                    previous_weeks=all_weeks,
                    system_prompt=system_prompt,  # Reuse same prompt for caching
                    rag_context=rag_context,       # For logging only
                    rag_query=rag_query            # For logging only
                )
                batch_elapsed = time.time() - batch_start
                batch_times.append(batch_elapsed)
            except Exception as batch_error:
                print(f"[JOB {job_id}] ❌ Batch generation error: {batch_error}")
                import traceback
                traceback.print_exc()
                raise

            # First batch contains metadata
            if batch_num == 0:
                first_batch_data = batch_data  # Store for markdown generation
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

        generation_elapsed = time.time() - generation_start_time

        # Save to database (85% → 100%)
        update_job_status(db, job_id, "in_progress", progress=85)
        print(f"\n[JOB {job_id}] 💾 Saving complete program to database...")
        db_save_start = time.time()

        program_data = {
            **program_metadata,
            "weeks": [week.dict() for week in all_weeks]
        }

        program_id = _save_program_to_db(db, user_id, program_data)
        db_save_elapsed = time.time() - db_save_start

        # Create schedule entries for the program (85% → 90%)
        update_job_status(db, job_id, "in_progress", progress=85)
        schedule_start = time.time()
        try:
            print(f"\n[JOB {job_id}] 📅 Creating workout schedule...")
            from db.schedule_utils import create_schedule_for_program, get_next_monday

            # Get days_per_week from params (default to 3 if not specified)
            days_per_week = params.get("days_per_week", 3)
            start_date = get_next_monday()  # Start on next Monday

            schedule_entries = create_schedule_for_program(
                db=db,
                user_id=user_id,
                program_id=program_id,
                program_type="user_generated",
                start_date=start_date,
                days_per_week=days_per_week
            )

            schedule_elapsed = time.time() - schedule_start
            print(f"[JOB {job_id}] ✅ Created {len(schedule_entries)} schedule entries (start: {start_date.isoformat()}) in {schedule_elapsed:.1f}s")
        except Exception as schedule_error:
            print(f"[JOB {job_id}] ⚠️  Failed to create schedule: {schedule_error}")
            # Don't fail the whole job if schedule creation fails
            import traceback
            traceback.print_exc()

        # Generate markdown file (90% → 95%)
        update_job_status(db, job_id, "in_progress", progress=90)
        markdown_start = time.time()
        try:
            print(f"\n[JOB {job_id}] 📄 Generating markdown file...")
            _generate_markdown_file(db, program_id, user_id, params, first_batch_data)
            print(f"[JOB {job_id}] ✅ Markdown file generated")
        except Exception as md_error:
            # Don't fail the job if markdown generation fails
            print(f"[JOB {job_id}] ⚠️  Markdown generation failed (non-fatal): {md_error}")
            import traceback
            traceback.print_exc()
        markdown_elapsed = time.time() - markdown_start

        # Mark complete
        total_elapsed = time.time() - total_start_time
        update_job_status(db, job_id, "completed", progress=100, program_id=str(program_id))

        # Print comprehensive timing report
        print(f"\n{'='*80}")
        print(f"[JOB {job_id}] 🎉 Program generation completed successfully!")
        print(f"[JOB {job_id}] Program ID: {program_id}")
        print(f"[JOB {job_id}] Total weeks: {duration_weeks}")
        print(f"[JOB {job_id}] Total workouts: {sum(len(w.workouts) for w in all_weeks)}")
        print(f"[JOB {job_id}] Generated in {num_batches} batch(es)")
        print(f"\n{'='*80}")
        print(f"⏱️  TIMING BREAKDOWN:")
        print(f"{'='*80}")
        for i, batch_time in enumerate(batch_times):
            print(f"  Batch {i+1}: {batch_time:.2f}s")
        print(f"  Total AI generation: {generation_elapsed:.2f}s")
        print(f"  Database save: {db_save_elapsed:.2f}s")
        print(f"  Markdown generation: {markdown_elapsed:.2f}s")
        print(f"  TOTAL TIME: {total_elapsed:.2f}s ({total_elapsed/60:.2f} minutes)")
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


def _generate_weeks_summary(previous_weeks: list, params: dict) -> str:
    """
    Generate TOON-optimized summary of previous weeks for context passing.

    TOON Format: Token-Optimized Object Notation - compact, human-readable,
    LLM-friendly format that reduces token usage by 70-75% vs JSON.

    Args:
        previous_weeks: List of WeekSchema objects from previous batches
        params: User parameters (for split pattern context)

    Returns:
        Compact formatted summary string
    """
    if not previous_weeks:
        return ""

    # Track muscle groups across weeks
    muscle_groups = ["Quads", "Hamstrings", "Glutes", "Chest", "Back", "Shoulders", "Triceps", "Biceps"]
    muscle_abbrev = {"Quads": "Q", "Hamstrings": "H", "Glutes": "G", "Chest": "C",
                     "Back": "B", "Shoulders": "S", "Triceps": "T", "Biceps": "Bi"}

    summary = "=== PREVIOUS WEEKS CONTEXT ===\n\n"

    # Section 1: Workout Details (compact notation)
    summary += "WORKOUTS (Format: Exercise Sets×Reps@%1RM):\n"

    weekly_volumes = {}
    weekly_intensities = {}
    exercise_variants = {}
    total_sets_per_week = {}

    for week in previous_weeks:
        week_num = week.week_number
        weekly_volumes[week_num] = {mg: 0 for mg in muscle_groups}
        weekly_intensities[week_num] = []
        total_sets_per_week[week_num] = 0

        for workout in week.workouts:
            workout_line = f"W{week_num}.D{workout.day_number}: "
            exercises_str = []
            workout_total_sets = 0

            for exercise in workout.exercises:
                # Track exercise variants
                ex_name = exercise.exercise_name
                if ex_name not in exercise_variants:
                    exercise_variants[ex_name] = set()
                exercise_variants[ex_name].add(week_num)

                # Count sets for this exercise
                num_sets = len(exercise.sets)
                workout_total_sets += num_sets

                # Get representative set (first set)
                first_set = exercise.sets[0]
                reps = first_set.reps
                intensity = int(first_set.intensity_percent)

                # Track intensity
                weekly_intensities[week_num].append(intensity)

                # Track muscle group volume
                mg = exercise.muscle_group
                if mg in weekly_volumes[week_num]:
                    weekly_volumes[week_num][mg] += num_sets

                # Shorten exercise name
                ex_short = ex_name.replace("Barbell ", "").replace("Dumbbell ", "")
                if len(ex_short) > 15:
                    # Smart abbreviations
                    ex_short = ex_short.replace("Back Squat", "Squat") \
                                       .replace("Bench Press", "Bench") \
                                       .replace("Romanian Deadlift", "RDL") \
                                       .replace("Overhead Press", "OHP") \
                                       .replace("Front Squat", "F.Squat") \
                                       .replace("Incline ", "Inc.") \
                                       .replace("Close-Grip ", "CG.") \
                                       .replace("Tricep ", "Tri.") \
                                       .replace("Extension", "Ext")

                exercises_str.append(f"{ex_short} {num_sets}×{reps}@{intensity}%")

            total_sets_per_week[week_num] += workout_total_sets
            workout_line += ", ".join(exercises_str) + f" ({workout_total_sets}s)"
            summary += workout_line + "\n"

        summary += "\n"

    # Section 2: Muscle Volume per Week
    summary += "MUSCLE VOLUME/WEEK (sets):\n"
    for week_num in sorted(weekly_volumes.keys()):
        volumes = weekly_volumes[week_num]

        # Group by body region
        lower = f"Q{volumes['Quads']} H{volumes['Hamstrings']} G{volumes['Glutes']}"
        upper_push = f"C{volumes['Chest']}"
        upper_pull = f"B{volumes['Back']}"
        shoulders = f"S{volumes['Shoulders']}"
        arms = f"T{volumes['Triceps']} Bi{volumes['Biceps']}"

        total = sum(volumes.values())

        # Detect if deload week
        is_deload = total < total_sets_per_week.get(week_num - 1, total) * 0.75
        deload_note = " (DELOAD)" if is_deload else ""

        summary += f"W{week_num}: {lower} | {upper_push} {upper_pull} | {shoulders} {arms} = {total} total{deload_note}\n"

    summary += "\n"

    # Section 3: Progression Patterns
    summary += "PROGRESSION:\n"

    # Volume progression
    week_nums = sorted(total_sets_per_week.keys())
    if len(week_nums) >= 2:
        volume_changes = []
        for i in range(1, len(week_nums)):
            prev_vol = total_sets_per_week[week_nums[i-1]]
            curr_vol = total_sets_per_week[week_nums[i]]
            if prev_vol > 0:
                pct_change = ((curr_vol - prev_vol) / prev_vol) * 100
                volume_changes.append(f"W{week_nums[i-1]}→W{week_nums[i]} {pct_change:+.0f}%")
        summary += f"- Volume: {', '.join(volume_changes)}\n"

    # Intensity progression
    if weekly_intensities:
        intensity_ranges = []
        for week_num in sorted(weekly_intensities.keys()):
            intensities = weekly_intensities[week_num]
            if intensities:
                min_int = min(intensities)
                max_int = max(intensities)
                avg_int = sum(intensities) // len(intensities)
                intensity_ranges.append(f"W{week_num}:{min_int}-{max_int}%(avg {avg_int}%)")
        summary += f"- Intensity: {', '.join(intensity_ranges)}\n"

    # Exercise variants used (group similar exercises)
    if exercise_variants:
        # Group by base movement
        squat_vars = [ex for ex in exercise_variants.keys() if "Squat" in ex]
        bench_vars = [ex for ex in exercise_variants.keys() if "Bench" in ex]
        dead_vars = [ex for ex in exercise_variants.keys() if "Dead" in ex or "RDL" in ex]

        if squat_vars:
            squat_summary = ", ".join([ex.replace("Barbell ", "").replace("Back ", "")
                                      for ex in squat_vars[:3]])  # Limit to 3
            summary += f"- Squat variants: {squat_summary}\n"

        if bench_vars:
            bench_summary = ", ".join([ex.replace("Barbell ", "").replace("Press", "")
                                      for ex in bench_vars[:3]])
            summary += f"- Bench variants: {bench_summary}\n"

        if dead_vars:
            dead_summary = ", ".join([ex.replace("Barbell ", "") for ex in dead_vars[:3]])
            summary += f"- Deadlift variants: {dead_summary}\n"

    # Training split
    if previous_weeks:
        first_week = previous_weeks[0]
        workout_names = [w.name for w in first_week.workouts]
        summary += f"- Split pattern: {', '.join(workout_names)}\n"

    summary += "\n"

    return summary


def _build_user_prompt(
    total_weeks: int,
    start_week: int,
    end_week: int,
    weeks_in_batch: int,
    batch_num: int,
    params: dict,
    week_specs: list,
    previous_weeks: list
) -> str:
    """Build user prompt optimized for program duration

    Args:
        total_weeks: Total program duration
        start_week: First week in batch
        end_week: Last week in batch
        weeks_in_batch: Number of weeks in this batch
        batch_num: Current batch number
        params: User parameters
        week_specs: Week specifications with phase, intensity, etc.
        previous_weeks: Previously generated weeks

    Returns:
        Optimized user prompt string
    """
    # Determine prompt complexity based on total program duration
    # Short programs (1-2 weeks): Simplified, focused
    # Medium programs (3-7 weeks): Moderate detail
    # Long programs (8+ weeks): Full detail with periodization
    is_short = total_weeks <= 2
    is_medium = 3 <= total_weeks <= 7
    is_long = total_weeks >= 8

    # Start with common user profile (all program lengths need this)
    user_prompt = f"""Generate a complete barbell training program batch.

**User Profile:**
- Height: {params.get('height_cm')} cm
- Weight: {params.get('weight_kg')} kg
- Age/Sex: {params.get('age')}{params.get('sex')}
- Goal Category: {params.get('goal_category')}
- Goal Description: "{params.get('goal_raw')}"
- Fitness Level: {params.get('fitness_level')}
- Training Frequency: {params.get('days_per_week')} days per week
- Session Duration: {params.get('session_duration', 60)} minutes"""

    # Add injury history and sport only if relevant (skip for very short programs)
    if not is_short or params.get('injury_history', 'none') != 'none':
        user_prompt += f"""
- Injury History: {params.get('injury_history', 'none')}"""

    if not is_short or params.get('specific_sport', 'none') != 'none':
        user_prompt += f"""
- Sport: {params.get('specific_sport', 'none')}"""

    # VBT only matters for power/Olympic lift programs
    if params.get('has_vbt_capability') or params.get('goal_category') == 'Power':
        user_prompt += f"""
- VBT Equipment Available: {'Yes' if params.get('has_vbt_capability') else 'No'}"""

    # Add user notes if provided
    user_notes = params.get('user_notes')
    if user_notes and user_notes.strip():
        user_prompt += f"""
- **Additional User Notes/Preferences:** {user_notes}
  (IMPORTANT: Incorporate these preferences into the program design where applicable)"""

    user_prompt += f"""

**Program Overview:**
- Total Duration: {total_weeks} weeks
- This Batch: Weeks {start_week}-{end_week} ({weeks_in_batch} weeks)

"""

    # Metadata requirements - simplified for short programs
    if is_short:
        user_prompt += """**Task 1: Create Program Metadata**
1. Program name should be clear and descriptive
2. Description should explain the program's focus
3. Progression strategy (if applicable for 2-week programs)
4. Overall notes should cover warm-ups, form, and safety

"""
    elif is_medium:
        user_prompt += """**Task 1: Create Program Metadata**
1. Program name should be descriptive and motivating
2. Description should explain what the program achieves
3. Progression strategy should explain how intensity/volume increases
4. Deload guidance if program is 5-7 weeks (typically week 4 or 6)
5. Overall notes should cover warm-ups, form, recovery, and safety

"""
    else:  # Long programs
        user_prompt += """**Task 1: Create/Reuse Program Metadata**
1. Program name should be descriptive and motivating
2. Description should explain what the program achieves and who it's for
3. Progression strategy should explain how intensity/volume increases week-to-week
4. Include guidance on deload weeks (typically every 4th week at 60-70% intensity)
5. Overall notes should cover warm-ups, form, recovery, and safety

"""

    # Multi-batch context with TOON-formatted summary
    if batch_num > 0 and previous_weeks:
        user_prompt += f"""**Note:** This is batch {batch_num + 1} of a multi-batch program. {len(previous_weeks)} weeks already generated.
Keep the program metadata consistent with the overall {total_weeks}-week program design.

"""
        # Add TOON-formatted summary of previous weeks
        weeks_summary = _generate_weeks_summary(previous_weeks, params)
        user_prompt += weeks_summary

        # Add instructions for using the context
        user_prompt += """**Instructions for Using Previous Context:**
1. Maintain progressive overload based on volume and intensity trends shown above
2. Balance muscle group distribution to avoid overtraining specific areas
3. Vary exercise selection - don't overuse the same movements from previous weeks
4. Continue the established split pattern for consistency
5. Ensure logical week-to-week progression in both intensity and volume

"""

    # Week generation task
    user_prompt += f"""**Task: Generate {weeks_in_batch} Week(s) of Training**

"""

    # Week specifications - simplified for short programs
    for spec in week_specs:
        if is_short:
            # Minimal detail for 1-2 week programs
            user_prompt += f"""**Week {spec['week_num']}:** {spec['phase']} - {spec['intensity_range']} intensity, {params.get('days_per_week')} days

"""
        else:
            # Full detail for 3+ week programs
            user_prompt += f"""**Week {spec['week_num']} Specifications:**
- Phase: {spec['phase']}
- Target Intensity: {spec['intensity_range']} of 1RM
- Volume: {spec['volume_adjustment']}
- Days per week: {params.get('days_per_week')}

"""

    # Requirements - scaled by program length
    if is_short:
        # Simplified requirements for 1-2 week programs
        goal_category = params.get('goal_category', '').lower()
        goal_specific_requirements = ""

        if goal_category == 'power':
            goal_specific_requirements = """
**CRITICAL POWER PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - EVERY workout MUST include at least 1 Olympic lift (power clean, hang clean, clean & jerk, snatch, push press, push jerk)
   - EVERY workout MUST include minimum 2 plyometric exercises (box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops)
   - Plyometric volume: 80-140 foot contacts per week (example: Box Jumps 4x5, Broad Jumps 3x3, Depth Jumps 3x3 per session)
"""
        elif goal_category == 'hypertrophy':
            goal_specific_requirements = """
**CRITICAL HYPERTROPHY PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - Each day of the week MUST have DIFFERENT compound lifts (e.g., Day 1: Squat+Row, Day 2: Deadlift+Bench, Day 3: Front Squat+OHP)
   - DO NOT program the same compounds (e.g., Back Squat + Bench Press) on multiple days - that's powerlifting, not hypertrophy
   - Include variety in movement patterns: squat variations, hinge variations, horizontal/vertical push, horizontal/vertical pull
   - Use multiple rep ranges across the week: 6-8, 8-12, 12-15, 15-20
   - Accessories must vary across the week (no repeating same exercise twice in same week)
   - Example CORRECT Day 1: Back Squat, Barbell Row, Barbell RDL, accessories
   - Example CORRECT Day 2: Romanian Deadlift, Bench Press, accessories
   - Example WRONG: Back Squat + Bench Press every single day
"""

        user_prompt += f"""**Requirements:**
1. Create exactly {params.get('days_per_week')} complete workouts per week
2. Each workout: adjust the number of exercises based on the workout duration which is {params.get('session_duration')} minutes
3. Use primarily barbell exercises. Plyometrics and bodyweight movements are always allowed (especially for power/athletic programs). DO NOT use dumbbells, cables, kettlebells, or bands unless user explicitly mentions having them in notes.{goal_specific_requirements}
4. **Exercise selection:**
   - Maximum 2 compound lifts per workout (squat/deadlift/bench/press/row/Olympic lift variations)
   - Keep main compounds consistent throughout the program
   - Vary accessories: Do NOT repeat the same accessory exercise twice in the same week (e.g., if Monday has barbell curls, Wednesday should have a different bicep exercise)
5. Set appropriate RIR
6. Structure workouts: main lifts first, accessories after

Generate all {weeks_in_batch} week(s) now with complete workouts."""

    elif is_medium:
        # Moderate detail for 3-7 week programs
        goal_category = params.get('goal_category', '').lower()
        goal_specific_requirements = ""

        if goal_category == 'power':
            goal_specific_requirements = """

**CRITICAL POWER PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - EVERY workout MUST include at least 1 Olympic lift (power clean, hang clean, clean & jerk, snatch, push press, push jerk)
   - EVERY workout MUST include minimum 2 plyometric exercises (box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops)
   - Plyometric volume: 80-140 foot contacts per week (example: Box Jumps 4x5, Broad Jumps 3x3, Depth Jumps 3x3 per session)
"""
        elif goal_category == 'hypertrophy':
            goal_specific_requirements = """

**CRITICAL HYPERTROPHY PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - Each day of the week MUST have DIFFERENT compound lifts (e.g., Day 1: Squat+Row, Day 2: Deadlift+Bench, Day 3: Front Squat+OHP)
   - DO NOT program the same compounds (e.g., Back Squat + Bench Press) on multiple days - that's powerlifting, not hypertrophy
   - Include variety in movement patterns: squat variations, hinge variations, horizontal/vertical push, horizontal/vertical pull
   - Use multiple rep ranges across the week: 6-8, 8-12, 12-15, 15-20
   - Accessories must vary across the week (no repeating same exercise twice in same week)
   - Example CORRECT Day 1: Back Squat, Barbell Row, Barbell RDL, accessories
   - Example CORRECT Day 2: Romanian Deadlift, Bench Press, accessories
   - Example WRONG: Back Squat + Bench Press every single day
"""

        user_prompt += f"""**Requirements for Each Week:**
1. Create exactly {params.get('days_per_week')} complete workouts
2. Each workout: adjust the number of exercises based on the workout duration which is {params.get('session_duration')} minutes
3. Use primarily barbell exercises. Plyometrics and bodyweight movements are always allowed (especially for power/athletic programs). DO NOT use dumbbells, cables, kettlebells, or bands unless user explicitly mentions having them in notes.{goal_specific_requirements}
4. **Exercise selection:**
   - Maximum 2 compound lifts per workout (squat/deadlift/bench/press/row/Olympic lift variations)
   - Keep main compounds consistent throughout the program
   - Vary accessories: Do NOT repeat the same accessory exercise twice in the same week (e.g., if Monday has barbell curls, Wednesday should have a different bicep exercise)
   - Change accessories every 2-4 weeks for variety
5. Set intensity_percent for each set within the specified range
6. Set appropriate RIR
7. Structure workouts logically (main lifts first, accessories after)
8. Balance muscle groups across the week

Generate all {weeks_in_batch} week(s) now with complete workouts for each week."""

    else:  # Long programs (8+ weeks)
        # Full detail for long programs
        goal_category = params.get('goal_category', '').lower()
        goal_specific_requirements = ""

        if goal_category == 'power':
            goal_specific_requirements = """

**CRITICAL POWER PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - EVERY workout MUST include at least 1 Olympic lift (power clean, hang clean, clean & jerk, snatch, push press, push jerk)
   - EVERY workout MUST include minimum 2 plyometric exercises (box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops)
   - Plyometric volume: 80-140 foot contacts per week (example: Box Jumps 4x5, Broad Jumps 3x3, Depth Jumps 3x3 per session)
"""
        elif goal_category == 'hypertrophy':
            goal_specific_requirements = """

**CRITICAL HYPERTROPHY PROGRAM REQUIREMENTS (NON-NEGOTIABLE):**
   - Each day of the week MUST have DIFFERENT compound lifts (e.g., Day 1: Squat+Row, Day 2: Deadlift+Bench, Day 3: Front Squat+OHP)
   - DO NOT program the same compounds (e.g., Back Squat + Bench Press) on multiple days - that's powerlifting, not hypertrophy
   - Include variety in movement patterns: squat variations, hinge variations, horizontal/vertical push, horizontal/vertical pull
   - Use multiple rep ranges across the week: 6-8, 8-12, 12-15, 15-20
   - Accessories must vary across the week (no repeating same exercise twice in same week)
   - Example CORRECT Day 1: Back Squat, Barbell Row, Barbell RDL, accessories
   - Example CORRECT Day 2: Romanian Deadlift, Bench Press, accessories
   - Example WRONG: Back Squat + Bench Press every single day
"""

        user_prompt += f"""**Requirements for Each Week:**
1. Create exactly {params.get('days_per_week')} complete workouts
2. Each workout: adjust the number of exercises based on the workout duration which is {params.get('session_duration')} minutes
3. Use primarily barbell exercises. Plyometrics and bodyweight movements are always allowed (especially for power/athletic programs). DO NOT use dumbbells, cables, kettlebells, or bands unless user explicitly mentions having them in notes.{goal_specific_requirements}
4. **Exercise selection:**
   - Maximum 2 compound lifts per workout (squat/deadlift/bench/press/row/Olympic lift variations)
   - Keep main compounds consistent throughout the program (e.g., if Week 1 has back squat, keep it in subsequent weeks)
   - Vary accessories: Do NOT repeat the same accessory exercise twice in the same week (e.g., if Monday has barbell curls, Wednesday should have a different bicep exercise)
   - Change accessories every 2-4 weeks to prevent adaptation and maintain engagement
5. Set intensity_percent for each set within the specified range for that week
6. Set appropriate RIR
7. Structure workouts logically (main lifts first, accessories after)
8. Balance muscle groups across the week
9. Use appropriate rest periods

Generate all {weeks_in_batch} week(s) now with complete workouts for each week."""

    return user_prompt


async def _generate_program_batch(
    job_id: str,
    batch_num: int,
    start_week: int,
    end_week: int,
    total_weeks: int,
    params: dict,
    previous_weeks: list,
    system_prompt: str,
    rag_context: str = None,
    rag_query: str = None
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
        system_prompt: Pre-built system prompt (same for all batches to enable caching)
        rag_context: RAG context (for logging only, already in system_prompt)
        rag_query: RAG query (for logging only)

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

    # System prompt is now passed in (built once before all batches for caching)
    # No need to rebuild it here!

    # User prompt - optimized based on program duration
    user_prompt = _build_user_prompt(
        total_weeks=total_weeks,
        start_week=start_week,
        end_week=end_week,
        weeks_in_batch=weeks_in_batch,
        batch_num=batch_num,
        params=params,
        week_specs=week_specs,
        previous_weeks=previous_weeks
    )

    print(f"[JOB {job_id}] 📤 Sending request to OpenAI API...")
    print(f"[JOB {job_id}] 📏 System prompt: {len(system_prompt)} chars (~{len(system_prompt)//4} tokens)")
    print(f"[JOB {job_id}] 📏 User prompt: {len(user_prompt)} chars (~{len(user_prompt)//4} tokens)")

    # Log TOON context if included
    if batch_num > 0 and previous_weeks:
        summary = _generate_weeks_summary(previous_weeks, params)
        summary_tokens = len(summary) // 4
        print(f"[JOB {job_id}] 📋 TOON context: {len(previous_weeks)} weeks, ~{summary_tokens} tokens (70-75% savings vs JSON)")

    print(f"[JOB {job_id}] 📏 Total prompt size: ~{(len(system_prompt) + len(user_prompt))//4} tokens")
    print(f"[JOB {job_id}] ⏰ Timeout set to 480.0 seconds (8 minutes)")
    print(f"[JOB {job_id}] 🤖 Using model: {model}")

    # Log optimization strategy
    if total_weeks <= 2:
        print(f"[JOB {job_id}] 🚀 OPTIMIZATION: Using SHORT CAG + simplified prompts for {total_weeks}-week program")
    elif total_weeks <= 7:
        print(f"[JOB {job_id}] 🚀 OPTIMIZATION: Using MEDIUM CAG + moderate prompts for {total_weeks}-week program")
    else:
        print(f"[JOB {job_id}] 🚀 OPTIMIZATION: Using FULL CAG + detailed prompts for {total_weeks}-week program")

    # Save prompts to disk if logging is enabled
    _save_prompt_log(
        job_id=job_id,
        batch_num=batch_num + 1,  # Convert 0-indexed to 1-indexed for user clarity
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rag_context=rag_context,
        rag_query=rag_query
    )

    start_time = time.time()

    try:
        print(f"[JOB {job_id}] 🔄 Awaiting OpenAI response...")
        response = await client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=ProgramBatchSchema,
            timeout=480.0  # 8 minutes for up to 4 weeks (increased for GPT-5-mini)
        )
        print(f"[JOB {job_id}] ✅ OpenAI API call completed successfully")
    except Exception as api_error:
        elapsed_error = time.time() - start_time
        print(f"[JOB {job_id}] ❌ OpenAI API error after {elapsed_error:.2f}s: {type(api_error).__name__}")
        print(f"[JOB {job_id}] Error details: {str(api_error)[:500]}")
        raise

    elapsed = time.time() - start_time
    print(f"[JOB {job_id}] ⏱️  OpenAI response received in {elapsed:.2f}s")
    print(f"[JOB {job_id}] 📦 Parsing response...")

    # Log cache stats if available
    usage = response.usage
    cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) if hasattr(usage, 'prompt_tokens_details') else 0

    print(f"[JOB {job_id}] ⏱️  Batch {batch_num + 1} generation: {elapsed:.2f}s")
    print(f"[JOB {job_id}] ⏱️  Time per week: {elapsed/weeks_in_batch:.2f}s")
    print(f"[JOB {job_id}] 📊 Tokens: {usage.prompt_tokens} input, {usage.completion_tokens} output, {usage.total_tokens} total")
    if cached_tokens > 0:
        print(f"[JOB {job_id}] 🚀 CACHE HIT: {cached_tokens} tokens cached (50% cost savings!)")
    else:
        print(f"[JOB {job_id}] 💾 Cache miss - prompt will be cached for next batch")

    # Log to session
    from core.session_logger import SessionLogger
    session_logger = SessionLogger.get_instance()

    # Ensure session is started (fallback if server didn't initialize properly)
    if session_logger.log_file_path is None:
        session_logger.start_session()
        print(f"[JOB {job_id}] ⚠️  Session logger wasn't initialized - started new session")

    session_logger.log_llm_call(
        component="program_generation",
        model=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cached_tokens=cached_tokens,
        details={
            "batch_num": batch_num + 1,
            "weeks": f"{start_week}-{end_week}",
            "duration_seconds": elapsed,
            "job_id": job_id
        }
    )

    return response.choices[0].message.parsed


def _get_system_prompt(duration_weeks: int) -> str:
    """Load system prompt with appropriate CAG knowledge base based on program duration

    Args:
        duration_weeks: Total program duration to determine which CAG file to load

    Returns:
        Complete system prompt with appropriate CAG knowledge
    """
    print(f"[PROMPT] Loading system prompt for {duration_weeks}-week program...")

    base_prompt = """
# Your Role

You are a specialized program generation AI with access to a Barbell-Focused Strength & Conditioning information containing Olympic-level programming knowledge.

**Task:** Create evidence-based, personalized training programs using only barbell exercises unless otherwise specified by the user, customized to the user's inputs.

# Critical Constraints

## Equipment
* **Primary:** Barbell, weight plates, squat rack with safeties, adjustable bench
* **Bodyweight movements:** Always allowed - plyometrics (box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops), pull-ups/chin-ups (if user has access)
* **Additional equipment:** Dumbbells, cables, kettlebells, bands - **DO NOT USE unless user explicitly mentions having them in their notes**
* **Forbidden:** Machines (unless user explicitly requests)

## Exercise Selection Rules
* Check for relevant exercises in the barbell exercise library
* Make sure to include a basic warmup near the top of the program that can be reused before every workout (about 5 mins long)
* **Volume distribution:** Compound movements first (60-70%), isolation/accessories second (30-40%)
* **Compound lift rules:**
  - Maximum 2 compound lifts per workout (spread heavy work across the week, don't stack it all on one day)
  - Keep main compound lifts consistent WITHIN each day across weeks (e.g., if Week 1 Day 1 has back squat, keep back squat on Day 1 in Week 2/3/4)
  - **HOWEVER:** Each day of the week should have DIFFERENT compound lifts (Day 1: Squat+Row, Day 2: Deadlift+Bench, Day 3: Front Squat+OHP)
  - Compounds = squat variations, deadlift variations, bench/press variations, rows, Olympic lifts
* **Accessory exercise rules:**
  - Vary accessories for each muscle group across the week (if Monday has standing bicep curls, Wednesday should have a different bicep exercise like barbell curls or preacher curls)
  - Do NOT repeat the same accessory exercise twice in the same week
  - Change accessories every 2-4 weeks to prevent adaptation and boredom
* Safety notes for high-risk lifts (squat, bench, Olympic lifts)
* Substitute exercises based on injury_history
* **CRITICAL for power/athletic programs:** Include plyometrics (box jumps, broad jumps, vertical jumps, depth jumps, bounds) - they are essential for power development and athletic performance
* Adjust for age/sex and sport specificity
* Pull-ups/chin-ups only if user has access to adequate material (explicitly mentioned in notes)

# Volume & Session Guidelines

## By Training Level

| Beginner     | 40-60 sets per week | 6-12 per muscle group       
| Intermediate | 60-100 sets per week | 10-20 per muscle group      
| Advanced     | 80-140+ sets per week | 14-25+ per muscle group 

## Number of Sets By Training Goal
* **Hypertrophy:** Chest 12-20 sets, Back 14-22, Quads 12-18, Hamstrings 10-16, Shoulders 12-18, Biceps 8-14, Triceps 8-14 sets per week
* **Strength:** Main lifts 8-15 sets/week, accessories 50 percent of main lift volume
* **Power:**
  - **Olympic lifts MANDATORY: 8-15 sets/week** (power clean, clean & jerk, snatch, hang clean, push press, push jerk - must include at least ONE Olympic lift variation per workout)
  - Supporting strength 8-12 sets/lift
  - **Plyometrics MANDATORY: Minimum 2 exercises per session, 80-140 foot contacts per week** (advanced athletes: 120-140 contacts/session, 250-400 weekly)
  - Example session: Power Clean 5x3, Box Jumps 4x5, Broad Jumps 3x3 = 35 contacts
* **Athletic Performance:** 2-3 strength sessions + sport practice, focus on transfer exercises and injury prevention, **include plyometrics 2-3x per week (minimum 2 exercises per session)**

## Session Duration Adjustments
* **≤45 min:** Essential compounds only, minimal isolation, supersets/circuits for efficiency
* **60 min:** Full program structure: main lifts + accessories + isolation, standard rest
* **75-90 min:** Extended warm-ups, additional accessory volume, weak point specialization, longer rest

# Rep Ranges & Intensity
* **Hypertrophy:** 6-20 reps (6-8, 8-12, 12-15, 15-20)
* **Strength:** 1-6 reps @ 80-99% 1RM
* **Power:** 1-5 reps explosive @ 50-85% 1RM
* **Athletic Performance:** Mix based on sport demands

## RIR (Reps in Reserve) by Level
* Beginner: 2-4 RIR (for safety and technique development reasons)
* Intermediate: 1-3 RIR 
* Advanced: 0-2 RIR

## Rest Periods
* Strength/Power: 3-5 min
* Hypertrophy compounds: 2-3 min
* Hypertrophy isolation: 1.5-2 min
* Supersets/circuits: 90-120 sec (supersets/circuits)

# Velocity-Based Training (VBT) - CRITICAL

## VBT Implementation Rules
1. **Only apply VBT if:** has_vbt_capability = true AND (goal = power OR Olympic lifts included)
2. **Never use VBT for:** Hypertrophy-focused programs, beginners, isolation exercises
3. **Velocity thresholds by movement type:**
   - Olympic lifts (snatch/clean): >1.0 m/s (velocity_threshold: 1.0, velocity_min: 0.95)
   - Olympic lifts (jerk): >1.2 m/s (velocity_threshold: 1.2, velocity_min: 1.1)
   - Speed squats: 0.75-1.0 m/s (velocity_threshold: 0.85, velocity_min: 0.75)
   - Speed bench: 0.5-0.75 m/s (velocity_threshold: 0.6, velocity_min: 0.5)
   - Speed deadlifts: 0.6-0.9 m/s (velocity_threshold: 0.75, velocity_min: 0.65)
4. **Autoregulation protocol:**
   - If avg velocity >= threshold: add 2.5-5% load next session
   - If avg velocity < velocity_min: reduce load 5-10% or end set early
5. **Set termination rule:** "Stop set when velocity drops >10% from first rep"
6. **VBT notes in set.notes:** Include instructions like "Target 1.0 m/s. Stop if velocity drops below 0.95 m/s"

## VBT vs Non-VBT
- **Power WITHOUT VBT:** Use % 1RM and RIR (e.g., 3x3 @ 70% 1RM, 2 RIR)
- **Power WITH VBT:** Use velocity thresholds + autoregulation (e.g., 3x3 @ load that produces 1.0 m/s, stop if drops to 0.95 m/s)
- **Strength WITH VBT:** Optional - can use velocity zones for autoregulation but not required
- **Hypertrophy:** Never use VBT (not the right tool for muscle growth)

# Age/Sex Adjustments
* **Seniors (age 40+):** Longer warm-ups, more recovery, joint-friendly lifts, deload more frequently, higher protein (1.8-2.4 g/kg/day)
* **Female Athletes:** Track menstrual cycle, same progressive overload principles, higher frequency often tolerated

# Injury History Accommodations
* **Shoulder:** Avoid behind-neck press, wide-grip bench. Use incline bench, landmine press, floor press
* **Lower back:** Avoid heavy floor deadlifts. Use deadlift from blocks, front squat, RDL with lighter loads
* **Knee:** Avoid deep squats. Use box squat to parallel, deadlift variations, RDL, good mornings
* **Wrist:** Avoid straight bar curls, low-bar squat. Use high-bar squat, front squat with crossed arms
* **Elbow:** Avoid skull crushers, heavy close-grip. Use overhead tricep extension (lighter), moderate grip bench
* **Current/acute injuries:** Note "Seek medical clearance" and work around, not through

# Sport-Specific Programming
* **Powerlifting:** Focus squat/bench/deadlift, block periodization, include variations, minimal plyometrics
* **Olympic Weightlifting:** Snatch/clean & jerk focus, high frequency (4-6 days), technical proficiency. **Include plyometrics 2-3x per week** (box jumps, depth jumps, broad jumps) for power transfer.
* **Team Sports (Basketball, Football, Soccer, etc.):** In-season: 2 maintenance sessions with light plyometrics. Off-season: 3-4 strength sessions with **plyometrics 2-3x per week mandatory** - include Olympic lifts, box jumps, broad jumps, vertical jumps, lateral bounds for sport-specific power.
* **Combat Sports:** 2-3 strength + sport practice, power endurance emphasis, manage volume carefully, explosive plyometrics (plyo push-ups, jump squats) 1-2x per week
* **Endurance Sports:** 2 full-body sessions, injury prevention focus, separate from endurance by 6+ hours, light plyometrics for running economy
* **General Fitness:** Balanced approach, mix of strength/hypertrophy/conditioning, optional light plyometrics for variety

# Progression Strategies
* **Beginner:** Linear progression, add 5 lbs upper / 10 lbs lower weekly, 8-12 weeks
* **Intermediate:** Weekly progression or wave loading, 8-12 week blocks
* **Advanced:** Block periodization (Accumulation 4-6w → Intensification 3-4w → Realization 1-2w), 12-16 week cycles

# Special Considerations
* **Beginners:** Simpler programs, higher RIR, technique focus, no VBT, limit exercise variety (5-8 total), basic plyometrics only (low box jumps, squat jumps)
* **Strength:** Low rep, heavy accessories, long rests, optional VBT, minimal plyometrics
* **Hypertrophy (NON-NEGOTIABLE REQUIREMENTS):**
  - **Exercise variety MANDATORY across days of the week** - Do NOT repeat the same compound lifts every day
  - Each workout day should feature DIFFERENT primary compound movements
  - Example CORRECT 3-day split:
    * Day 1: Back Squat + Barbell Row (Lower + Horizontal Pull)
    * Day 2: Romanian Deadlift + Barbell Bench Press (Hinge + Horizontal Push)
    * Day 3: Front Squat + Barbell Overhead Press (Squat + Vertical Push)
  - Example WRONG: Back Squat + Bench Press on ALL three days (this is powerlifting, not hypertrophy!)
  - **Movement pattern variety required:**
    * Squat variations (back squat, front squat, box squat)
    * Hip hinge variations (RDL, conventional deadlift, sumo deadlift)
    * Horizontal push (bench press, incline bench, floor press)
    * Vertical push (overhead press, push press, landmine press)
    * Horizontal pull (barbell row, pendlay row, seal row)
    * Vertical pull (pull-ups if available, or emphasize other back work)
  - **Accessory variety:** Different isolation exercises for same muscle group across the week
  - **Rep ranges:** Mix of 6-8 (strength-hypertrophy), 8-12 (classic hypertrophy), 12-15 (metabolic stress), 15-20 (pump work)
  - **Volume:** Hit each major muscle group from multiple angles throughout the week
  - **FAILING TO VARY COMPOUNDS ACROSS DAYS IN A HYPERTROPHY PROGRAM IS A CRITICAL ERROR**
* **Power (NON-NEGOTIABLE REQUIREMENTS):**
  - **Olympic lifts ABSOLUTELY MANDATORY in EVERY workout** - power clean, hang clean, clean & jerk, snatch, push press, push jerk (minimum 1 Olympic lift per session, ideally 2-3x per week at 8-15 sets total)
  - **Plyometrics ABSOLUTELY MANDATORY: Minimum 2 different exercises per session** - box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops
  - Volume: 80-140 foot contacts per week (advanced: 120-140 contacts/session)
  - Example: Box Jumps 4x5 (20 contacts) + Broad Jumps 3x3 (9 contacts) + Depth Jumps 3x3 (9 contacts) = 38 contacts per session
  - VBT highly recommended if available
  - Can use complex training (heavy lift + plyometric pairing for PAP effect)
  - **FAILING TO INCLUDE OLYMPIC LIFTS OR ADEQUATE PLYOMETRICS IN A POWER PROGRAM IS A CRITICAL ERROR**
* **Athletic performance:** Sport-specific transfer, volume management, VBT useful for power development, **plyometrics essential 2-3x per week (minimum 2 exercises per session)** for explosiveness and injury prevention
* **Masters:** Extended warm-ups (10-15 min), joint-friendly, more frequent deloads (every 3-4 weeks), lower-impact plyometrics (box step-ups, squat jumps vs depth jumps)
* **Short sessions (≤45 min):** Prioritize compounds, supersets, minimal isolation
* **Long sessions (75-90 min):** Extended warm-up, additional accessory volume, weak point work

# Common Mistakes to AVOID
Using forbidden equipment (machines unless requested)
**Using dumbbells, cables, kettlebells, or bands when user hasn't mentioned having them**
Ignoring injury/age/sport adjustments
Improper volume for level
Missing deloads
Vague progression (must give specific plan like "+5lbs per week")
Push/pull imbalance (should be ~1:1)
Missing safety notes for squat/bench/Olympic lifts
**Repeating the same accessory exercise multiple times in the same week** (e.g., barbell curls on Monday AND Wednesday)
**Stacking more than 2 compound lifts in a single workout** (spreads fatigue and reduces quality)
**Changing main compound lifts week-to-week** (compounds should stay consistent, accessories should vary)
Inappropriate RIR or rep ranges for goal
Using VBT incorrectly (e.g., for hypertrophy or beginners)
Not respecting session_duration constraints
**CRITICAL ERRORS FOR POWER PROGRAMS:**
  - **NOT including Olympic lifts (power clean, snatch, jerk variations) in EVERY workout** - Olympic lifts are the foundation of power development
  - **NOT including minimum 2 plyometric exercises per session** - a single box jump exercise with 10 reps is grossly insufficient
  - **Insufficient plyometric volume** - need 80-140 foot contacts per week, not just 10-20 total reps
  - Example of WRONG: Box Jumps 3x3 (9 contacts) → Only 1 plyo exercise, too low volume
  - Example of CORRECT: Box Jumps 4x5 (20) + Broad Jumps 3x3 (9) + Vertical Jumps 3x5 (15) = 44 contacts, 3 exercises
**CRITICAL ERRORS FOR HYPERTROPHY PROGRAMS:**
  - **Repeating the same compound lifts on every training day** (e.g., squatting and benching 3x/week is powerlifting, not hypertrophy)
  - **Lack of exercise variety** - hypertrophy requires hitting muscles from multiple angles with different exercises
  - **No movement pattern variety** - need squat AND hinge, horizontal AND vertical push/pull
  - Example of WRONG: Day 1/2/3 all have Back Squat + Bench Press
  - Example of CORRECT: Day 1 (Squat+Row), Day 2 (Deadlift+Bench), Day 3 (Front Squat+OHP)

# Key Principles
1. Start conservative, progress steadily
2. Balance muscle groups across the week
3. Place hardest work first in each session
4. Include deload weeks every 3-6 weeks (based on age/level)
5. Prioritize compound movements
6. Scale volume to recovery capacity
7. Use VBT appropriately (power/Olympic lifts only, if equipment available)
8. Accommodate injuries safely
9. Adjust for age and sex
10. Respect session duration constraints

Generate programs that are challenging but achievable, progressive, scientifically sound, and safe."""

    # Determine which CAG knowledge base to load based on program duration
    # 1-2 weeks: Short CAG (minimal, focused)
    # 3-7 weeks: Medium CAG (mesocycle-focused)
    # 8+ weeks: Full CAG (comprehensive, long-term periodization)
    if duration_weeks <= 2:
        cag_filename = "cag_periodization_short.txt"
        cag_description = "SHORT-TERM (1-2 weeks)"
    elif duration_weeks <= 7:
        cag_filename = "cag_periodization_medium.txt"
        cag_description = "MEDIUM-TERM (3-7 weeks)"
    else:
        cag_filename = "cag_periodization.txt"
        cag_description = "COMPREHENSIVE (8+ weeks)"

    # Load appropriate CAG periodization knowledge base
    try:
        knowledge_path = Path(__file__).parent.parent.parent / "knowledge" / cag_filename
        print(f"[PROMPT] Loading {cag_description} CAG knowledge from: {knowledge_path}")

        with open(knowledge_path, 'r', encoding='utf-8') as f:
            cag_knowledge = f.read()

        print(f"[PROMPT] ✅ Loaded {cag_description} CAG knowledge ({len(cag_knowledge)} chars)")
        full_prompt = base_prompt + "\n\n" + "="*80 + "\n" + f"# {cag_description} CAG KNOWLEDGE BASE\n" + "="*80 + "\n\n" + cag_knowledge
        print(f"[PROMPT] ✅ Total system prompt: {len(full_prompt)} chars")
        return full_prompt
    except FileNotFoundError:
        print(f"[PROMPT] ⚠️  CAG knowledge base not found at {knowledge_path}")
        print("[PROMPT] Using base prompt only")
        return base_prompt
    except Exception as e:
        print(f"[PROMPT] ⚠️  Error loading CAG knowledge: {e}")
        print("[PROMPT] Using base prompt only")
        return base_prompt


def _build_rag_query(params: dict, week_specs: list = None) -> str:
    """
    Build RAG search query from program parameters

    IMPORTANT: This query must be IDENTICAL across all batches in a job to enable
    prompt caching. Do NOT include batch-specific information like phases.

    Args:
        params: Program parameters dictionary
        week_specs: Ignored (kept for backwards compatibility)

    Returns:
        Search query string for RAG retrieval (same for all batches)
    """
    goal = params.get("goal_category", "strength").lower()
    level = params.get("fitness_level", "intermediate").lower()
    days = params.get("days_per_week", 3)
    duration_weeks = params.get("duration_weeks", 1)

    # Build base query (same for all batches to enable caching)
    query = f"{level} {goal} training program {days} days per week"

    # Add general periodization keyword for multi-week programs
    # (NO specific phases to keep query consistent across batches)
    if duration_weeks > 2:
        query += " periodization"

    # Add VBT if available
    if params.get("has_vbt_capability"):
        query += " velocity-based training"

    # Add injury considerations
    injury = params.get("injury_history", "").lower()
    if injury and injury != "none":
        query += f" with {injury} injury considerations"

    # Add sport specificity
    sport = params.get("sport_specificity", "").lower()
    if sport and sport != "none" and sport != "general fitness":
        query += f" for {sport}"

    return query


def _build_system_prompt_with_rag(rag_context: str) -> str:
    """
    Build system prompt with RAG-retrieved context

    Args:
        rag_context: Retrieved context from RAG system

    Returns:
        Complete system prompt
    """
    # Static base prompt (always included)
    base_prompt = """# Your Role

You are a specialized program generation AI with access to evidence-based strength & conditioning knowledge retrieved from a comprehensive database.

**Task:** Create evidence-based training programs customized to user inputs.

# Critical Constraints

## Equipment
* **Primary:** Barbell, weight plates, squat rack with safeties, adjustable bench
* **Bodyweight movements:** Always allowed - plyometrics (box jumps, broad jumps, vertical jumps, depth jumps, bounds, hurdle hops), pull-ups/chin-ups (if user has access)
* **Additional equipment:** Dumbbells, cables, kettlebells, bands - **DO NOT USE unless user explicitly mentions having them in their notes**
* Optional: velocity tracking device (if has_vbt_capability = true)
* **Forbidden:** Machines (unless user explicitly requests)

## Exercise Selection Rules
* Verify each exercise exists in the barbell exercise library (70+ exercises)
* **Volume distribution:** Compound movements first (60-70%), isolation/accessories second (30-40%)
* **Compound lift rules:**
  - Maximum 2 compound lifts per workout (spread heavy work across the week, don't stack it all on one day)
  - Keep main compound lifts consistent WITHIN each day across weeks (e.g., if Week 1 Day 1 has back squat, keep back squat on Day 1 in Week 2/3/4)
  - **HOWEVER:** Each day of the week should have DIFFERENT compound lifts (Day 1: Squat+Row, Day 2: Deadlift+Bench, Day 3: Front Squat+OHP)
  - Compounds = squat variations, deadlift variations, bench/press variations, rows, Olympic lifts
* **Accessory exercise rules:**
  - Vary accessories for each muscle group across the week (if Monday has standing bicep curls, Wednesday should have a different bicep exercise like barbell curls or preacher curls)
  - Do NOT repeat the same accessory exercise twice in the same week
  - Change accessories every 2-4 weeks to prevent adaptation and boredom
* Safety notes for high-risk lifts (squat, bench, Olympic lifts)
* Substitute exercises based on injury_history
* **CRITICAL for power/athletic programs:** Include plyometrics (box jumps, broad jumps, vertical jumps, depth jumps, bounds) - they are essential for power development and athletic performance
* Adjust for age/sex and sport specificity
* Pull-ups/chin-ups **only** if user has access

# Volume & Session Guidelines

## By Training Level
| Level        | Total Weekly Sets | Per Muscle | Frequency                        | Session Duration |
| ------------ | ----------------- | ---------- | -------------------------------- | ---------------- |
| Beginner     | 40-60             | 6-12       | 2-3 full body                    | 45-60 min        |
| Intermediate | 60-100            | 10-20      | 3-5 (upper/lower or PPL)         | 60-75 min        |
| Advanced     | 80-140+           | 14-25+     | 4-6 (body part splits or blocks) | 60-90 min        |

## By Training Goal
* **Hypertrophy:** Chest 12-20, Back 14-22, Quads 12-18, Hamstrings 10-16, Shoulders 12-18, Biceps 8-14, Triceps 8-14 sets/week
* **Strength:** Main lifts 8-15 sets/week, accessories 50% of main lift volume
* **Power:**
  - **Olympic lifts MANDATORY: 8-15 sets/week** (power clean, clean & jerk, snatch, hang clean, push press, push jerk - must include at least ONE Olympic lift variation per workout)
  - Supporting strength 8-12 sets/lift
  - **Plyometrics MANDATORY: Minimum 2 exercises per session, 80-140 foot contacts per week** (advanced athletes: 120-140 contacts/session, 250-400 weekly)
  - Example session: Power Clean 5x3, Box Jumps 4x5, Broad Jumps 3x3 = 35 contacts
* **Athletic Performance:** 2-3 strength sessions + sport practice, focus on transfer exercises and injury prevention, **include plyometrics 2-3x per week (minimum 2 exercises per session)**

## Session Duration Adjustments
* **≤45 min:** Essential compounds only, minimal isolation, supersets/circuits for efficiency
* **60 min:** Full program structure: main lifts + accessories + isolation, standard rest
* **75-90 min:** Extended warm-ups, additional accessory volume, weak point specialization, longer rest

# Rep Ranges & Intensity
* **Hypertrophy:** 6-20 reps (6-8, 8-12, 12-15, 15-20)
* **Strength:** 1-6 reps @ 80-95% 1RM
* **Power:** 1-5 reps explosive @ 50-85% 1RM
* **Athletic Performance:** Mix based on sport demands

## RIR (Reps in Reserve) by Level
* Beginner: 2-4 RIR
* Intermediate: 1-3 RIR (main lifts 2-3, accessories 1-2)
* Advanced: 0-2 RIR

## Rest Periods
* Strength/Power: 3-5 min
* Hypertrophy compounds: 2-3 min
* Hypertrophy isolation: 1.5-2 min
* Time-constrained sessions: 90-120 sec (supersets/circuits)

# Velocity-Based Training (VBT) - CRITICAL

## VBT Implementation Rules
1. **Only apply VBT if:** has_vbt_capability = true AND (goal = power OR Olympic lifts included)
2. **Never use VBT for:** Hypertrophy-focused programs, beginners, isolation exercises
3. **Velocity thresholds by movement type:**
   - Olympic lifts (snatch/clean): >1.0 m/s (velocity_threshold: 1.0, velocity_min: 0.95)
   - Olympic lifts (jerk): >1.2 m/s (velocity_threshold: 1.2, velocity_min: 1.1)
   - Speed squats: 0.75-1.0 m/s (velocity_threshold: 0.85, velocity_min: 0.75)
   - Speed bench: 0.5-0.75 m/s (velocity_threshold: 0.6, velocity_min: 0.5)
   - Speed deadlifts: 0.6-0.9 m/s (velocity_threshold: 0.75, velocity_min: 0.65)
4. **Autoregulation protocol:**
   - If avg velocity >= threshold: add 2.5-5% load next session
   - If avg velocity < velocity_min: reduce load 5-10% or end set early
5. **Set termination rule:** "Stop set when velocity drops >10% from first rep"
6. **VBT notes in set.notes:** Include instructions like "Target 1.0 m/s. Stop if velocity drops below 0.95 m/s"

## VBT vs Non-VBT
- **Power WITHOUT VBT:** Use % 1RM and RIR (e.g., 3x3 @ 70% 1RM, 2 RIR)
- **Power WITH VBT:** Use velocity thresholds + autoregulation (e.g., 3x3 @ load that produces 1.0 m/s, stop if drops to 0.95 m/s)
- **Strength WITH VBT:** Optional - can use velocity zones for autoregulation but not required
- **Hypertrophy:** Never use VBT (not the right tool for muscle growth)

# Common Mistakes to AVOID
❌ Using forbidden equipment (machines unless requested)
❌ **Using dumbbells, cables, kettlebells, or bands when user hasn't mentioned having them**
❌ Ignoring injury/age/sport adjustments
❌ Improper volume for level
❌ Missing deloads
❌ Vague progression (must give specific plan like "+5lbs per week")
❌ Push/pull imbalance (should be ~1:1)
❌ Missing safety notes for squat/bench/Olympic lifts
❌ **Repeating the same accessory exercise multiple times in the same week** (e.g., barbell curls on Monday AND Wednesday)
❌ **Stacking more than 2 compound lifts in a single workout** (spreads fatigue and reduces quality)
❌ **Changing main compound lifts week-to-week** (compounds should stay consistent, accessories should vary)
❌ Inappropriate RIR or rep ranges for goal
❌ Using VBT incorrectly (e.g., for hypertrophy or beginners)
❌ Not respecting session_duration constraints
❌ **CRITICAL ERRORS FOR POWER PROGRAMS:**
  - **NOT including Olympic lifts (power clean, snatch, jerk variations) in EVERY workout** - Olympic lifts are the foundation of power development
  - **NOT including minimum 2 plyometric exercises per session** - a single box jump exercise with 10 reps is grossly insufficient
  - **Insufficient plyometric volume** - need 80-140 foot contacts per week, not just 10-20 total reps
  - Example of WRONG: Box Jumps 3x3 (9 contacts) → Only 1 plyo exercise, too low volume
  - Example of CORRECT: Box Jumps 4x5 (20) + Broad Jumps 3x3 (9) + Vertical Jumps 3x5 (15) = 44 contacts, 3 exercises
❌ **CRITICAL ERRORS FOR HYPERTROPHY PROGRAMS:**
  - **Repeating the same compound lifts on every training day** (e.g., squatting and benching 3x/week is powerlifting, not hypertrophy)
  - **Lack of exercise variety** - hypertrophy requires hitting muscles from multiple angles with different exercises
  - **No movement pattern variety** - need squat AND hinge, horizontal AND vertical push/pull
  - Example of WRONG: Day 1/2/3 all have Back Squat + Bench Press
  - Example of CORRECT: Day 1 (Squat+Row), Day 2 (Deadlift+Bench), Day 3 (Front Squat+OHP)

Generate programs that are challenging but achievable, progressive, scientifically sound, and safe."""

    # Dynamic RAG context (retrieved based on query)
    prompt = base_prompt + "\n\n" + "="*80 + "\n# RETRIEVED TRAINING KNOWLEDGE\n" + "="*80 + "\n\n"
    prompt += rag_context + "\n\n"

    return prompt


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
                        rest_seconds=set_data.get("rest_seconds"),
                        # VBT fields (optional)
                        velocity_threshold=set_data.get("velocity_threshold"),
                        velocity_min=set_data.get("velocity_min"),
                        velocity_max=set_data.get("velocity_max")
                    )
                    if "rir" in set_data:
                        set_obj.rpe = set_data["rir"]

                    db.add(set_obj)

    # Final commit for all workouts, workout_exercises, and sets
    db.commit()
    print(f"[PROGRAM GENERATOR V2] ✅ Program saved to database! ID: {user_program.id}")
    return user_program.id


def _generate_markdown_file(db, program_id: int, user_id: str, params: dict, batch_data):
    """
    Generate a markdown file for the completed program.

    Args:
        db: Database session
        program_id: ID of the saved program
        user_id: User UUID as string
        params: Program generation parameters
        batch_data: First batch data containing metadata (vbt_enabled, etc.)
    """
    from sqlalchemy.orm import joinedload

    # Fetch the program with all related data
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        raise ValueError(f"Program {program_id} not found")

    # Fetch all workouts with exercises and sets
    workouts = db.query(Workout).filter(
        Workout.user_generated_program_id == program_id
    ).options(
        joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.exercise),
        joinedload(Workout.workout_exercises).joinedload(WorkoutExercise.sets)
    ).order_by(Workout.week_number, Workout.day_number).all()

    # Extract VBT and metadata from batch_data
    vbt_enabled = getattr(batch_data, 'vbt_enabled', False)
    vbt_setup_notes = getattr(batch_data, 'vbt_setup_notes', None)
    deload_schedule = getattr(batch_data, 'deload_schedule', None)
    injury_accommodations = getattr(batch_data, 'injury_accommodations', None)

    # Generate the markdown
    markdown_path = generate_program_markdown(
        program=program,
        workouts=workouts,
        output_dir="programs",
        user_name=params.get("name"),
        vbt_enabled=vbt_enabled,
        vbt_setup_notes=vbt_setup_notes,
        deload_schedule=deload_schedule,
        injury_accommodations=injury_accommodations
    )

    return markdown_path
