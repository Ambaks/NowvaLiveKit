"""
Database utility functions for program management
"""
from sqlalchemy.orm import Session
from .models import UserGeneratedProgram, PartnerProgram
from typing import List, Tuple


def get_user_programs(db: Session, user_id: str) -> Tuple[List[UserGeneratedProgram], List[PartnerProgram]]:
    """
    Get all programs for a user (both user-generated and partner programs)

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        Tuple of (user_generated_programs, partner_programs)
    """
    user_generated = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.user_id == user_id
    ).all()

    partner = db.query(PartnerProgram).filter(
        PartnerProgram.user_id == user_id
    ).all()

    return user_generated, partner


def has_any_programs(db: Session, user_id: str) -> bool:
    """
    Check if a user has any programs (user-generated or partner)

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        True if user has at least one program, False otherwise
    """
    user_generated_count = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.user_id == user_id
    ).count()

    partner_count = db.query(PartnerProgram).filter(
        PartnerProgram.user_id == user_id
    ).count()

    return (user_generated_count + partner_count) > 0


def create_user_generated_program(
    db: Session,
    user_id: str,
    name: str,
    description: str = None,
    duration_weeks: int = None
) -> UserGeneratedProgram:
    """
    Create a new user-generated program

    Args:
        db: Database session
        user_id: User's UUID as string
        name: Program name
        description: Optional program description
        duration_weeks: Optional program duration in weeks

    Returns:
        Created UserGeneratedProgram instance
    """
    program = UserGeneratedProgram(
        user_id=user_id,
        name=name,
        description=description,
        duration_weeks=duration_weeks
    )

    db.add(program)
    db.commit()
    db.refresh(program)

    return program


def count_user_programs(db: Session, user_id: str) -> int:
    """
    Count total number of programs for a user.

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        Total count of programs (user-generated + partner)
    """
    user_generated_count = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.user_id == user_id
    ).count()

    partner_count = db.query(PartnerProgram).filter(
        PartnerProgram.user_id == user_id
    ).count()

    return user_generated_count + partner_count


def get_program_with_full_structure(db: Session, program_id: int) -> UserGeneratedProgram:
    """
    Get a program with all related data eagerly loaded.

    Args:
        db: Database session
        program_id: Program ID

    Returns:
        UserGeneratedProgram with workouts, exercises, and sets loaded
    """
    from sqlalchemy.orm import joinedload

    program = db.query(UserGeneratedProgram).options(
        joinedload(UserGeneratedProgram.workouts)
        .joinedload('workout_exercises')
        .joinedload('exercise')
    ).options(
        joinedload(UserGeneratedProgram.workouts)
        .joinedload('workout_exercises')
        .joinedload('sets')
    ).filter(UserGeneratedProgram.id == program_id).first()

    return program


def get_program_summary_list(db: Session, user_id: str) -> List[dict]:
    """
    Get list of programs with basic info for selection.

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        List of dicts with program summaries: [{id, name, description, duration_weeks, type}, ...]
    """
    summaries = []

    # User-generated programs
    user_generated = db.query(UserGeneratedProgram).filter(
        UserGeneratedProgram.user_id == user_id
    ).all()

    for program in user_generated:
        summaries.append({
            "id": program.id,
            "name": program.name,
            "description": program.description or "",
            "duration_weeks": program.duration_weeks,
            "type": "user_generated",
            "created_at": str(program.created_at)
        })

    # Partner programs
    partner = db.query(PartnerProgram).filter(
        PartnerProgram.user_id == user_id
    ).all()

    for program in partner:
        summaries.append({
            "id": program.id,
            "name": program.name,
            "description": program.description or "",
            "duration_weeks": program.duration_weeks,
            "type": "partner",
            "partner_name": program.partner_name,
            "created_at": str(program.created_at)
        })

    # Sort by most recent first
    summaries.sort(key=lambda x: x["created_at"], reverse=True)

    return summaries
