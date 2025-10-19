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
