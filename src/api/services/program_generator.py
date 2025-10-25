"""
Program Generator Service
Background task that generates workout programs using GPT-5
"""
from db.database import SessionLocal
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set
from .job_manager import update_job_status
import asyncio
import json
from openai import AsyncOpenAI
import os
from pathlib import Path


async def generate_program_background(job_id: str, user_id: str, params: dict):
    """
    Background task that generates a workout program.
    Updates job status as it progresses.

    Args:
        job_id: UUID of the generation job
        user_id: UUID of the user
        params: Dictionary containing all program parameters
    """
    db = SessionLocal()

    try:
        # Update status to in_progress
        update_job_status(db, job_id, "in_progress", progress=10)
        print(f"\n{'='*80}")
        print(f"[JOB {job_id}] Starting program generation...")
        print(f"{'='*80}\n")

        # Load knowledge base
        update_job_status(db, job_id, "in_progress", progress=20)
        system_prompt = _get_system_prompt()
        print(f"[JOB {job_id}] System prompt loaded ({len(system_prompt)} chars)")

        # Create user prompt
        update_job_status(db, job_id, "in_progress", progress=30)
        user_prompt = _create_user_prompt(params)
        print(f"[JOB {job_id}] User prompt created ({len(user_prompt)} chars)")

        # Call GPT-5
        update_job_status(db, job_id, "in_progress", progress=40)
        print(f"[JOB {job_id}] 🚀 Calling GPT-5 API for program generation...")

        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("PROGRAM_CREATION_MODEL", "gpt-5-mini")

        # GPT-5 doesn't support custom temperature
        request_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "timeout": 300.0,  # 5 minutes max
            "max_completion_tokens": 16000,  # Limit response size to prevent truncation/corruption
        }

        # Only add temperature if not GPT-5
        if not model.startswith("gpt-5"):
            request_params["temperature"] = 0.7

        import time
        start_time = time.time()

        # Retry logic for API calls
        max_retries = 3
        retry_count = 0
        response = None
        last_error = None

        while retry_count < max_retries:
            try:
                response = await client.chat.completions.create(**request_params)
                break  # Success, exit retry loop
            except Exception as api_error:
                retry_count += 1
                last_error = api_error
                print(f"[JOB {job_id}] ⚠️  API call failed (attempt {retry_count}/{max_retries}): {api_error}")

                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff: 2s, 4s, 8s
                    print(f"[JOB {job_id}] Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[JOB {job_id}] ❌ All retry attempts failed")
                    raise last_error

        elapsed_time = time.time() - start_time
        print(f"[JOB {job_id}] ✅ API call completed in {elapsed_time:.2f} seconds!")

        # Parse response
        update_job_status(db, job_id, "in_progress", progress=70)
        program_json = response.choices[0].message.content

        # Try to parse JSON - handle common issues
        try:
            program_data = json.loads(program_json)
            print(f"[JOB {job_id}] ✅ JSON parsed successfully ({len(program_json)} chars)")
        except json.JSONDecodeError as e:
            print(f"[JOB {job_id}] ⚠️  JSON parse error, attempting to fix...")
            print(f"[JOB {job_id}] ❌ ERROR: {e.msg} at line {e.lineno} column {e.colno} (char {e.pos})")

            # Save problematic JSON for debugging
            error_file = f"/tmp/program_json_error_{job_id}.json"
            with open(error_file, 'w') as f:
                f.write(program_json)
            print(f"[JOB {job_id}] 📁 Saved problematic JSON to {error_file}")

            # Show context around error
            if e.pos and e.pos < len(program_json):
                start = max(0, e.pos - 200)
                end = min(len(program_json), e.pos + 200)
                error_context = program_json[start:end]
                print(f"[JOB {job_id}] Context around error:")
                print(f"[JOB {job_id}] ...{error_context}...")
                print(f"[JOB {job_id}] " + " " * (min(200, e.pos - start) + 3) + "^--- ERROR HERE")

            # Try to extract JSON from markdown code blocks if present
            original_json = program_json
            if "```json" in program_json:
                program_json = program_json.split("```json")[1].split("```")[0].strip()
            elif "```" in program_json:
                program_json = program_json.split("```")[1].split("```")[0].strip()

            # Try multiple repair strategies
            import re

            # Strategy 1: Remove trailing commas
            program_json = re.sub(r',(\s*[}\]])', r'\1', program_json)

            # Strategy 2: Remove comments
            program_json = re.sub(r'//.*?$', '', program_json, flags=re.MULTILINE)
            program_json = re.sub(r'/\*.*?\*/', '', program_json, flags=re.DOTALL)

            # Strategy 3: Fix common quote issues
            # Replace smart quotes with regular quotes
            program_json = program_json.replace('"', '"').replace('"', '"')
            program_json = program_json.replace(''', "'").replace(''', "'")

            try:
                program_data = json.loads(program_json)
                print(f"[JOB {job_id}] ✅ JSON fixed and parsed successfully")
            except json.JSONDecodeError as e2:
                print(f"[JOB {job_id}] ❌ Could not auto-fix JSON")
                print(f"[JOB {job_id}] Original error: {e}")
                print(f"[JOB {job_id}] After fix attempt: {e2}")
                print(f"[JOB {job_id}] Context around error position:")
                start = max(0, e.pos - 100)
                end = min(len(original_json), e.pos + 100)
                print(f"[JOB {job_id}] ...{original_json[start:end]}...")
                raise e  # Raise original error for better debugging

        # Save to database
        update_job_status(db, job_id, "in_progress", progress=85)
        print(f"[JOB {job_id}] 💾 Saving program to database...")
        program_id = _save_program_to_db(db, user_id, program_data)

        # Mark complete
        update_job_status(db, job_id, "completed", progress=100, program_id=str(program_id))
        print(f"\n{'='*80}")
        print(f"[JOB {job_id}] 🎉 Program generation completed!")
        print(f"[JOB {job_id}] Program ID: {program_id}")
        print(f"{'='*80}\n")

    except json.JSONDecodeError as e:
        print(f"\n[JOB {job_id}] ❌ JSON DECODE ERROR: {e}")
        update_job_status(db, job_id, "failed", progress=0, error_message=f"JSON parsing failed: {str(e)}")

    except Exception as e:
        print(f"\n[JOB {job_id}] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        update_job_status(db, job_id, "failed", progress=0, error_message=str(e))

    finally:
        db.close()


def _get_system_prompt() -> str:
    """Load system prompt with knowledge base"""

    # Base coaching expertise and guidelines
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

**Barbell Exercise Library:**
- Lower: Back squat, front squat, deadlift (conventional/sumo), RDL, Bulgarian split squat, hip thrust
- Upper Push: Bench press (flat/incline), overhead press, push press, close-grip bench
- Upper Pull: Barbell row (bent-over/pendlay), pull-ups (weighted)
- Olympic: Clean, snatch, push jerk (for power focus)

**Progression Strategies:**
- Linear Progression: Add weight each week (beginner)
- Double Progression: Increase reps, then weight (all levels)
- Wave Loading: Vary intensity across weeks (intermediate+)
- Block Periodization: Phase-based training (advanced)

**Program Structure by Frequency:**
- 2-3 days: Full body each session
- 4 days: Upper/Lower split
- 5-6 days: Push/Pull/Legs or Upper/Lower/Upper/Lower

**Key Principles:**
1. Start conservative, progress steadily
2. Balance muscle groups across the week
3. Place hardest work first in each session
4. Include deload weeks every 4-8 weeks
5. Prioritize compound movements
6. Scale volume to recovery capacity

Generate programs that are challenging but achievable, progressive, and scientifically sound. Always return valid JSON in the exact format specified."""

    # Load CAG periodization knowledge base SUMMARY from external file
    try:
        # Get path relative to this file - using SUMMARY for token efficiency
        knowledge_path = Path(__file__).parent.parent.parent / "knowledge" / "cag_summary.txt"
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            cag_knowledge = f.read()

        print(f"[PROGRAM GENERATOR] Loaded CAG knowledge base summary ({len(cag_knowledge)} characters)")

        # Combine base prompt with CAG knowledge
        full_prompt = base_prompt + "\n\n" + "="*80 + "\n" + cag_knowledge
        return full_prompt

    except FileNotFoundError:
        print("[PROGRAM GENERATOR] ⚠️  WARNING: CAG knowledge base summary file not found, using base prompt only")
        return base_prompt
    except Exception as e:
        print(f"[PROGRAM GENERATOR] ⚠️  WARNING: Error loading CAG knowledge base: {e}")
        return base_prompt


def _create_user_prompt(params: dict) -> str:
    """Create user prompt from parameters"""
    name = params.get("name", "User")
    height_cm = params.get("height_cm")
    weight_kg = params.get("weight_kg")
    goal_category = params.get("goal_category")
    goal_raw = params.get("goal_raw")
    fitness_level = params.get("fitness_level")
    duration_weeks = params.get("duration_weeks")
    days_per_week = params.get("days_per_week")

    user_prompt = f"""Create a personalized barbell-only weightlifting program for the following user:

**User Profile:**
- Height: {height_cm} cm
- Weight: {weight_kg} kg
- Goal Category: {goal_category}
- Goal Description: "{goal_raw}"
- Fitness Level: {fitness_level}
- Program Duration: {duration_weeks} weeks
- Training Frequency: {days_per_week} days per week

**Requirements:**
1. Create a COMPLETE {duration_weeks}-week program with ALL {days_per_week} training days for EVERY week
2. Use ONLY barbell exercises (and bodyweight for pull-ups/dips if needed)
3. Include specific intensity percentages (% of 1RM) for each set that progress week-by-week
4. Optimize volume per muscle group based on {goal_category} focus
5. Set appropriate RIR based on {fitness_level} level (beginner: 2-3 RIR, intermediate: 1-2 RIR, advanced: 0-1 RIR)
6. Show progressive loading: Week 1 might be 75% 1RM, Week 2 might be 77.5%, etc.
7. Include deload weeks with reduced intensity/volume
8. Structure each day logically (main lifts → accessories)
9. Set appropriate rest periods based on goal

**CRITICAL: You MUST generate ALL {duration_weeks} weeks × {days_per_week} days = {duration_weeks * days_per_week} total workouts.**

**Output Format:**
Return a valid JSON object with this EXACT structure:

{{
  "program_name": "Descriptive program name",
  "description": "Brief program description",
  "duration_weeks": {duration_weeks},
  "goal": "{goal_category}",
  "progression_strategy": "Detailed explanation of how intensity/volume progresses week-to-week",
  "notes": "Important notes about deloads, form, recovery, warm-ups, etc.",
  "weeks": [
    {{
      "week_number": 1,
      "phase": "Build/Deload/Peak/Taper",
      "workouts": [
        {{
          "day_number": 1,
          "name": "Workout day name (e.g., Upper Push, Lower Power)",
          "description": "Brief description of focus",
          "exercises": [
            {{
              "exercise_name": "Exact exercise name (e.g., Barbell Bench Press)",
              "category": "Strength",
              "muscle_group": "Primary muscle group",
              "order": 1,
              "sets": [
                {{
                  "set_number": 1,
                  "reps": 5,
                  "intensity_percent": 75.0,
                  "weight": null,
                  "rpe": null,
                  "rir": 2,
                  "rest_seconds": 180,
                  "notes": "Optional notes"
                }}
              ]
            }}
          ]
        }},
        {{
          "day_number": 2,
          "name": "...",
          "exercises": [...]
        }},
        {{
          "day_number": 3,
          "name": "...",
          "exercises": [...]
        }},
        {{
          "day_number": 4,
          "name": "...",
          "exercises": [...]
        }}
      ]
    }},
    {{
      "week_number": 2,
      "phase": "Build",
      "workouts": [
        // ALL {days_per_week} days for Week 2 with slightly higher intensity
      ]
    }}
    // Continue for ALL {duration_weeks} weeks
  ]
}}

**IMPORTANT REMINDERS:**
- Include intensity_percent (% of 1RM) for EVERY set
- Generate ALL {duration_weeks} weeks (not just a template)
- Each week should have ALL {days_per_week} workout days
- Show progressive overload: intensity should increase week-to-week
- Include deload weeks (typically every 4th week with ~60-70% intensity)

**CRITICAL - JSON FORMAT REQUIREMENTS:**
- Return ONLY valid JSON - no markdown, no code blocks, no explanatory text
- NO trailing commas before closing braces }} or brackets ]
- ALL property names MUST be in double quotes "property_name"
- ALL string values MUST use double quotes, not single quotes
- NO JavaScript-style comments (//) or /* */ anywhere
- NO line breaks within string values (use \\n if needed)
- NO unescaped quotes within strings
- Ensure all brackets and braces are properly matched and closed
- Test that your JSON is valid before returning

**VALIDATION CHECKLIST:**
✓ Every {{ has a matching }}
✓ Every [ has a matching ]
✓ No trailing commas
✓ All strings use double quotes
✓ No comments anywhere

Generate the COMPLETE program now with all {duration_weeks} weeks. Return ONLY the raw JSON object - nothing else."""

    return user_prompt


def _save_program_to_db(db, user_id: str, program_data: dict) -> str:
    """
    Save program to database and return program_id

    Args:
        db: Database session
        user_id: User UUID as string
        program_data: Program JSON data from GPT-5

    Returns:
        Program ID as string
    """
    # Create UserGeneratedProgram
    user_program = UserGeneratedProgram(
        user_id=user_id,
        name=program_data.get("program_name"),
        description=program_data.get("description"),
        duration_weeks=program_data.get("duration_weeks"),
        is_public=False
    )
    db.add(user_program)
    db.flush()  # Get the ID

    # Create each week and its workouts
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
            db.flush()

            # Create exercises for this workout
            for exercise_data in workout_data.get("exercises", []):
                # Check if exercise exists, if not create it
                exercise_name = exercise_data.get("exercise_name")
                exercise = db.query(Exercise).filter(Exercise.name == exercise_name).first()

                if not exercise:
                    # Create new exercise
                    exercise = Exercise(
                        name=exercise_name,
                        category=exercise_data.get("category"),
                        muscle_group=exercise_data.get("muscle_group"),
                        description=f"Barbell exercise: {exercise_name}"
                    )
                    db.add(exercise)
                    db.flush()
                    print(f"[PROGRAM GENERATOR] Created new exercise: {exercise_name}")

                # Create workout_exercise (join table entry)
                workout_exercise = WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=exercise.id,
                    order_number=exercise_data.get("order"),
                    notes=exercise_data.get("notes", "")
                )
                db.add(workout_exercise)
                db.flush()

                # Create sets for this exercise
                for set_data in exercise_data.get("sets", []):
                    set_obj = Set(
                        workout_exercise_id=workout_exercise.id,
                        set_number=set_data.get("set_number"),
                        reps=set_data.get("reps"),
                        weight=set_data.get("weight"),  # Will be None initially
                        intensity_percent=set_data.get("intensity_percent"),  # % of 1RM
                        rpe=set_data.get("rpe"),
                        rest_seconds=set_data.get("rest_seconds")
                    )
                    # Store RIR in RPE column temporarily
                    if "rir" in set_data:
                        set_obj.rpe = set_data["rir"]

                    db.add(set_obj)

    db.commit()
    print(f"[PROGRAM GENERATOR] ✅ Program saved to database! ID: {user_program.id}")
    return user_program.id
