"""
Simple Program Updates
Handles basic field updates without requiring LLM calls for efficiency.

Use this for:
- Title/name changes
- Description updates
- Simple exercise swaps
- Single parameter changes (rest periods, tempo, etc.)

Use program_updater.py (LLM) for:
- Structural changes (days/week, duration)
- Multiple exercise changes
- Goal changes
- Complex requests requiring program redesign
"""
from sqlalchemy.orm import Session
from db.models import UserGeneratedProgram, Workout, WorkoutExercise, Exercise, Set
import re
from typing import Optional, Tuple, Dict, Any


def is_safe_simple_change(change_request: str) -> bool:
    """
    Check if change is a safe simple update (title or description only).

    All other changes (exercise swaps, rest periods, frequency, etc.) should
    go through LLM validation to ensure they're safe for the user's goals.

    Returns:
        True if change is title/description (safe, instant apply)
        False otherwise (needs LLM validation)
    """
    request_lower = change_request.lower().strip()

    # Pattern 1: Title/Name changes
    title_patterns = [
        r"change (?:the )?(?:name|title) to (.+)",
        r"rename (?:it )?to (.+)",
        r"call it (.+)",
    ]
    for pattern in title_patterns:
        if re.search(pattern, request_lower):
            return True

    # Pattern 2: Description changes
    desc_patterns = [
        r"change (?:the )?description to (.+)",
        r"update (?:the )?description to (.+)",
    ]
    for pattern in desc_patterns:
        if re.search(pattern, request_lower):
            return True

    # All other changes need LLM validation
    return False


def detect_simple_update(change_request: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Detect if the change request is a simple safe update (title/description only).

    All training-related changes now go through LLM validation.

    Returns:
        (update_type, params) where update_type is one of:
        - "title_change": Change program name
        - "description_change": Change program description
        - "requires_llm": Everything else (exercise swaps, frequency, rest, etc.)

    Examples:
        "change the name to Summer Shred 2.0" → ("title_change", {"new_name": "Summer Shred 2.0"})
        "replace bench press with incline bench" → ("requires_llm", None)  # Now needs validation
        "I can only train 3 days now" → ("requires_llm", None)
    """
    request_lower = change_request.lower().strip()

    # Pattern 1: Title/Name changes (SAFE)
    title_patterns = [
        r"change (?:the )?(?:name|title) to (.+)",
        r"rename (?:it )?to (.+)",
        r"call it (.+)",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, request_lower)
        if match:
            new_name = match.group(1).strip().strip('"\'')
            return ("title_change", {"new_name": new_name})

    # Pattern 2: Description changes (SAFE)
    desc_patterns = [
        r"change (?:the )?description to (.+)",
        r"update (?:the )?description to (.+)",
    ]
    for pattern in desc_patterns:
        match = re.search(pattern, request_lower)
        if match:
            new_desc = match.group(1).strip().strip('"\'')
            return ("description_change", {"new_description": new_desc})

    # Everything else requires LLM validation
    # This includes: exercise swaps, rest periods, frequency changes, duration changes, etc.
    return ("requires_llm", None)


def apply_title_change(db: Session, program_id: int, new_name: str) -> bool:
    """
    Apply a simple title change.

    Returns:
        True if successful, False otherwise
    """
    try:
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            return False

        program.name = new_name
        db.commit()

        print(f"[SIMPLE UPDATE] Changed program name to: {new_name}")
        return True

    except Exception as e:
        print(f"[SIMPLE UPDATE] Error changing title: {e}")
        db.rollback()
        return False


def apply_description_change(db: Session, program_id: int, new_description: str) -> bool:
    """
    Apply a simple description change.

    Returns:
        True if successful, False otherwise
    """
    try:
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            return False

        program.description = new_description
        db.commit()

        print(f"[SIMPLE UPDATE] Changed program description to: {new_description}")
        return True

    except Exception as e:
        print(f"[SIMPLE UPDATE] Error changing description: {e}")
        db.rollback()
        return False


def apply_exercise_swap(
    db: Session,
    program_id: int,
    old_exercise_name: str,
    new_exercise_name: str
) -> Tuple[bool, int]:
    """
    Swap one exercise for another across the entire program.

    Args:
        db: Database session
        program_id: Program ID
        old_exercise_name: Name of exercise to replace (fuzzy match)
        new_exercise_name: Name of new exercise

    Returns:
        (success, count) where count is number of instances swapped
    """
    try:
        # Find or create new exercise in catalog
        new_exercise = db.query(Exercise).filter(
            Exercise.name.ilike(f"%{new_exercise_name}%")
        ).first()

        if not new_exercise:
            # Create new exercise
            new_exercise = Exercise(
                name=new_exercise_name.title(),
                category="Strength"
            )
            db.add(new_exercise)
            db.flush()

        # Find old exercise
        old_exercise = db.query(Exercise).filter(
            Exercise.name.ilike(f"%{old_exercise_name}%")
        ).first()

        if not old_exercise:
            print(f"[SIMPLE UPDATE] Could not find exercise matching: {old_exercise_name}")
            return (False, 0)

        # Find all workout_exercises using the old exercise in this program
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            return (False, 0)

        swap_count = 0
        for workout in program.workouts:
            for we in workout.workout_exercises:
                if we.exercise_id == old_exercise.id:
                    we.exercise_id = new_exercise.id
                    swap_count += 1

        db.commit()

        print(f"[SIMPLE UPDATE] Swapped {old_exercise.name} → {new_exercise.name} ({swap_count} instances)")
        return (True, swap_count)

    except Exception as e:
        print(f"[SIMPLE UPDATE] Error swapping exercise: {e}")
        db.rollback()
        return (False, 0)


def apply_rest_period_change(
    db: Session,
    program_id: int,
    rest_seconds: int,
    exercise_name: Optional[str] = None
) -> Tuple[bool, int]:
    """
    Change rest periods across the program.

    Args:
        db: Database session
        program_id: Program ID
        rest_seconds: New rest period in seconds
        exercise_name: Optional - only change for specific exercise

    Returns:
        (success, count) where count is number of sets updated
    """
    try:
        program = db.query(UserGeneratedProgram).filter(
            UserGeneratedProgram.id == program_id
        ).first()

        if not program:
            return (False, 0)

        update_count = 0

        if exercise_name:
            # Find the exercise
            exercise = db.query(Exercise).filter(
                Exercise.name.ilike(f"%{exercise_name}%")
            ).first()

            if not exercise:
                return (False, 0)

            # Update only for this exercise
            for workout in program.workouts:
                for we in workout.workout_exercises:
                    if we.exercise_id == exercise.id:
                        for s in we.sets:
                            s.rest_seconds = rest_seconds
                            update_count += 1
        else:
            # Update all sets in the program
            for workout in program.workouts:
                for we in workout.workout_exercises:
                    for s in we.sets:
                        s.rest_seconds = rest_seconds
                        update_count += 1

        db.commit()

        print(f"[SIMPLE UPDATE] Changed rest periods to {rest_seconds}s ({update_count} sets)")
        return (True, update_count)

    except Exception as e:
        print(f"[SIMPLE UPDATE] Error changing rest periods: {e}")
        db.rollback()
        return (False, 0)


def handle_simple_update(
    db: Session,
    program_id: int,
    change_request: str
) -> Tuple[bool, str]:
    """
    Main entry point for simple updates.

    Returns:
        (success, message) where message describes what happened
    """
    update_type, params = detect_simple_update(change_request)

    if update_type == "requires_llm":
        return (False, "This change requires LLM processing")

    elif update_type == "title_change":
        success = apply_title_change(db, program_id, params["new_name"])
        if success:
            return (True, f"Program name changed to '{params['new_name']}'")
        else:
            return (False, "Failed to change program name")

    elif update_type == "description_change":
        success = apply_description_change(db, program_id, params["new_description"])
        if success:
            return (True, f"Program description updated")
        else:
            return (False, "Failed to change description")

    elif update_type == "exercise_swap":
        success, count = apply_exercise_swap(
            db,
            program_id,
            params["old_exercise"],
            params["new_exercise"]
        )
        if success:
            return (True, f"Swapped {params['old_exercise']} → {params['new_exercise']} ({count} instances)")
        else:
            return (False, f"Could not find exercise: {params['old_exercise']}")

    elif update_type == "rest_period_change":
        success, count = apply_rest_period_change(
            db,
            program_id,
            params["rest_seconds"]
        )
        if success:
            return (True, f"Changed rest periods to {params['rest_seconds']}s ({count} sets)")
        else:
            return (False, "Failed to change rest periods")

    else:
        return (False, f"Unknown update type: {update_type}")
