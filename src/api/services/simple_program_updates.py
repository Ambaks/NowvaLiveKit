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
from db.models import UserGeneratedProgram
import re
from typing import Optional, Tuple, Dict, Any


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

    else:
        return (False, f"Unknown update type: {update_type}")
