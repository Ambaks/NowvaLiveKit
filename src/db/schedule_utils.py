"""
Database utility functions for workout scheduling
Handles schedule creation, retrieval, and smart rest day allocation
"""
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from .models import Schedule, Workout, WorkoutExercise, Exercise, Set, UserGeneratedProgram, PartnerProgram


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
