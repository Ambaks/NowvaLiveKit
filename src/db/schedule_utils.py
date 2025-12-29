"""
Database utility functions for workout scheduling
Handles schedule creation, retrieval, and smart rest day allocation
"""
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from .models import Schedule, Workout, WorkoutExercise, Exercise, Set, UserGeneratedProgram, PartnerProgram
from .schedule_history import create_schedule_snapshot, log_schedule_change


def get_next_monday(start_date: Optional[date] = None) -> date:
    """
    Get the next Monday from the given date (or today if not specified).
    If the date IS a Monday, return that Monday.

    Args:
        start_date: Date to start from (defaults to today)

    Returns:
        Next Monday as a date object
    """
    if start_date is None:
        start_date = date.today()

    # If it's already Monday (weekday 0), return it
    if start_date.weekday() == 0:
        return start_date

    # Otherwise find next Monday
    days_until_monday = (7 - start_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7

    return start_date + timedelta(days=days_until_monday)


def analyze_workout_muscle_groups(db: Session, workout_id: int) -> Dict[str, int]:
    """
    Analyze a workout to determine primary muscle groups trained.
    Returns a dict of muscle_group -> exercise_count

    Args:
        db: Database session
        workout_id: Workout ID

    Returns:
        Dict mapping muscle groups to number of exercises (e.g., {"Quads": 3, "Chest": 2})
    """
    workout_exercises = db.query(WorkoutExercise).options(
        joinedload(WorkoutExercise.exercise)
    ).filter(WorkoutExercise.workout_id == workout_id).all()

    muscle_group_counts = {}
    for we in workout_exercises:
        if we.exercise and we.exercise.muscle_group:
            mg = we.exercise.muscle_group
            muscle_group_counts[mg] = muscle_group_counts.get(mg, 0) + 1

    return muscle_group_counts


def is_sufficient_rest_between_workouts(
    db: Session,
    workout1_id: int,
    workout2_id: int,
    threshold: float = 0.3
) -> bool:
    """
    Determine if two workouts have sufficient muscle group separation.
    Returns True if workouts target different muscle groups (can be done back-to-back).
    Returns False if significant overlap (need rest day).

    Args:
        db: Database session
        workout1_id: First workout ID
        workout2_id: Second workout ID
        threshold: Overlap threshold (0.3 = 30% muscle group overlap)

    Returns:
        True if sufficient rest/separation, False if rest day needed
    """
    mg1 = analyze_workout_muscle_groups(db, workout1_id)
    mg2 = analyze_workout_muscle_groups(db, workout2_id)

    if not mg1 or not mg2:
        # If we can't analyze, default to allowing back-to-back
        return True

    # Calculate overlap: common muscle groups / total unique muscle groups
    all_groups = set(mg1.keys()) | set(mg2.keys())
    common_groups = set(mg1.keys()) & set(mg2.keys())

    if not all_groups:
        return True

    overlap_ratio = len(common_groups) / len(all_groups)

    return overlap_ratio < threshold


def create_smart_schedule_pattern(
    db: Session,
    workout_ids: List[int],
    days_per_week: int
) -> List[int]:
    """
    Create a smart weekly schedule pattern that respects muscle group recovery.
    Returns a list of weekday indices (0=Mon, 1=Tue, ..., 6=Sun).

    Strategy:
    - 2 days/week: Mon, Fri (maximum rest)
    - 3 days/week: Mon, Wed, Fri (standard pattern)
    - 4 days/week: Mon, Tue, Thu, Sat (upper/lower split friendly)
    - 5 days/week: Mon, Tue, Wed, Fri, Sat (mid-week rest)
    - 6 days/week: Mon-Sat
    - 7 days/week: Every day

    Args:
        db: Database session
        workout_ids: List of workout IDs in the program (to analyze muscle groups)
        days_per_week: Number of training days per week

    Returns:
        List of weekday indices (e.g., [0, 2, 4] for Mon/Wed/Fri)
    """
    if days_per_week == 1:
        return [0]  # Monday only
    elif days_per_week == 2:
        return [0, 4]  # Mon, Fri
    elif days_per_week == 3:
        return [0, 2, 4]  # Mon, Wed, Fri
    elif days_per_week == 4:
        return [0, 1, 3, 5]  # Mon, Tue, Thu, Sat
    elif days_per_week == 5:
        return [0, 1, 2, 4, 5]  # Mon, Tue, Wed, Fri, Sat
    elif days_per_week == 6:
        return [0, 1, 2, 3, 4, 5]  # Mon-Sat
    elif days_per_week >= 7:
        return [0, 1, 2, 3, 4, 5, 6]  # Every day
    else:
        return [0]  # Default to Monday


def clear_future_schedules(db: Session, user_id: str) -> int:
    """
    Delete all incomplete future scheduled workouts for a user.
    Preserves completed workouts for history/progress tracking.

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        Number of schedule entries deleted
    """
    today = date.today()

    # Delete all future uncompleted schedules
    deleted_count = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= today,
            Schedule.completed == False
        )
    ).delete(synchronize_session=False)

    db.commit()
    return deleted_count


def create_schedule_for_program(
    db: Session,
    user_id: str,
    program_id: int,
    program_type: str = "user_generated",
    start_date: Optional[date] = None,
    days_per_week: int = 3
) -> List[Schedule]:
    """
    Create schedule entries for a program, mapping workouts to calendar dates.
    Uses smart scheduling to respect rest days and muscle group recovery.

    IMPORTANT: This function automatically clears all existing incomplete future
    schedules for the user before creating new ones, ensuring users only have
    one active program at a time.

    Args:
        db: Database session
        user_id: User's UUID as string
        program_id: Program ID (UserGeneratedProgram or PartnerProgram)
        program_type: "user_generated" or "partner"
        start_date: When to start the program (defaults to next Monday)
        days_per_week: Number of training days per week

    Returns:
        List of created Schedule objects
    """
    # Clear any existing future schedules before creating new ones
    deleted_count = clear_future_schedules(db, user_id)
    if deleted_count > 0:
        print(f"[SCHEDULE] Cleared {deleted_count} existing future schedules for user {user_id}")

    # Default to next Monday if no start date provided
    if start_date is None:
        start_date = get_next_monday()

    # Fetch all workouts for the program, ordered by week and day
    if program_type == "user_generated":
        workouts = db.query(Workout).filter(
            Workout.user_generated_program_id == program_id
        ).order_by(Workout.week_number, Workout.day_number).all()
    else:
        workouts = db.query(Workout).filter(
            Workout.partner_program_id == program_id
        ).order_by(Workout.week_number, Workout.day_number).all()

    if not workouts:
        return []

    # Get the smart weekly schedule pattern
    workout_ids = [w.id for w in workouts]
    weekly_pattern = create_smart_schedule_pattern(db, workout_ids, days_per_week)

    # Create schedule entries
    schedules = []
    current_date = start_date
    workout_index = 0

    for workout in workouts:
        # Calculate which day of the week this workout should be on
        pattern_index = workout_index % len(weekly_pattern)
        target_weekday = weekly_pattern[pattern_index]

        # Find the next occurrence of this weekday
        days_ahead = (target_weekday - current_date.weekday()) % 7
        if workout_index > 0 and days_ahead == 0:
            # If we'd schedule on the same day, move to next week
            days_ahead = 7

        scheduled_date = current_date + timedelta(days=days_ahead)

        # Create schedule entry
        schedule = Schedule(
            user_id=user_id,
            user_generated_program_id=program_id if program_type == "user_generated" else None,
            partner_program_id=program_id if program_type == "partner" else None,
            workout_id=workout.id,
            scheduled_date=scheduled_date,
            completed=False
        )

        db.add(schedule)
        schedules.append(schedule)

        # Move current_date forward for next workout
        current_date = scheduled_date + timedelta(days=1)
        workout_index += 1

    db.commit()

    return schedules


def get_todays_workout(db: Session, user_id: str) -> Optional[Dict]:
    """
    Get today's scheduled workout for a user with full structure.
    Eagerly loads all related data (exercises, sets, etc.).

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        Dict with workout data or None if no workout scheduled today
        {
            "schedule_id": int,
            "workout_id": int,
            "workout_name": str,
            "description": str,
            "exercises": [
                {
                    "workout_exercise_id": int,
                    "exercise_id": int,
                    "exercise_name": str,
                    "muscle_group": str,
                    "order_number": int,
                    "notes": str,
                    "sets": [
                        {
                            "set_id": int,
                            "set_number": int,
                            "reps": int,
                            "intensity_percent": float,
                            "rpe": float,
                            "rest_seconds": int,
                            "velocity_threshold": float (optional)
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    today = date.today()

    # Query schedule with eager loading
    schedule = db.query(Schedule).options(
        joinedload(Schedule.workout)
        .joinedload(Workout.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).options(
        joinedload(Schedule.workout)
        .joinedload(Workout.workout_exercises)
        .joinedload(WorkoutExercise.sets)
    ).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date == today,
            Schedule.completed == False
        )
    ).first()

    if not schedule or not schedule.workout:
        return None

    workout = schedule.workout

    # Build structured response
    exercises_data = []
    for we in sorted(workout.workout_exercises, key=lambda x: x.order_number):
        sets_data = []
        for s in sorted(we.sets, key=lambda x: x.set_number):
            sets_data.append({
                "set_id": s.id,
                "set_number": s.set_number,
                "reps": s.reps,
                "intensity_percent": float(s.intensity_percent) if s.intensity_percent else None,
                "rpe": float(s.rpe) if s.rpe else None,
                "rest_seconds": s.rest_seconds,
                "velocity_threshold": float(s.velocity_threshold) if s.velocity_threshold else None,
                "velocity_min": float(s.velocity_min) if s.velocity_min else None,
                "velocity_max": float(s.velocity_max) if s.velocity_max else None,
            })

        exercises_data.append({
            "workout_exercise_id": we.id,
            "exercise_id": we.exercise.id if we.exercise else None,
            "exercise_name": we.exercise.name if we.exercise else "Unknown",
            "muscle_group": we.exercise.muscle_group if we.exercise else None,
            "category": we.exercise.category if we.exercise else None,
            "order_number": we.order_number,
            "notes": we.notes,
            "sets": sets_data
        })

    return {
        "schedule_id": schedule.id,
        "workout_id": workout.id,
        "workout_name": workout.name,
        "description": workout.description,
        "week_number": workout.week_number,
        "day_number": workout.day_number,
        "phase": workout.phase,
        "exercises": exercises_data
    }


def get_upcoming_workouts(
    db: Session,
    user_id: str,
    days_ahead: int = 7
) -> List[Dict]:
    """
    Get upcoming scheduled workouts for the next N days.

    Args:
        db: Database session
        user_id: User's UUID as string
        days_ahead: Number of days to look ahead

    Returns:
        List of workout summaries with scheduled dates
    """
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    schedules = db.query(Schedule).options(
        joinedload(Schedule.workout)
    ).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= today,
            Schedule.scheduled_date <= end_date
        )
    ).order_by(Schedule.scheduled_date).all()

    result = []
    for schedule in schedules:
        if schedule.workout:
            result.append({
                "schedule_id": schedule.id,
                "scheduled_date": schedule.scheduled_date.isoformat(),
                "completed": schedule.completed,
                "workout_id": schedule.workout.id,
                "workout_name": schedule.workout.name,
                "week_number": schedule.workout.week_number,
                "day_number": schedule.workout.day_number,
                "phase": schedule.workout.phase
            })

    return result


def mark_workout_completed(db: Session, schedule_id: int) -> bool:
    """
    Mark a scheduled workout as completed.

    Args:
        db: Database session
        schedule_id: Schedule entry ID

    Returns:
        True if successful, False if schedule not found
    """
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()

    if not schedule:
        return False

    schedule.completed = True
    db.commit()

    return True


def reschedule_workout(
    db: Session,
    schedule_id: int,
    new_date: date
) -> bool:
    """
    Reschedule a workout to a different date.

    Args:
        db: Database session
        schedule_id: Schedule entry ID
        new_date: New scheduled date

    Returns:
        True if successful, False if schedule not found
    """
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()

    if not schedule:
        return False

    schedule.scheduled_date = new_date
    db.commit()

    return True


def get_user_schedule_range(
    db: Session,
    user_id: str,
    start_date: date,
    end_date: date
) -> List[Dict]:
    """
    Get all scheduled workouts for a user within a date range.
    Useful for calendar views.

    Args:
        db: Database session
        user_id: User's UUID as string
        start_date: Start of range
        end_date: End of range

    Returns:
        List of schedule entries with workout info
    """
    schedules = db.query(Schedule).options(
        joinedload(Schedule.workout)
    ).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= start_date,
            Schedule.scheduled_date <= end_date
        )
    ).order_by(Schedule.scheduled_date).all()

    result = []
    for schedule in schedules:
        if schedule.workout:
            result.append({
                "schedule_id": schedule.id,
                "scheduled_date": schedule.scheduled_date.isoformat(),
                "completed": schedule.completed,
                "workout_id": schedule.workout.id,
                "workout_name": schedule.workout.name,
                "week_number": schedule.workout.week_number,
                "day_number": schedule.workout.day_number,
                "phase": schedule.workout.phase,
                "description": schedule.workout.description
            })

    return result


def has_scheduled_workouts(db: Session, user_id: str) -> bool:
    """
    Check if user has any scheduled workouts.

    Args:
        db: Database session
        user_id: User's UUID as string

    Returns:
        True if user has at least one scheduled workout
    """
    count = db.query(Schedule).filter(Schedule.user_id == user_id).count()
    return count > 0


# ===== SCHEDULE MODIFICATION FUNCTIONS =====


def move_workout(
    db: Session,
    schedule_id: int,
    new_date: date,
    allow_overwrite: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Move a single workout to a new date (NO cascading).

    Args:
        db: Database session
        schedule_id: Schedule entry to move
        new_date: Target date
        allow_overwrite: If True, overwrite existing workout on target date

    Returns:
        (success: bool, error_message: Optional[str])
    """
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()

    if not schedule:
        return (False, "Workout not found")

    # Prevent moving completed workouts
    if schedule.completed:
        return (False, "Cannot move completed workouts")

    # Prevent moving skipped workouts
    if schedule.skipped:
        return (False, "Cannot move skipped workouts")

    # Check if target date is in the past
    if new_date < date.today():
        return (False, "Cannot move workout to a past date")

    # Check for conflicts on target date
    conflict = db.query(Schedule).filter(
        and_(
            Schedule.user_id == schedule.user_id,
            Schedule.scheduled_date == new_date,
            Schedule.id != schedule_id,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).first()

    if conflict and not allow_overwrite:
        workout_name = conflict.workout.name if conflict.workout else "a workout"
        return (False, f"You already have '{workout_name}' scheduled on {new_date}. Would you like to swap them instead?")

    # Capture before state for history
    affected_ids = [schedule_id]
    if conflict and allow_overwrite:
        affected_ids.append(conflict.id)

    before_state = create_schedule_snapshot(db, affected_ids)
    old_date = schedule.scheduled_date

    if conflict and allow_overwrite:
        # Delete conflicting workout
        db.delete(conflict)

    # Move the workout
    schedule.scheduled_date = new_date
    schedule.modified_at = datetime.utcnow()
    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, [schedule_id])

    # Log change
    workout_name = schedule.workout.name if schedule.workout else "workout"
    description = f"Moved {workout_name} from {old_date.strftime('%b %d')} to {new_date.strftime('%b %d')}"
    log_schedule_change(
        db, str(schedule.user_id), "move", description,
        affected_ids, before_state, after_state, "move_workout"
    )

    db.commit()

    return (True, None)


def swap_workouts(
    db: Session,
    schedule_id_1: int,
    schedule_id_2: int
) -> Tuple[bool, Optional[str]]:
    """
    Swap two individual workouts by exchanging their dates.

    Args:
        db: Database session
        schedule_id_1: First workout schedule ID
        schedule_id_2: Second workout schedule ID

    Returns:
        (success: bool, error_message: Optional[str])
    """
    schedule1 = db.query(Schedule).filter(Schedule.id == schedule_id_1).first()
    schedule2 = db.query(Schedule).filter(Schedule.id == schedule_id_2).first()

    if not schedule1 or not schedule2:
        return (False, "One or both workouts not found")

    # Prevent swapping completed workouts
    if schedule1.completed or schedule2.completed:
        return (False, "Cannot swap completed workouts")

    # Prevent swapping skipped workouts
    if schedule1.skipped or schedule2.skipped:
        return (False, "Cannot swap skipped workouts")

    # Verify same user
    if schedule1.user_id != schedule2.user_id:
        return (False, "Cannot swap workouts between different users")

    # Capture before state for history
    affected_ids = [schedule_id_1, schedule_id_2]
    before_state = create_schedule_snapshot(db, affected_ids)
    date1_old = schedule1.scheduled_date
    date2_old = schedule2.scheduled_date

    # Swap dates
    temp_date = schedule1.scheduled_date
    schedule1.scheduled_date = schedule2.scheduled_date
    schedule2.scheduled_date = temp_date

    schedule1.modified_at = datetime.utcnow()
    schedule2.modified_at = datetime.utcnow()
    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    workout1_name = schedule1.workout.name if schedule1.workout else "workout"
    workout2_name = schedule2.workout.name if schedule2.workout else "workout"
    description = f"Swapped {workout1_name} ({date1_old.strftime('%b %d')}) with {workout2_name} ({date2_old.strftime('%b %d')})"
    log_schedule_change(
        db, str(schedule1.user_id), "swap", description,
        affected_ids, before_state, after_state, "swap_workouts"
    )

    db.commit()

    return (True, None)


def swap_weeks(
    db: Session,
    user_id: str,
    week1_start: date,
    week2_start: date
) -> Tuple[bool, Optional[str], List[Tuple[int, int]]]:
    """
    Swap ALL workouts between two weeks.

    Args:
        db: Database session
        user_id: User's UUID
        week1_start: Start date of first week (Monday)
        week2_start: Start date of second week (Monday)

    Returns:
        (success: bool, error_message: Optional[str], swapped_pairs: List[Tuple[schedule_id, schedule_id]])
    """
    # Get week end dates
    week1_end = week1_start + timedelta(days=6)
    week2_end = week2_start + timedelta(days=6)

    # Fetch all workouts in both weeks
    week1_workouts = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= week1_start,
            Schedule.scheduled_date <= week1_end,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).order_by(Schedule.scheduled_date).all()

    week2_workouts = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= week2_start,
            Schedule.scheduled_date <= week2_end,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).order_by(Schedule.scheduled_date).all()

    if not week1_workouts and not week2_workouts:
        return (False, "No workouts found in either week", [])

    # Capture before state for history
    affected_ids = [w.id for w in week1_workouts] + [w.id for w in week2_workouts]
    before_state = create_schedule_snapshot(db, affected_ids)

    # Calculate offset between weeks (in days)
    week_offset = (week2_start - week1_start).days

    # Swap all week1 workouts forward
    for workout in week1_workouts:
        workout.scheduled_date = workout.scheduled_date + timedelta(days=week_offset)
        workout.modified_at = datetime.utcnow()

    # Swap all week2 workouts backward
    for workout in week2_workouts:
        workout.scheduled_date = workout.scheduled_date - timedelta(days=week_offset)
        workout.modified_at = datetime.utcnow()

    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    description = f"Swapped week starting {week1_start.strftime('%b %d')} with week starting {week2_start.strftime('%b %d')} ({len(affected_ids)} workouts)"
    log_schedule_change(
        db, str(user_id), "swap_weeks", description,
        affected_ids, before_state, after_state, "swap_weeks"
    )

    db.commit()

    swapped_pairs = [(w1.id, w2.id) for w1, w2 in zip(week1_workouts, week2_workouts)]

    return (True, None, swapped_pairs)


def skip_workout(
    db: Session,
    schedule_id: int,
    reason: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Mark a workout as skipped (preserves for adherence tracking).
    Does NOT reschedule automatically.

    Args:
        db: Database session
        schedule_id: Schedule entry to skip
        reason: Optional reason for skipping

    Returns:
        (success: bool, error_message: Optional[str])
    """
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()

    if not schedule:
        return (False, "Workout not found")

    if schedule.completed:
        return (False, "Cannot skip a completed workout")

    if schedule.skipped:
        return (False, "Workout is already marked as skipped")

    # Capture before state for history
    affected_ids = [schedule_id]
    before_state = create_schedule_snapshot(db, affected_ids)

    # Mark as skipped
    schedule.skipped = True
    schedule.skipped_at = datetime.utcnow()
    schedule.skip_reason = reason
    schedule.modified_at = datetime.utcnow()
    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    workout_name = schedule.workout.name if schedule.workout else "workout"
    skip_date = schedule.scheduled_date.strftime('%b %d')
    reason_text = f" (Reason: {reason})" if reason else ""
    description = f"Skipped {workout_name} on {skip_date}{reason_text}"
    log_schedule_change(
        db, str(schedule.user_id), "skip", description,
        affected_ids, before_state, after_state, "skip_workout"
    )

    db.commit()

    return (True, None)


def add_rest_day(
    db: Session,
    user_id: str,
    rest_date: date,
    shift_future_workouts: bool = True
) -> Tuple[bool, Optional[str], int]:
    """
    Add a rest day, optionally shifting future workouts forward.

    Args:
        db: Database session
        user_id: User's UUID
        rest_date: Date to insert rest day
        shift_future_workouts: If True, push all future workouts forward by 1 day

    Returns:
        (success: bool, error_message: Optional[str], workouts_shifted: int)
    """
    # Check if there's already a workout on this date
    existing = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date == rest_date,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).first()

    if existing:
        workout_name = existing.workout.name if existing.workout else "a workout"
        return (False, f"You already have '{workout_name}' on {rest_date}. Move it first.", 0)

    shifted_count = 0

    if shift_future_workouts:
        # Get all future workouts (on or after rest_date)
        future_workouts = db.query(Schedule).filter(
            and_(
                Schedule.user_id == user_id,
                Schedule.scheduled_date >= rest_date,
                Schedule.completed == False,
                Schedule.skipped == False
            )
        ).order_by(Schedule.scheduled_date.desc()).all()  # Process in reverse to avoid conflicts

        if future_workouts:
            # Capture before state for history
            affected_ids = [w.id for w in future_workouts]
            before_state = create_schedule_snapshot(db, affected_ids)

            # Shift each workout forward by 1 day
            for workout in future_workouts:
                workout.scheduled_date = workout.scheduled_date + timedelta(days=1)
                workout.modified_at = datetime.utcnow()
                shifted_count += 1

            db.flush()

            # Capture after state for history
            after_state = create_schedule_snapshot(db, affected_ids)

            # Log change
            description = f"Added rest day on {rest_date.strftime('%b %d')}, shifted {shifted_count} workouts forward"
            log_schedule_change(
                db, str(user_id), "add_rest", description,
                affected_ids, before_state, after_state, "add_rest_day"
            )

        db.commit()

    return (True, None, shifted_count)


def repeat_workout(
    db: Session,
    schedule_id: int,
    repeat_date: date
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Duplicate a workout to another date.
    Creates a new schedule entry with the same workout.

    Args:
        db: Database session
        schedule_id: Original workout to repeat
        repeat_date: Date to repeat the workout

    Returns:
        (success: bool, error_message: Optional[str], new_schedule_id: Optional[int])
    """
    original = db.query(Schedule).filter(Schedule.id == schedule_id).first()

    if not original:
        return (False, "Workout not found", None)

    # Check for conflicts
    conflict = db.query(Schedule).filter(
        and_(
            Schedule.user_id == original.user_id,
            Schedule.scheduled_date == repeat_date,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).first()

    if conflict:
        workout_name = conflict.workout.name if conflict.workout else "a workout"
        return (False, f"You already have '{workout_name}' on {repeat_date}", None)

    # Capture before state for history (empty - we're creating new)
    before_state = []

    # Create duplicate schedule entry
    repeated = Schedule(
        user_id=original.user_id,
        user_generated_program_id=original.user_generated_program_id,
        partner_program_id=original.partner_program_id,
        workout_id=original.workout_id,
        scheduled_date=repeat_date,
        completed=False,
        skipped=False,
        is_deload=original.is_deload,
        deload_intensity_modifier=original.deload_intensity_modifier
    )

    db.add(repeated)
    db.flush()
    db.refresh(repeated)

    # Capture after state for history
    affected_ids = [repeated.id]
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    workout_name = original.workout.name if original.workout else "workout"
    orig_date = original.scheduled_date.strftime('%b %d')
    new_date = repeat_date.strftime('%b %d')
    description = f"Repeated {workout_name} from {orig_date} to {new_date}"
    log_schedule_change(
        db, str(original.user_id), "repeat", description,
        affected_ids, before_state, after_state, "repeat_workout"
    )

    db.commit()

    return (True, None, repeated.id)


def apply_deload_week(
    db: Session,
    user_id: str,
    week_start: date,
    intensity_modifier: float = 0.7
) -> Tuple[bool, Optional[str], int]:
    """
    Apply deload modifier to all workouts in a week.
    Marks workouts with reduced intensity for recovery.

    Args:
        db: Database session
        user_id: User's UUID
        week_start: Start of deload week (Monday)
        intensity_modifier: Intensity reduction (0.7 = 70% of prescribed, default)

    Returns:
        (success: bool, error_message: Optional[str], workouts_modified: int)
    """
    if not (0.3 <= intensity_modifier <= 1.0):
        return (False, "Intensity modifier must be between 0.3 and 1.0", 0)

    week_end = week_start + timedelta(days=6)

    # Get all workouts in the week
    workouts = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= week_start,
            Schedule.scheduled_date <= week_end,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).all()

    if not workouts:
        return (False, f"No workouts found in week starting {week_start}", 0)

    # Capture before state for history
    affected_ids = [w.id for w in workouts]
    before_state = create_schedule_snapshot(db, affected_ids)

    # Apply deload modifier
    modified_count = 0
    for workout in workouts:
        workout.is_deload = True
        workout.deload_intensity_modifier = intensity_modifier
        workout.modified_at = datetime.utcnow()
        modified_count += 1

    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    intensity_pct = int(intensity_modifier * 100)
    description = f"Applied {intensity_pct}% deload week starting {week_start.strftime('%b %d')} ({modified_count} workouts)"
    log_schedule_change(
        db, str(user_id), "deload", description,
        affected_ids, before_state, after_state, "apply_deload_week"
    )

    db.commit()

    return (True, None, modified_count)


def clear_date_range(
    db: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    preserve_completed: bool = True
) -> Tuple[bool, Optional[str], int]:
    """
    Clear all workouts in a date range (vacation mode).

    Args:
        db: Database session
        user_id: User's UUID
        start_date: Range start
        end_date: Range end
        preserve_completed: If True, only delete incomplete workouts

    Returns:
        (success: bool, error_message: Optional[str], workouts_cleared: int)
    """
    if start_date > end_date:
        return (False, "Start date must be before end date", 0)

    # Build query
    query = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= start_date,
            Schedule.scheduled_date <= end_date
        )
    )

    if preserve_completed:
        query = query.filter(Schedule.completed == False)

    # Get workouts to delete for history
    workouts_to_delete = query.all()

    if not workouts_to_delete:
        return (True, None, 0)

    # Capture before state for history
    affected_ids = [w.id for w in workouts_to_delete]
    before_state = create_schedule_snapshot(db, affected_ids)

    # Delete workouts
    cleared_count = query.delete(synchronize_session=False)
    db.flush()

    # Capture after state for history (empty - workouts deleted)
    after_state = []

    # Log change
    description = f"Cleared {cleared_count} workouts from {start_date.strftime('%b %d')} to {end_date.strftime('%b %d')}"
    log_schedule_change(
        db, str(user_id), "clear", description,
        affected_ids, before_state, after_state, "clear_date_range"
    )

    db.commit()

    return (True, None, cleared_count)


def reschedule_remaining_week(
    db: Session,
    user_id: str,
    days_offset: int = 1
) -> Tuple[bool, Optional[str], int]:
    """
    Push the rest of this week's workouts forward by N days.
    Useful when user needs extra recovery mid-week.

    Args:
        db: Database session
        user_id: User's UUID
        days_offset: How many days to push forward (default: 1)

    Returns:
        (success: bool, error_message: Optional[str], workouts_rescheduled: int)
    """
    today = date.today()

    # Get end of current week (Sunday)
    days_until_sunday = 6 - today.weekday()
    week_end = today + timedelta(days=days_until_sunday)

    # Get remaining workouts this week
    remaining_workouts = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date > today,  # Future only
            Schedule.scheduled_date <= week_end,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).order_by(Schedule.scheduled_date.desc()).all()  # Reverse order to avoid conflicts

    if not remaining_workouts:
        return (False, "No remaining workouts this week", 0)

    # Capture before state for history
    affected_ids = [w.id for w in remaining_workouts]
    before_state = create_schedule_snapshot(db, affected_ids)

    # Shift workouts
    rescheduled_count = 0
    for workout in remaining_workouts:
        workout.scheduled_date = workout.scheduled_date + timedelta(days=days_offset)
        workout.modified_at = datetime.utcnow()
        rescheduled_count += 1

    db.flush()

    # Capture after state for history
    after_state = create_schedule_snapshot(db, affected_ids)

    # Log change
    description = f"Pushed {rescheduled_count} remaining workouts forward by {days_offset} day{'s' if days_offset != 1 else ''}"
    log_schedule_change(
        db, str(user_id), "reschedule", description,
        affected_ids, before_state, after_state, "reschedule_remaining_week"
    )

    db.commit()

    return (True, None, rescheduled_count)


def find_schedule_by_criteria(
    db: Session,
    user_id: str,
    target_date: Optional[date] = None,
    workout_name_fragment: Optional[str] = None,
    week_start: Optional[date] = None
) -> List[Schedule]:
    """
    Find schedule entries matching criteria.
    Helper for voice agent to locate workouts by natural language.

    Args:
        db: Database session
        user_id: User's UUID
        target_date: Specific date (optional)
        workout_name_fragment: Partial workout name (e.g., "leg", "upper")
        week_start: Start of week to search within (optional)

    Returns:
        List of matching Schedule entries
    """
    query = db.query(Schedule).join(Workout).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    )

    if target_date:
        query = query.filter(Schedule.scheduled_date == target_date)

    if week_start:
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            and_(
                Schedule.scheduled_date >= week_start,
                Schedule.scheduled_date <= week_end
            )
        )

    if workout_name_fragment:
        query = query.filter(Workout.name.ilike(f"%{workout_name_fragment}%"))

    return query.order_by(Schedule.scheduled_date).all()
