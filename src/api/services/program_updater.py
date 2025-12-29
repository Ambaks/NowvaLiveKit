"""
Program Updater Service
Uses OpenAI + Cache-Augmented Generation (CAG) to intelligently modify existing programs

Key Features:
- Fetches existing program structure from database
- Uses LLM with CAG to adapt program based on user's change request
- Preserves database IDs where possible (no unnecessary deletions)
- Handles structural changes (days/week, duration, exercises, etc.)
- Provides diff of what changed
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
from typing import Dict, List, Any, Optional, Tuple
import json
import re


async def detect_update_scope(change_request: str, current_program: Dict) -> Dict[str, Any]:
    """
    Use LLM to intelligently detect the scope of a program update request.

    Args:
        change_request: User's change request
        current_program: Current program structure

    Returns:
        {
            "scope": "week" | "workout" | "full_program",
            "affected_weeks": [3, 4] or None,
            "affected_workouts": [(3, 1), (3, 2)] or None,  # (week, day) tuples
            "reason": "Explanation of detection"
        }
    """
    from openai import AsyncOpenAI
    import os

    duration_weeks = current_program.get("metadata", {}).get("duration_weeks", 0)
    days_per_week = current_program.get("metadata", {}).get("days_per_week", 0)

    print(f"[SCOPE] Detecting scope for: '{change_request}'")

    # Get all workouts list for "all workouts" scope
    all_workouts = []
    for week in current_program.get("weeks", []):
        week_num = week.get("week_number")
        for workout in week.get("workouts", []):
            day_num = workout.get("day_number")
            all_workouts.append((week_num, day_num))

    # Use LLM to determine scope
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = f"""You are a workout program analyzer. Analyze change requests and determine the minimal scope needed to implement them.

Program structure:
- {duration_weeks} weeks total
- {days_per_week} days per week
- Total workouts: {len(all_workouts)}

Return JSON with this exact structure:
{{
  "scope": "workout" | "week" | "full_program",
  "affected_weeks": [1, 2, 3] or null,
  "affected_workouts": [[1,1], [1,2]] or null,
  "reason": "Brief explanation"
}}

Scope guidelines:
- "workout": Changes affecting specific workout(s) or all workouts (e.g., "add exercise to every workout", "modify week 2 day 1")
- "week": Changes affecting entire week(s) (e.g., "change week 3", "swap weeks 2 and 4")
- "full_program": Structural changes (e.g., "change from 3 to 5 days", "extend to 16 weeks", "change goal to hypertrophy")

For "add X to every workout" use scope="workout" with affected_workouts={json.dumps(all_workouts)}"""

    user_prompt = f"""Change request: "{change_request}"

Determine the minimal scope needed to implement this change. Return JSON only."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        print(f"[SCOPE] LLM detected: {result['scope']} - {result['reason']}")
        return result

    except Exception as e:
        print(f"[SCOPE ERROR] LLM scope detection failed: {e}, defaulting to full_program")
        return {
            "scope": "full_program",
            "affected_weeks": None,
            "affected_workouts": None,
            "reason": "Scope detection failed, regenerating full program for safety"
        }


async def update_program_background(
    job_id: str,
    user_id: str,
    program_id: int,
    change_request: str,
    user_profile: dict
):
    """
    Background task that updates an existing workout program using CAG.

    Args:
        job_id: UUID of the update job
        user_id: UUID of the user
        program_id: ID of the program to update
        change_request: User's description of what they want to change
        user_profile: User's physical/demographic data for context
    """
    total_start_time = time.time()

    print(f"\n[UPDATE JOB {job_id}] 🔄 Background task STARTED")
    print(f"[UPDATE JOB {job_id}] User ID: {user_id}")
    print(f"[UPDATE JOB {job_id}] Program ID: {program_id}")
    print(f"[UPDATE JOB {job_id}] Change Request: {change_request}")

    db = SessionLocal()

    try:
        print(f"\n{'='*80}")
        print(f"[UPDATE JOB {job_id}] Starting program update with CAG...")
        print(f"{'='*80}\n")

        update_job_status(db, job_id, "in_progress", progress=5)

        # Step 1: Fetch current program (5% → 15%)
        print(f"[UPDATE JOB {job_id}] 📖 Fetching current program from database...")
        current_program = _get_current_program_as_json(db, program_id)

        if not current_program:
            raise ValueError(f"Program {program_id} not found")

        print(f"[UPDATE JOB {job_id}] ✅ Current program loaded: {current_program['metadata']['name']}")
        print(f"[UPDATE JOB {job_id}]    Duration: {current_program['metadata']['duration_weeks']} weeks")
        print(f"[UPDATE JOB {job_id}]    Days/week: {current_program['metadata'].get('days_per_week', 'unknown')}")
        print(f"[UPDATE JOB {job_id}]    Total workouts: {len(current_program['weeks'])} weeks")

        update_job_status(db, job_id, "in_progress", progress=15)

        # Step 2: Load CAG knowledge base (15% → 20%)
        print(f"[UPDATE JOB {job_id}] 📚 Loading CAG knowledge base...")
        cag_knowledge = _load_cag_knowledge()
        print(f"[UPDATE JOB {job_id}] ✅ CAG knowledge loaded ({len(cag_knowledge)} characters)")

        update_job_status(db, job_id, "in_progress", progress=20)

        # Step 2.5: Detect update scope (20% → 25%)
        print(f"[UPDATE JOB {job_id}] 🔍 Detecting update scope...")
        scope_info = await detect_update_scope(change_request, current_program)
        print(f"[UPDATE JOB {job_id}] ✅ Scope detected: {scope_info['scope']}")
        print(f"[UPDATE JOB {job_id}]    Reason: {scope_info['reason']}")

        update_job_status(db, job_id, "in_progress", progress=25)

        # Step 3: Generate updated program via LLM (25% → 70%)
        # Route to appropriate regeneration strategy based on scope
        llm_start = time.time()

        if scope_info["scope"] == "week":
            # Week-level regeneration
            print(f"[UPDATE JOB {job_id}] 🤖 Regenerating specific week(s): {scope_info['affected_weeks']}")
            updated_program = await _regenerate_specific_weeks(
                job_id=job_id,
                current_program=current_program,
                affected_weeks=scope_info["affected_weeks"],
                change_request=change_request,
                user_profile=user_profile,
                cag_knowledge=cag_knowledge
            )

        elif scope_info["scope"] == "workout":
            # Workout-level regeneration
            print(f"[UPDATE JOB {job_id}] 🤖 Regenerating specific workout(s): {scope_info['affected_workouts']}")
            updated_program = await _regenerate_specific_workouts(
                job_id=job_id,
                current_program=current_program,
                affected_workouts=scope_info["affected_workouts"],
                change_request=change_request,
                user_profile=user_profile,
                cag_knowledge=cag_knowledge
            )

        else:
            # Full program regeneration (existing behavior)
            print(f"[UPDATE JOB {job_id}] 🤖 Regenerating full program (structural change)")
            updated_program = await _generate_updated_program(
                job_id=job_id,
                current_program=current_program,
                change_request=change_request,
                user_profile=user_profile,
                cag_knowledge=cag_knowledge
            )

        llm_elapsed = time.time() - llm_start
        print(f"[UPDATE JOB {job_id}] ✅ LLM generation complete in {llm_elapsed:.2f}s")

        update_job_status(db, job_id, "in_progress", progress=70)

        # Step 4: Calculate diff (70% → 75%)
        print(f"[UPDATE JOB {job_id}] 📊 Calculating program changes...")
        diff = _calculate_diff(current_program, updated_program)
        print(f"[UPDATE JOB {job_id}] ✅ Diff calculated:")
        for change in diff:
            print(f"[UPDATE JOB {job_id}]    - {change}")

        update_job_status(db, job_id, "in_progress", progress=75)

        # Step 5: Apply updates to database (75% → 95%)
        print(f"[UPDATE JOB {job_id}] 💾 Applying updates to database...")
        db_start = time.time()

        _apply_program_updates(db, program_id, updated_program)

        db_elapsed = time.time() - db_start
        print(f"[UPDATE JOB {job_id}] ✅ Database updated in {db_elapsed:.2f}s")

        update_job_status(db, job_id, "in_progress", progress=95)

        # Step 6: Mark complete (95% → 100%)
        total_elapsed = time.time() - total_start_time

        # Mark job as completed
        update_job_status(
            db,
            job_id,
            "completed",
            progress=100,
            program_id=str(program_id)
        )

        print(f"\n{'='*80}")
        print(f"[UPDATE JOB {job_id}] 🎉 Program update completed successfully!")
        print(f"[UPDATE JOB {job_id}] Program ID: {program_id}")
        print(f"[UPDATE JOB {job_id}] Total time: {total_elapsed:.2f}s ({total_elapsed/60:.2f} minutes)")
        print(f"[UPDATE JOB {job_id}]   LLM generation: {llm_elapsed:.2f}s")
        print(f"[UPDATE JOB {job_id}]   Database update: {db_elapsed:.2f}s")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n[UPDATE JOB {job_id}] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

        db.rollback()

        try:
            update_job_status(db, job_id, "failed", progress=0, error_message=str(e))
        except Exception as update_error:
            print(f"[UPDATE JOB {job_id}] ⚠️  Failed to update job status: {update_error}")

    finally:
        db.close()


def _get_current_program_as_json(db, program_id: int) -> Optional[Dict]:
    """
    Fetch complete program structure from database and convert to JSON.

    Returns:
        {
            "metadata": {
                "name": "...",
                "description": "...",
                "duration_weeks": 12,
                "goal": "hypertrophy",
                ...
            },
            "weeks": [
                {
                    "week_number": 1,
                    "workouts": [...]
                },
                ...
            ]
        }
    """
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        return None

    # Count days per week from first week
    first_week_workouts = [w for w in program.workouts if w.week_number == 1]
    days_per_week = len(first_week_workouts)

    # Build metadata
    metadata = {
        "name": program.name,
        "description": program.description or "",
        "duration_weeks": program.duration_weeks,
        "days_per_week": days_per_week,
        "created_at": str(program.created_at),
        "updated_at": str(program.updated_at)
    }

    # Build weeks structure
    weeks_dict = {}
    for workout in program.workouts:
        week_num = workout.week_number
        if week_num not in weeks_dict:
            weeks_dict[week_num] = {
                "week_number": week_num,
                "workouts": []
            }

        # Build workout structure
        workout_data = {
            "day_number": workout.day_number,
            "name": workout.name,
            "description": workout.description or "",
            "phase": workout.phase or "",
            "exercises": []
        }

        # Build exercises
        for we in sorted(workout.workout_exercises, key=lambda x: x.order_number):
            exercise_data = {
                "order_number": we.order_number,
                "exercise_name": we.exercise.name if we.exercise else "Unknown",
                "notes": we.notes or "",
                "sets": []
            }

            # Build sets
            for s in sorted(we.sets, key=lambda x: x.set_number):
                set_data = {
                    "set_number": s.set_number,
                    "reps": s.reps,
                    "weight_kg": float(s.weight) if s.weight else None,
                    "intensity_percent": float(s.intensity_percent) if s.intensity_percent else None,
                    "rpe": float(s.rpe) if s.rpe else None,
                    "rest_seconds": s.rest_seconds,
                    "velocity_threshold": float(s.velocity_threshold) if s.velocity_threshold else None
                }
                exercise_data["sets"].append(set_data)

            workout_data["exercises"].append(exercise_data)

        weeks_dict[week_num]["workouts"].append(workout_data)

    # Sort weeks
    weeks = [weeks_dict[k] for k in sorted(weeks_dict.keys())]

    return {
        "metadata": metadata,
        "weeks": weeks
    }


def _load_cag_knowledge() -> str:
    """Load CAG periodization knowledge base from file"""
    try:
        cag_path = Path(__file__).parent.parent.parent / "knowledge" / "cag_periodization.txt"
        with open(cag_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("[UPDATE] ⚠️  WARNING: CAG knowledge base file not found")
        return ""
    except Exception as e:
        print(f"[UPDATE] ⚠️  WARNING: Error loading CAG knowledge base: {e}")
        return ""


def _load_cag_summary() -> str:
    """Load condensed CAG summary for validation"""
    try:
        cag_path = Path(__file__).parent.parent.parent / "knowledge" / "cag_summary.txt"
        with open(cag_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("[VALIDATION] ⚠️  WARNING: CAG summary file not found")
        return ""
    except Exception as e:
        print(f"[VALIDATION] ⚠️  WARNING: Error loading CAG summary: {e}")
        return ""


def _get_program_summary(current_program: Dict) -> Dict[str, Any]:
    """
    Create a lightweight summary of the program for validation.

    Returns essential info without full exercise details, reducing tokens by ~97%.

    Args:
        current_program: Full program structure

    Returns:
        {
            "goal": "strength",
            "duration_weeks": 12,
            "days_per_week": 5,
            "primary_lifts": ["Back Squat", "Deadlift", ...],
            "training_phases": ["Accumulation", "Peak"],
            "avg_volume_per_week": 85,
            "sample_week": {...abbreviated...}
        }
    """
    metadata = current_program.get("metadata", {})
    weeks = current_program.get("weeks", [])

    # Extract primary lifts (main compound movements)
    primary_lift_keywords = ['squat', 'deadlift', 'bench', 'press', 'row', 'clean', 'snatch', 'jerk']
    primary_lifts = set()

    # Scan first few weeks for primary lifts
    for week in weeks[:3]:  # Just look at first 3 weeks
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", [])[:3]:  # First 3 exercises per workout
                exercise_name = exercise.get("exercise_name", "").lower()
                if any(kw in exercise_name for kw in primary_lift_keywords):
                    primary_lifts.add(exercise.get("exercise_name", ""))

    # Extract training phases
    phases = set()
    for week in weeks:
        for workout in week.get("workouts", []):
            phase = workout.get("phase")
            if phase:
                phases.add(phase)

    # Calculate average volume (total sets per week)
    total_sets = 0
    weeks_counted = 0
    for week in weeks[:4]:  # Sample first 4 weeks
        week_sets = 0
        for workout in week.get("workouts", []):
            for exercise in workout.get("exercises", []):
                week_sets += len(exercise.get("sets", []))
        total_sets += week_sets
        weeks_counted += 1

    avg_volume = total_sets // weeks_counted if weeks_counted > 0 else 0

    # Create abbreviated sample week (Week 1)
    sample_week = None
    if len(weeks) > 0:
        first_week = weeks[0]
        sample_week = {
            "week_number": first_week.get("week_number", 1),
            "workouts": []
        }

        for workout in first_week.get("workouts", [])[:3]:  # First 3 workouts
            sample_workout = {
                "day_number": workout.get("day_number"),
                "name": workout.get("name"),
                "phase": workout.get("phase"),
                "exercises": []
            }

            # Just list exercise names, not full sets
            for exercise in workout.get("exercises", [])[:5]:  # First 5 exercises
                sample_workout["exercises"].append({
                    "name": exercise.get("exercise_name"),
                    "set_count": len(exercise.get("sets", []))
                })

            sample_week["workouts"].append(sample_workout)

    summary = {
        "goal": metadata.get("goal", "unknown"),
        "duration_weeks": metadata.get("duration_weeks", 0),
        "days_per_week": metadata.get("days_per_week", 0),
        "primary_lifts": list(primary_lifts),
        "training_phases": list(phases),
        "avg_volume_per_week": avg_volume,
        "sample_week": sample_week
    }

    return summary


async def validate_program_change_with_llm(
    current_program: Dict,
    change_request: str,
    user_profile: dict
) -> Dict[str, Any]:
    """
    Use LLM with CAG knowledge to validate if a program change is risky.

    Args:
        current_program: Current program structure
        change_request: User's requested change
        user_profile: User's physical/demographic data

    Returns:
        {
            "is_risky": bool,
            "warning": str (if risky),
            "alternative": str (if risky)
        }
    """
    print(f"[VALIDATION] Analyzing change request: {change_request}")

    # Load CAG summary for validation rules
    cag_summary = _load_cag_summary()

    # Get lightweight program summary instead of full program (97% token reduction)
    program_summary = _get_program_summary(current_program)

    print(f"[VALIDATION] Using program summary (goal: {program_summary['goal']}, "
          f"{program_summary['days_per_week']} days/week, "
          f"{len(program_summary['primary_lifts'])} primary lifts)")

    # Build validation prompt
    system_prompt = f"""You are an elite strength and conditioning coach analyzing a proposed program change.

Use the evidence-based training principles below to determine if the change is risky or problematic:

{cag_summary}

CURRENT PROGRAM SUMMARY:
- Goal: {program_summary['goal']}
- Frequency: {program_summary['days_per_week']} days/week
- Duration: {program_summary['duration_weeks']} weeks
- Primary Lifts: {', '.join(program_summary['primary_lifts'])}
- Training Phases: {', '.join(program_summary['training_phases'])}
- Avg Volume/Week: {program_summary['avg_volume_per_week']} sets

Sample Week (Week 1):
{json.dumps(program_summary['sample_week'], indent=2)}

USER PROFILE:
- Age: {user_profile.get('age')}, Sex: {user_profile.get('sex')}
- Fitness Level: {user_profile.get('fitness_level', 'intermediate')}

CHANGE REQUEST: "{change_request}"

ANALYSIS TASK:
Determine if this change conflicts with training science or the user's goal.

RISKY CHANGE CATEGORIES:
1. **Exercise Classification Violation**: Replacing primary/compound lifts (squat, deadlift, bench, overhead press, rows) with accessory/isolation exercises (curls, extensions, raises)
2. **Insufficient Frequency**: Reducing below 2 days/week (below minimum effective frequency per CAG)
3. **Extreme Duration Reduction**: Shortening program by >60% (may not allow sufficient adaptation time)
4. **Volume Violation**: Changes that would put user below MEV (Minimum Effective Volume) landmarks

SAFE CHANGES:
- Primary lift → Different primary lift (squat → front squat)
- Moderate frequency adjustments (5→4 or 5→3 days)
- Minor duration changes (+/- 2-4 weeks)
- Rest period adjustments
- Accessory → Accessory swaps

Return ONLY valid JSON in this exact format:
{{
  "is_risky": true or false,
  "warning": "Specific explanation of WHY it's problematic, referencing CAG principles",
  "alternative": "Concrete better option that achieves similar user intent"
}}

If change is SAFE, return:
{{
  "is_risky": false,
  "warning": "",
  "alternative": ""
}}"""

    user_prompt = f"""Analyze this change request: "{change_request}"

Is it risky for a {user_profile.get('fitness_level')} level {program_summary['goal']} program?

Return JSON validation result."""

    try:
        # Call OpenAI with faster, cheaper model for validation
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        print(f"[VALIDATION] 🌐 Calling OpenAI gpt-4o-mini for validation...")

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower temp for more consistent validation
            response_format={"type": "json_object"}
        )

        result_text = response.choices[0].message.content
        validation_result = json.loads(result_text)

        if validation_result.get("is_risky"):
            print(f"[VALIDATION] ⚠️  RISKY CHANGE DETECTED")
            print(f"[VALIDATION]    Warning: {validation_result.get('warning')}")
            print(f"[VALIDATION]    Alternative: {validation_result.get('alternative')}")
        else:
            print(f"[VALIDATION] ✅ Safe change, proceeding")

        return validation_result

    except Exception as e:
        print(f"[VALIDATION] ❌ Error during validation: {e}")
        import traceback
        traceback.print_exc()

        # On error, default to safe (don't block user)
        return {
            "is_risky": False,
            "warning": "",
            "alternative": ""
        }


async def _generate_updated_week(
    job_id: str,
    week_number: int,
    current_week: Dict,
    previous_week: Optional[Dict],
    next_week: Optional[Dict],
    change_request: str,
    program_metadata: Dict,
    user_profile: dict,
    cag_knowledge: str
) -> Dict:
    """
    Regenerate only a specific week, using adjacent weeks for progression context.

    Args:
        job_id: Job ID for logging
        week_number: Week to regenerate
        current_week: Current structure of this week
        previous_week: Week before (for progression context) or None if Week 1
        next_week: Week after (for progression context) or None if last week
        change_request: User's change request
        program_metadata: Program metadata (goal, duration, etc.)
        user_profile: User's physical/demographic data
        cag_knowledge: CAG knowledge base

    Returns:
        Updated week structure
    """
    print(f"[WEEK REGEN {job_id}] Regenerating Week {week_number}")

    # Build context from adjacent weeks
    context_info = f"Regenerating Week {week_number} of {program_metadata.get('duration_weeks')} total weeks"

    if previous_week:
        context_info += f"\n\nPREVIOUS WEEK (Week {previous_week.get('week_number')}):"
        # Abbreviated previous week info
        for workout in previous_week.get("workouts", [])[:2]:  # First 2 workouts
            exercises = [e.get("exercise_name") for e in workout.get("exercises", [])[:3]]
            context_info += f"\n  Day {workout.get('day_number')}: {', '.join(exercises)}"

    if next_week:
        context_info += f"\n\nNEXT WEEK (Week {next_week.get('week_number')}):"
        # Abbreviated next week info
        for workout in next_week.get("workouts", [])[:2]:  # First 2 workouts
            exercises = [e.get("exercise_name") for e in workout.get("exercises", [])[:3]]
            context_info += f"\n  Day {workout.get('day_number')}: {', '.join(exercises)}"

    system_prompt = f"""You are an elite strength and conditioning coach updating Week {week_number} of a training program.

PROGRAM CONTEXT:
- Goal: {program_metadata.get('goal')}
- Frequency: {program_metadata.get('days_per_week')} days/week
- Duration: {program_metadata.get('duration_weeks')} weeks
- Progression Strategy: {program_metadata.get('progression_strategy', 'Progressive overload')}

{context_info}

CHANGE REQUEST: "{change_request}"

CURRENT WEEK {week_number}:
{json.dumps(current_week, indent=2)}

{cag_knowledge}

IMPORTANT INSTRUCTIONS:
1. Apply the requested change to Week {week_number}
2. Maintain logical progression from previous week → this week → next week
3. Preserve program coherence and training principles
4. Only modify what's necessary for the change
5. Ensure the week fits into the overall program structure

Generate ONLY the updated Week {week_number} in JSON format."""

    user_prompt = f"""Update Week {week_number} to accommodate: "{change_request}"

Return the complete updated week in this JSON structure:
{{
  "week_number": {week_number},
  "workouts": [
    {{
      "day_number": 1,
      "name": "Workout Name",
      "description": "...",
      "phase": "Build/Peak/Deload",
      "exercises": [
        {{
          "order_number": 1,
          "exercise_name": "Exercise Name",
          "notes": "...",
          "sets": [
            {{
              "set_number": 1,
              "reps": 5,
              "weight_kg": null,
              "percentage_1rm": 75.0,
              "rir": 3,
              "rest_seconds": 180,
              "tempo": "3010",
              "notes": ""
            }}
          ]
        }}
      ]
    }}
  ]
}}"""

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    result_text = response.choices[0].message.content
    updated_week = json.loads(result_text)

    print(f"[WEEK REGEN {job_id}] ✅ Week {week_number} regenerated")
    return updated_week


async def _generate_updated_workout(
    job_id: str,
    week_number: int,
    day_number: int,
    current_workout: Dict,
    week_context: List[Dict],
    change_request: str,
    program_metadata: Dict,
    user_profile: dict,
    cag_knowledge: str
) -> Dict:
    """
    Regenerate only a specific workout within a week.

    Args:
        job_id: Job ID for logging
        week_number: Week containing this workout
        day_number: Day number of this workout
        current_workout: Current workout structure
        week_context: Other workouts in this week (for context)
        change_request: User's change request
        program_metadata: Program metadata
        user_profile: User's data
        cag_knowledge: CAG knowledge base

    Returns:
        Updated workout structure
    """
    print(f"[WORKOUT REGEN {job_id}] Regenerating Week {week_number}, Day {day_number}")

    # Build context from other workouts in the week
    context_info = f"This is Day {day_number} of Week {week_number}"

    if week_context:
        context_info += "\n\nOTHER WORKOUTS THIS WEEK:"
        for workout in week_context:
            if workout.get("day_number") != day_number:
                exercises = [e.get("exercise_name") for e in workout.get("exercises", [])[:3]]
                context_info += f"\n  Day {workout.get('day_number')}: {', '.join(exercises)}"

    system_prompt = f"""You are an elite strength and conditioning coach updating a single workout.

PROGRAM CONTEXT:
- Goal: {program_metadata.get('goal')}
- Frequency: {program_metadata.get('days_per_week')} days/week
- Week {week_number} of {program_metadata.get('duration_weeks')}

{context_info}

CHANGE REQUEST: "{change_request}"

CURRENT WORKOUT (Week {week_number}, Day {day_number}):
{json.dumps(current_workout, indent=2)}

{cag_knowledge}

IMPORTANT INSTRUCTIONS:
1. Apply the requested change to this specific workout
2. Maintain balance with other workouts in the week
3. Ensure the workout fits the program's goal and training principles
4. Only modify what's necessary

Generate ONLY the updated workout in JSON format."""

    user_prompt = f"""Update this workout to accommodate: "{change_request}"

Return the complete updated workout:
{{
  "day_number": {day_number},
  "name": "Workout Name",
  "description": "...",
  "phase": "Build/Peak/Deload",
  "exercises": [...]
}}"""

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    result_text = response.choices[0].message.content
    updated_workout = json.loads(result_text)

    print(f"[WORKOUT REGEN {job_id}] ✅ Week {week_number}, Day {day_number} regenerated")
    return updated_workout


async def _regenerate_specific_weeks(
    job_id: str,
    current_program: Dict,
    affected_weeks: List[int],
    change_request: str,
    user_profile: dict,
    cag_knowledge: str
) -> Dict:
    """
    Regenerate only specific weeks, preserving the rest of the program.

    Args:
        job_id: Job ID
        current_program: Full current program
        affected_weeks: List of week numbers to regenerate
        change_request: User's change request
        user_profile: User data
        cag_knowledge: CAG knowledge base

    Returns:
        Complete program with only affected weeks regenerated
    """
    updated_program = json.loads(json.dumps(current_program))  # Deep copy
    weeks_list = updated_program["weeks"]
    program_metadata = updated_program["metadata"]
    duration_weeks = program_metadata.get("duration_weeks", 0)

    for week_num in affected_weeks:
        if 1 <= week_num <= duration_weeks:
            print(f"[WEEK REGEN {job_id}] Processing Week {week_num}...")

            # Get current, previous, and next weeks
            current_week = weeks_list[week_num - 1]
            previous_week = weeks_list[week_num - 2] if week_num > 1 else None
            next_week = weeks_list[week_num] if week_num < duration_weeks else None

            # Regenerate this week
            updated_week = await _generate_updated_week(
                job_id=job_id,
                week_number=week_num,
                current_week=current_week,
                previous_week=previous_week,
                next_week=next_week,
                change_request=change_request,
                program_metadata=program_metadata,
                user_profile=user_profile,
                cag_knowledge=cag_knowledge
            )

            # Replace week in program
            weeks_list[week_num - 1] = updated_week

    return updated_program


async def _regenerate_specific_workouts(
    job_id: str,
    current_program: Dict,
    affected_workouts: List[Tuple[int, int]],
    change_request: str,
    user_profile: dict,
    cag_knowledge: str
) -> Dict:
    """
    Regenerate only specific workouts, preserving the rest of the program.

    Args:
        job_id: Job ID
        current_program: Full current program
        affected_workouts: List of (week_number, day_number) tuples
        change_request: User's change request
        user_profile: User data
        cag_knowledge: CAG knowledge base

    Returns:
        Complete program with only affected workouts regenerated
    """
    updated_program = json.loads(json.dumps(current_program))  # Deep copy
    weeks_list = updated_program["weeks"]
    program_metadata = updated_program["metadata"]

    for (week_num, day_num) in affected_workouts:
        print(f"[WORKOUT REGEN {job_id}] Processing Week {week_num}, Day {day_num}...")

        # Find the week
        week = next((w for w in weeks_list if w.get("week_number") == week_num), None)

        if week:
            workouts = week.get("workouts", [])

            # Find the specific workout
            workout = next((w for w in workouts if w.get("day_number") == day_num), None)

            if workout:
                # Get week context (other workouts in this week)
                week_context = workouts.copy()

                # Regenerate this workout
                updated_workout = await _generate_updated_workout(
                    job_id=job_id,
                    week_number=week_num,
                    day_number=day_num,
                    current_workout=workout,
                    week_context=week_context,
                    change_request=change_request,
                    program_metadata=program_metadata,
                    user_profile=user_profile,
                    cag_knowledge=cag_knowledge
                )

                # Replace workout in week
                for i, w in enumerate(workouts):
                    if w.get("day_number") == day_num:
                        workouts[i] = updated_workout
                        break

    return updated_program


async def _generate_updated_program(
    job_id: str,
    current_program: Dict,
    change_request: str,
    user_profile: dict,
    cag_knowledge: str
) -> Dict:
    """
    Use LLM with CAG to generate updated program based on change request.
    """
    # Build system prompt with CAG
    system_prompt = f"""You are an elite strength and conditioning coach updating an existing workout program.

The user has requested the following change to their program:
"{change_request}"

IMPORTANT INSTRUCTIONS:
1. Preserve the existing program structure WHERE POSSIBLE
2. Only modify what's necessary to accommodate the requested change
3. Maintain program coherence (progression, volume, exercise selection)
4. Ensure the updated program is scientifically sound and safe
5. If the change affects overall structure (e.g., 5 days → 3 days), restructure intelligently
6. If the change is minor (e.g., swap one exercise), make minimal modifications

USER PROFILE:
- Age: {user_profile.get('age')}, Sex: {user_profile.get('sex')}
- Height: {user_profile.get('height_cm')} cm, Weight: {user_profile.get('weight_kg')} kg
- Fitness Level: {user_profile.get('fitness_level', 'unknown')}

CURRENT PROGRAM:
{json.dumps(current_program, indent=2)}

{cag_knowledge}

Generate the UPDATED program in the exact same JSON format as the current program.
Include all weeks, workouts, exercises, and sets with complete details.
"""

    # Build user prompt
    user_prompt = f"""Update the program to accommodate this change: "{change_request}"

Return the complete updated program in JSON format with this structure:
{{
    "metadata": {{
        "name": "Program Name",
        "description": "Description",
        "duration_weeks": 12,
        "days_per_week": 3,
        "goal": "hypertrophy/strength/power",
        "progression_strategy": "...",
        "overall_notes": "..."
    }},
    "weeks": [
        {{
            "week_number": 1,
            "workouts": [
                {{
                    "day_number": 1,
                    "name": "Workout Name",
                    "description": "...",
                    "phase": "Build/Peak/Deload/...",
                    "exercises": [
                        {{
                            "order_number": 1,
                            "exercise_name": "Back Squat",
                            "notes": "...",
                            "sets": [
                                {{
                                    "set_number": 1,
                                    "reps": 5,
                                    "weight_kg": null,
                                    "percentage_1rm": 75.0,
                                    "rir": 3,
                                    "rest_seconds": 180,
                                    "tempo": "3010",
                                    "notes": ""
                                }}
                            ]
                        }}
                    ]
                }}
            ]
        }}
    ]
}}"""

    # Call OpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"[UPDATE JOB {job_id}] 🌐 Calling OpenAI GPT-4o for program update...")

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    result_text = response.choices[0].message.content
    updated_program = json.loads(result_text)

    print(f"[UPDATE JOB {job_id}] ✅ LLM returned updated program")

    return updated_program


def _calculate_diff(old_program: Dict, new_program: Dict) -> List[str]:
    """
    Calculate high-level differences between old and new program.
    Returns list of human-readable change descriptions.
    """
    changes = []

    old_meta = old_program["metadata"]
    new_meta = new_program["metadata"]

    # Check metadata changes
    if old_meta["duration_weeks"] != new_meta["duration_weeks"]:
        changes.append(
            f"Duration changed: {old_meta['duration_weeks']} → {new_meta['duration_weeks']} weeks"
        )

    if old_meta.get("days_per_week") != new_meta.get("days_per_week"):
        changes.append(
            f"Training frequency changed: {old_meta.get('days_per_week')} → {new_meta.get('days_per_week')} days/week"
        )

    if old_meta["name"] != new_meta["name"]:
        changes.append(f"Program name updated: '{new_meta['name']}'")

    # Count workouts
    old_workout_count = sum(len(w["workouts"]) for w in old_program["weeks"])
    new_workout_count = sum(len(w["workouts"]) for w in new_program["weeks"])

    if old_workout_count != new_workout_count:
        changes.append(f"Total workouts changed: {old_workout_count} → {new_workout_count}")

    # Sample exercise changes from first week
    if len(old_program["weeks"]) > 0 and len(new_program["weeks"]) > 0:
        old_first_workout = old_program["weeks"][0]["workouts"][0] if old_program["weeks"][0]["workouts"] else None
        new_first_workout = new_program["weeks"][0]["workouts"][0] if new_program["weeks"][0]["workouts"] else None

        if old_first_workout and new_first_workout:
            old_exercises = [e["exercise_name"] for e in old_first_workout["exercises"]]
            new_exercises = [e["exercise_name"] for e in new_first_workout["exercises"]]

            if old_exercises != new_exercises:
                changes.append(f"Exercise selection modified (sample from Week 1 Day 1)")

    if not changes:
        changes.append("Minor adjustments to existing structure")

    return changes


def _apply_program_updates(db, program_id: int, updated_program: Dict):
    """
    Apply the updated program to the database, preserving IDs where possible.

    Strategy:
    1. Update UserGeneratedProgram metadata
    2. Match existing workouts by (week_number, day_number)
    3. Update matched workouts, create new ones, delete removed ones
    4. For each workout, update exercises and sets similarly
    """
    program = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.id == program_id
    ).first()

    if not program:
        raise ValueError(f"Program {program_id} not found")

    # Update metadata
    new_meta = updated_program["metadata"]
    program.name = new_meta["name"]
    program.description = new_meta.get("description", "")
    program.duration_weeks = new_meta["duration_weeks"]

    # Build lookup of existing workouts by (week, day)
    existing_workouts = {}
    for workout in program.workouts:
        key = (workout.week_number, workout.day_number)
        existing_workouts[key] = workout

    # Track which workouts we've processed
    processed_workout_keys = set()

    # Process updated weeks
    for week_data in updated_program["weeks"]:
        week_num = week_data["week_number"]

        for workout_data in week_data["workouts"]:
            day_num = workout_data["day_number"]
            key = (week_num, day_num)
            processed_workout_keys.add(key)

            if key in existing_workouts:
                # Update existing workout
                workout = existing_workouts[key]
                workout.name = workout_data["name"]
                workout.description = workout_data.get("description", "")
                workout.phase = workout_data.get("phase", "")

                # Update exercises for this workout
                _update_workout_exercises(db, workout, workout_data["exercises"])
            else:
                # Create new workout
                new_workout = Workout(
                    user_generated_program_id=program_id,
                    week_number=week_num,
                    day_number=day_num,
                    name=workout_data["name"],
                    description=workout_data.get("description", ""),
                    phase=workout_data.get("phase", "")
                )
                db.add(new_workout)
                db.flush()  # Get ID for workout

                # Add exercises
                _update_workout_exercises(db, new_workout, workout_data["exercises"])

    # Delete workouts that no longer exist
    for key, workout in existing_workouts.items():
        if key not in processed_workout_keys:
            print(f"[UPDATE] Removing workout: Week {key[0]}, Day {key[1]}")
            db.delete(workout)

    db.commit()
    print(f"[UPDATE] ✅ Program {program_id} updated successfully")


def _update_workout_exercises(db, workout: Workout, exercises_data: List[Dict]):
    """
    Update exercises for a workout, preserving IDs where possible.
    """
    # Build lookup of existing exercises by order_number
    existing_exercises = {we.order_number: we for we in workout.workout_exercises}

    # Track processed order numbers
    processed_orders = set()

    for exercise_data in exercises_data:
        order_num = exercise_data["order_number"]
        exercise_name = exercise_data["exercise_name"]
        processed_orders.add(order_num)

        # Find or create exercise in global catalog
        exercise = db.query(Exercise).filter(Exercise.name == exercise_name).first()
        if not exercise:
            exercise = Exercise(name=exercise_name, category="Strength")
            db.add(exercise)
            db.flush()

        if order_num in existing_exercises:
            # Update existing
            we = existing_exercises[order_num]
            we.exercise_id = exercise.id
            we.notes = exercise_data.get("notes", "")

            # Update sets
            _update_exercise_sets(db, we, exercise_data["sets"])
        else:
            # Create new
            we = WorkoutExercise(
                workout_id=workout.id,
                exercise_id=exercise.id,
                order_number=order_num,
                notes=exercise_data.get("notes", "")
            )
            db.add(we)
            db.flush()

            # Add sets
            _update_exercise_sets(db, we, exercise_data["sets"])

    # Delete exercises no longer in workout
    for order_num, we in existing_exercises.items():
        if order_num not in processed_orders:
            db.delete(we)


def _update_exercise_sets(db, workout_exercise: WorkoutExercise, sets_data: List[Dict]):
    """
    Update sets for an exercise, preserving IDs where possible.
    """
    # Build lookup of existing sets by set_number
    existing_sets = {s.set_number: s for s in workout_exercise.sets}

    # Track processed set numbers
    processed_set_nums = set()

    for set_data in sets_data:
        set_num = set_data["set_number"]
        processed_set_nums.add(set_num)

        if set_num in existing_sets:
            # Update existing
            s = existing_sets[set_num]
            s.reps = set_data.get("reps")
            s.weight = set_data.get("weight_kg")  # Map weight_kg -> weight
            s.intensity_percent = set_data.get("intensity_percent")
            s.rpe = set_data.get("rpe")
            s.rest_seconds = set_data.get("rest_seconds")
            s.velocity_threshold = set_data.get("velocity_threshold")
        else:
            # Create new
            s = Set(
                workout_exercise_id=workout_exercise.id,
                set_number=set_num,
                reps=set_data.get("reps"),
                weight=set_data.get("weight_kg"),  # Map weight_kg -> weight
                intensity_percent=set_data.get("intensity_percent"),
                rpe=set_data.get("rpe"),
                rest_seconds=set_data.get("rest_seconds"),
                velocity_threshold=set_data.get("velocity_threshold")
            )
            db.add(s)

    # Delete sets no longer in exercise
    for set_num, s in existing_sets.items():
        if set_num not in processed_set_nums:
            db.delete(s)
