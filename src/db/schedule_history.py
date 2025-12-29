"""
Schedule change history tracking and undo functionality.

Provides:
- Snapshot-based change history with JSONB storage
- Undo capability for schedule modifications
- Automatic history cleanup (max 50 entries per user)
- 7-day undo window
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import Schedule, ScheduleChangeHistory


# Configuration
MAX_HISTORY_ENTRIES = 50
UNDO_TIME_WINDOW_DAYS = 7


def create_schedule_snapshot(db: Session, schedule_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Create JSONB snapshot of schedule entries for undo capability.

    Args:
        db: Database session
        schedule_ids: List of schedule IDs to snapshot

    Returns:
        List of schedule dictionaries with all fields

    Example:
        >>> snapshot = create_schedule_snapshot(db, [1, 2, 3])
        >>> snapshot[0]
        {
            'id': 1,
            'user_id': 'uuid...',
            'workout_id': 5,
            'scheduled_date': '2025-12-30',
            'completed': False,
            'skipped': False,
            ...
        }
    """
    schedules = db.query(Schedule).filter(Schedule.id.in_(schedule_ids)).all()

    snapshot = []
    for s in schedules:
        snapshot.append({
            'id': s.id,
            'user_id': str(s.user_id),
            'user_generated_program_id': s.user_generated_program_id,
            'partner_program_id': s.partner_program_id,
            'workout_id': s.workout_id,
            'scheduled_date': s.scheduled_date.isoformat() if s.scheduled_date else None,
            'completed': s.completed,
            'skipped': s.skipped,
            'skipped_at': s.skipped_at.isoformat() if s.skipped_at else None,
            'skip_reason': s.skip_reason,
            'is_deload': s.is_deload,
            'deload_intensity_modifier': float(s.deload_intensity_modifier) if s.deload_intensity_modifier else None,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'modified_at': s.modified_at.isoformat() if s.modified_at else None,
        })

    return snapshot


def log_schedule_change(
    db: Session,
    user_id: str,
    change_type: str,
    description: str,
    affected_schedule_ids: List[int],
    before_state: List[Dict],
    after_state: List[Dict],
    function_name: Optional[str] = None
) -> ScheduleChangeHistory:
    """
    Log a schedule change to history for undo capability.

    Args:
        db: Database session
        user_id: User UUID
        change_type: Type of change (move, swap, skip, add_rest, etc.)
        description: Human-readable description
        affected_schedule_ids: List of schedule IDs affected
        before_state: JSONB snapshot before change
        after_state: JSONB snapshot after change
        function_name: Name of function that made change

    Returns:
        Created ScheduleChangeHistory entry

    Example:
        >>> log_schedule_change(
        ...     db, user_id, "move",
        ...     "Moved Leg Day from Dec 30 to Jan 2",
        ...     [1], before_snapshot, after_snapshot,
        ...     "move_workout"
        ... )
    """
    history_entry = ScheduleChangeHistory(
        user_id=user_id,
        change_type=change_type,
        description=description,
        affected_schedule_ids=affected_schedule_ids,
        before_state=before_state,
        after_state=after_state,
        function_name=function_name,
        is_undone=False
    )

    db.add(history_entry)
    db.flush()

    # Cleanup old history (keep max 50 entries)
    cleanup_old_history(db, user_id)

    return history_entry


def cleanup_old_history(db: Session, user_id: str):
    """
    Remove old history entries beyond MAX_HISTORY_ENTRIES limit.

    Args:
        db: Database session
        user_id: User UUID

    Keeps the 50 most recent entries, deletes the rest.
    """
    # Get all history entries for user, ordered by newest first
    all_entries = db.query(ScheduleChangeHistory).filter(
        ScheduleChangeHistory.user_id == user_id
    ).order_by(desc(ScheduleChangeHistory.created_at)).all()

    # If we have more than MAX_HISTORY_ENTRIES, delete the oldest ones
    if len(all_entries) > MAX_HISTORY_ENTRIES:
        entries_to_delete = all_entries[MAX_HISTORY_ENTRIES:]
        for entry in entries_to_delete:
            db.delete(entry)


def get_recent_changes(db: Session, user_id: str, limit: int = 5) -> List[ScheduleChangeHistory]:
    """
    Get recent schedule changes for a user.

    Args:
        db: Database session
        user_id: User UUID
        limit: Maximum number of entries to return

    Returns:
        List of ScheduleChangeHistory entries, newest first
    """
    return db.query(ScheduleChangeHistory).filter(
        ScheduleChangeHistory.user_id == user_id
    ).order_by(desc(ScheduleChangeHistory.created_at)).limit(limit).all()


def can_undo_change(change: ScheduleChangeHistory) -> Tuple[bool, Optional[str]]:
    """
    Check if a change can be undone.

    Args:
        change: ScheduleChangeHistory entry

    Returns:
        (can_undo: bool, error_message: Optional[str])

    Rules:
    - Cannot undo if already undone
    - Cannot undo if older than 7 days
    """
    if change.is_undone:
        return False, "This change has already been undone."

    age = datetime.utcnow() - change.created_at
    if age.days > UNDO_TIME_WINDOW_DAYS:
        return False, f"This change is too old to undo (older than {UNDO_TIME_WINDOW_DAYS} days)."

    return True, None


def undo_last_change(db: Session, user_id: str, change_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """
    Undo the last schedule change (or specific change by ID).

    Args:
        db: Database session
        user_id: User UUID
        change_id: Optional specific change ID to undo (defaults to most recent)

    Returns:
        (success: bool, error_message: Optional[str])

    Algorithm:
    1. Retrieve change history entry
    2. Validate (not undone, within 7 days)
    3. Delete schedules created after the change (IDs in after_state but not in before_state)
    4. Restore/update schedules from before_state
    5. Mark original change as undone
    6. Log the undo itself as new change
    7. Commit

    Example:
        >>> success, error = undo_last_change(db, user_id)
        >>> if success:
        ...     print("Change undone successfully")
    """
    # Get the change to undo
    if change_id:
        change = db.query(ScheduleChangeHistory).filter(
            ScheduleChangeHistory.id == change_id,
            ScheduleChangeHistory.user_id == user_id
        ).first()

        if not change:
            return False, "Change not found."
    else:
        # Get most recent undoable change
        change = db.query(ScheduleChangeHistory).filter(
            ScheduleChangeHistory.user_id == user_id,
            ScheduleChangeHistory.is_undone == False
        ).order_by(desc(ScheduleChangeHistory.created_at)).first()

        if not change:
            return False, "No recent changes to undo."

    # Validate
    can_undo, error = can_undo_change(change)
    if not can_undo:
        return False, error

    # Extract schedule IDs from before and after states
    before_ids = {s['id'] for s in change.before_state}
    after_ids = {s['id'] for s in change.after_state}

    # IDs created by this change (in after but not in before)
    created_ids = after_ids - before_ids

    # IDs modified by this change (in both before and after)
    modified_ids = after_ids & before_ids

    # IDs deleted by this change (in before but not in after)
    deleted_ids = before_ids - after_ids

    try:
        # 1. Delete schedules that were created by this change
        if created_ids:
            db.query(Schedule).filter(Schedule.id.in_(created_ids)).delete(synchronize_session=False)

        # 2. Restore schedules that were deleted by this change
        for schedule_data in change.before_state:
            if schedule_data['id'] in deleted_ids:
                # Recreate deleted schedule
                from datetime import date as date_type
                restored_schedule = Schedule(
                    id=schedule_data['id'],
                    user_id=schedule_data['user_id'],
                    user_generated_program_id=schedule_data['user_generated_program_id'],
                    partner_program_id=schedule_data['partner_program_id'],
                    workout_id=schedule_data['workout_id'],
                    scheduled_date=date_type.fromisoformat(schedule_data['scheduled_date']) if schedule_data['scheduled_date'] else None,
                    completed=schedule_data['completed'],
                    skipped=schedule_data['skipped'],
                    skipped_at=datetime.fromisoformat(schedule_data['skipped_at']) if schedule_data['skipped_at'] else None,
                    skip_reason=schedule_data['skip_reason'],
                    is_deload=schedule_data['is_deload'],
                    deload_intensity_modifier=schedule_data['deload_intensity_modifier'],
                )
                db.add(restored_schedule)

        # 3. Restore modified schedules to before state
        for schedule_data in change.before_state:
            if schedule_data['id'] in modified_ids:
                schedule = db.query(Schedule).filter(Schedule.id == schedule_data['id']).first()
                if schedule:
                    from datetime import date as date_type
                    # Restore all fields
                    schedule.user_id = schedule_data['user_id']
                    schedule.user_generated_program_id = schedule_data['user_generated_program_id']
                    schedule.partner_program_id = schedule_data['partner_program_id']
                    schedule.workout_id = schedule_data['workout_id']
                    schedule.scheduled_date = date_type.fromisoformat(schedule_data['scheduled_date']) if schedule_data['scheduled_date'] else None
                    schedule.completed = schedule_data['completed']
                    schedule.skipped = schedule_data['skipped']
                    schedule.skipped_at = datetime.fromisoformat(schedule_data['skipped_at']) if schedule_data['skipped_at'] else None
                    schedule.skip_reason = schedule_data['skip_reason']
                    schedule.is_deload = schedule_data['is_deload']
                    schedule.deload_intensity_modifier = schedule_data['deload_intensity_modifier']
                    schedule.modified_at = datetime.utcnow()

        db.flush()

        # 4. Mark original change as undone
        change.is_undone = True
        change.undone_at = datetime.utcnow()

        # 5. Log the undo itself as a new change
        undo_entry = ScheduleChangeHistory(
            user_id=user_id,
            change_type="undo",
            description=f"Undid change: {change.description}",
            affected_schedule_ids=change.affected_schedule_ids,
            before_state=change.after_state,  # Reversed
            after_state=change.before_state,  # Reversed
            function_name="undo_last_change",
            is_undone=False,
            undo_change_id=change.id
        )
        db.add(undo_entry)

        db.commit()
        return True, None

    except Exception as e:
        db.rollback()
        return False, f"Failed to undo change: {str(e)}"


def format_change_for_display(change: ScheduleChangeHistory) -> str:
    """
    Format a change entry for display to user.

    Args:
        change: ScheduleChangeHistory entry

    Returns:
        Formatted string

    Example:
        >>> format_change_for_display(change)
        "Moved Leg Day from Dec 30 to Jan 2 (2 hours ago)"
    """
    age = datetime.utcnow() - change.created_at

    if age.days == 0:
        if age.seconds < 3600:
            time_ago = f"{age.seconds // 60} minutes ago"
        else:
            time_ago = f"{age.seconds // 3600} hours ago"
    elif age.days == 1:
        time_ago = "yesterday"
    else:
        time_ago = f"{age.days} days ago"

    status = " [UNDONE]" if change.is_undone else ""

    return f"{change.description} ({time_ago}){status}"
