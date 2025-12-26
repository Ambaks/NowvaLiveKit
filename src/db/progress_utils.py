"""
Database utility functions for progress tracking and logging
Handles ProgressLog creation and workout performance analysis
"""
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, desc

from .models import ProgressLog, Set, Exercise, WorkoutExercise, Workout


def log_completed_set(
    db: Session,
    user_id: str,
    set_id: int,
    performed_reps: int,
    performed_weight: Optional[float] = None,
    rpe: Optional[float] = None,
    measured_velocity: Optional[float] = None,
    velocity_loss: Optional[float] = None,
    notes: Optional[str] = None
) -> ProgressLog:
    """
    Create a ProgressLog entry for a completed set.
    Logs set immediately for data safety.

    Args:
        db: Database session
        user_id: User's UUID as string
        set_id: Set ID from the workout
        performed_reps: Actual reps completed
        performed_weight: Actual weight used (kg or lbs)
        rpe: Rate of Perceived Exertion (1-10)
        measured_velocity: Bar velocity in m/s (from pose estimation)
        velocity_loss: Velocity loss percentage in the set
        notes: Optional notes about the set

    Returns:
        Created ProgressLog object
    """
    progress = ProgressLog(
        user_id=user_id,
        set_id=set_id,
        performed_reps=performed_reps,
        performed_weight=Decimal(str(performed_weight)) if performed_weight else None,
        rpe=Decimal(str(rpe)) if rpe else None,
        measured_velocity=Decimal(str(measured_velocity)) if measured_velocity else None,
        velocity_loss=Decimal(str(velocity_loss)) if velocity_loss else None,
        completed_at=datetime.utcnow()
    )

    db.add(progress)
    db.commit()
    db.refresh(progress)

    return progress


def get_set_history(
    db: Session,
    user_id: str,
    set_id: int,
    limit: int = 10
) -> List[ProgressLog]:
    """
    Get the history of a specific set across workouts.
    Useful for tracking progress on a particular exercise/set combination.

    Args:
        db: Database session
        user_id: User's UUID as string
        set_id: Set ID
        limit: Maximum number of entries to return

    Returns:
        List of ProgressLog entries, most recent first
    """
    logs = db.query(ProgressLog).filter(
        and_(
            ProgressLog.user_id == user_id,
            ProgressLog.set_id == set_id
        )
    ).order_by(desc(ProgressLog.completed_at)).limit(limit).all()

    return logs


def get_exercise_progress(
    db: Session,
    user_id: str,
    exercise_name: str,
    days_back: int = 90
) -> List[Dict]:
    """
    Get all progress logs for a specific exercise over time.
    Aggregates across all sets of that exercise.

    Args:
        db: Database session
        user_id: User's UUID as string
        exercise_name: Name of the exercise
        days_back: How many days back to look

    Returns:
        List of progress entries with context
        [
            {
                "date": "2025-01-15",
                "reps": 5,
                "weight": 225.0,
                "rpe": 8.0,
                "velocity": 0.65,
                "set_number": 1,
                "workout_name": "Upper Push"
            },
            ...
        ]
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)

    # Complex query joining through the relationships
    results = db.query(
        ProgressLog,
        Set,
        WorkoutExercise,
        Exercise,
        Workout
    ).join(
        Set, ProgressLog.set_id == Set.id
    ).join(
        WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id
    ).join(
        Exercise, WorkoutExercise.exercise_id == Exercise.id
    ).join(
        Workout, WorkoutExercise.workout_id == Workout.id
    ).filter(
        and_(
            ProgressLog.user_id == user_id,
            Exercise.name == exercise_name,
            ProgressLog.completed_at >= cutoff_date
        )
    ).order_by(desc(ProgressLog.completed_at)).all()

    progress_data = []
    for log, set_obj, we, exercise, workout in results:
        progress_data.append({
            "date": log.completed_at.date().isoformat(),
            "completed_at": log.completed_at.isoformat(),
            "reps": log.performed_reps,
            "weight": float(log.performed_weight) if log.performed_weight else None,
            "rpe": float(log.rpe) if log.rpe else None,
            "velocity": float(log.measured_velocity) if log.measured_velocity else None,
            "velocity_loss": float(log.velocity_loss) if log.velocity_loss else None,
            "set_number": set_obj.set_number,
            "workout_name": workout.name,
            "week_number": workout.week_number,
            "day_number": workout.day_number
        })

    return progress_data


def get_workout_session_logs(
    db: Session,
    user_id: str,
    workout_id: int,
    session_date: Optional[date] = None
) -> List[Dict]:
    """
    Get all progress logs for a specific workout session.
    If session_date not provided, gets the most recent session.

    Args:
        db: Database session
        user_id: User's UUID as string
        workout_id: Workout ID
        session_date: Optional specific date to query

    Returns:
        List of progress logs for that workout session
    """
    if session_date is None:
        session_date = date.today()

    # Get all sets for this workout
    workout_exercise_ids = db.query(WorkoutExercise.id).filter(
        WorkoutExercise.workout_id == workout_id
    ).all()
    workout_exercise_ids = [we[0] for we in workout_exercise_ids]

    set_ids = db.query(Set.id).filter(
        Set.workout_exercise_id.in_(workout_exercise_ids)
    ).all()
    set_ids = [s[0] for s in set_ids]

    # Get progress logs for those sets on this date
    start_datetime = datetime.combine(session_date, datetime.min.time())
    end_datetime = datetime.combine(session_date, datetime.max.time())

    logs = db.query(ProgressLog).options(
        joinedload(ProgressLog.set).joinedload(Set.workout_exercise).joinedload(WorkoutExercise.exercise)
    ).filter(
        and_(
            ProgressLog.user_id == user_id,
            ProgressLog.set_id.in_(set_ids),
            ProgressLog.completed_at >= start_datetime,
            ProgressLog.completed_at <= end_datetime
        )
    ).order_by(ProgressLog.completed_at).all()

    result = []
    for log in logs:
        exercise_name = log.set.workout_exercise.exercise.name if log.set.workout_exercise.exercise else "Unknown"
        result.append({
            "progress_log_id": log.id,
            "exercise_name": exercise_name,
            "set_number": log.set.set_number,
            "performed_reps": log.performed_reps,
            "performed_weight": float(log.performed_weight) if log.performed_weight else None,
            "rpe": float(log.rpe) if log.rpe else None,
            "measured_velocity": float(log.measured_velocity) if log.measured_velocity else None,
            "completed_at": log.completed_at.isoformat()
        })

    return result


def calculate_estimated_1rm(weight: float, reps: int) -> Optional[float]:
    """
    Calculate estimated 1RM using Epley formula.
    1RM = weight × (1 + reps/30)

    Args:
        weight: Weight lifted
        reps: Reps completed

    Returns:
        Estimated 1RM or None if invalid inputs
    """
    if weight <= 0 or reps <= 0:
        return None

    if reps == 1:
        return weight

    # Epley formula
    estimated_1rm = weight * (1 + reps / 30.0)

    return round(estimated_1rm, 2)


def get_personal_records(
    db: Session,
    user_id: str,
    exercise_name: Optional[str] = None
) -> List[Dict]:
    """
    Get personal records for user.
    If exercise_name provided, returns PRs for that exercise.
    Otherwise, returns PRs for all exercises.

    Args:
        db: Database session
        user_id: User's UUID as string
        exercise_name: Optional exercise name filter

    Returns:
        List of PR records
        [
            {
                "exercise_name": "Back Squat",
                "max_weight": 315.0,
                "reps": 5,
                "estimated_1rm": 365.0,
                "date": "2025-01-15"
            },
            ...
        ]
    """
    # Join through relationships to get exercise names
    query = db.query(
        Exercise.name,
        func.max(ProgressLog.performed_weight).label('max_weight'),
        ProgressLog.performed_reps,
        ProgressLog.completed_at
    ).join(
        Set, ProgressLog.set_id == Set.id
    ).join(
        WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id
    ).join(
        Exercise, WorkoutExercise.exercise_id == Exercise.id
    ).filter(
        and_(
            ProgressLog.user_id == user_id,
            ProgressLog.performed_weight.isnot(None)
        )
    )

    if exercise_name:
        query = query.filter(Exercise.name == exercise_name)

    query = query.group_by(
        Exercise.name,
        ProgressLog.performed_reps,
        ProgressLog.completed_at
    ).order_by(
        Exercise.name,
        desc('max_weight')
    )

    results = query.all()

    # Process results to get best PR per exercise
    prs = {}
    for exercise, weight, reps, completed_at in results:
        if exercise not in prs:
            estimated_1rm = calculate_estimated_1rm(float(weight), reps)
            prs[exercise] = {
                "exercise_name": exercise,
                "max_weight": float(weight),
                "reps": reps,
                "estimated_1rm": estimated_1rm,
                "date": completed_at.date().isoformat()
            }
        else:
            # Check if this is a better PR (higher estimated 1RM)
            current_estimated = prs[exercise]["estimated_1rm"]
            new_estimated = calculate_estimated_1rm(float(weight), reps)

            if new_estimated and (current_estimated is None or new_estimated > current_estimated):
                prs[exercise] = {
                    "exercise_name": exercise,
                    "max_weight": float(weight),
                    "reps": reps,
                    "estimated_1rm": new_estimated,
                    "date": completed_at.date().isoformat()
                }

    return list(prs.values())


def calculate_velocity_loss_for_set(
    db: Session,
    user_id: str,
    set_id: int,
    session_date: Optional[date] = None
) -> Optional[float]:
    """
    Calculate velocity loss within a set.
    Velocity loss = (first_rep_velocity - last_rep_velocity) / first_rep_velocity * 100

    Note: This requires rep-by-rep velocity tracking, which isn't in the current schema.
    For now, this returns None but can be implemented when pose estimation adds per-rep velocity.

    Args:
        db: Database session
        user_id: User's UUID as string
        set_id: Set ID
        session_date: Optional session date

    Returns:
        Velocity loss percentage or None
    """
    # TODO: Implement when per-rep velocity tracking is added
    # Current schema only has measured_velocity (average or single value)
    return None


def get_workout_completion_rate(
    db: Session,
    user_id: str,
    days_back: int = 30
) -> Dict:
    """
    Calculate workout completion rate over the last N days.

    Args:
        db: Database session
        user_id: User's UUID as string
        days_back: Number of days to analyze

    Returns:
        Dict with completion statistics
        {
            "total_scheduled": 12,
            "total_completed": 10,
            "completion_rate": 0.83,
            "missed_workouts": 2
        }
    """
    from .models import Schedule

    cutoff_date = date.today() - timedelta(days=days_back)

    # Get all scheduled workouts in the period
    total_scheduled = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= cutoff_date,
            Schedule.scheduled_date < date.today()  # Don't count future workouts
        )
    ).count()

    # Get completed workouts
    total_completed = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= cutoff_date,
            Schedule.scheduled_date < date.today(),
            Schedule.completed == True
        )
    ).count()

    missed = total_scheduled - total_completed
    rate = total_completed / total_scheduled if total_scheduled > 0 else 0.0

    return {
        "total_scheduled": total_scheduled,
        "total_completed": total_completed,
        "completion_rate": round(rate, 2),
        "missed_workouts": missed,
        "period_days": days_back
    }


def get_recent_activity_summary(
    db: Session,
    user_id: str,
    days_back: int = 7
) -> Dict:
    """
    Get a summary of recent workout activity.

    Args:
        db: Database session
        user_id: User's UUID as string
        days_back: Number of days to look back

    Returns:
        Dict with activity summary
        {
            "total_sets": 45,
            "total_reps": 225,
            "total_volume": 12500.0,  # weight × reps sum
            "unique_exercises": 8,
            "workouts_completed": 3,
            "average_rpe": 7.5
        }
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)

    logs = db.query(ProgressLog).filter(
        and_(
            ProgressLog.user_id == user_id,
            ProgressLog.completed_at >= cutoff_date
        )
    ).all()

    if not logs:
        return {
            "total_sets": 0,
            "total_reps": 0,
            "total_volume": 0.0,
            "unique_exercises": 0,
            "workouts_completed": 0,
            "average_rpe": None
        }

    total_sets = len(logs)
    total_reps = sum(log.performed_reps for log in logs)
    total_volume = sum(
        (float(log.performed_weight) * log.performed_reps)
        for log in logs
        if log.performed_weight
    )

    # Get unique exercises
    unique_exercises = db.query(func.count(func.distinct(Exercise.id))).join(
        WorkoutExercise, Exercise.id == WorkoutExercise.exercise_id
    ).join(
        Set, WorkoutExercise.id == Set.workout_exercise_id
    ).join(
        ProgressLog, Set.id == ProgressLog.set_id
    ).filter(
        and_(
            ProgressLog.user_id == user_id,
            ProgressLog.completed_at >= cutoff_date
        )
    ).scalar() or 0

    # Calculate average RPE (exclude None values)
    rpe_values = [float(log.rpe) for log in logs if log.rpe]
    average_rpe = sum(rpe_values) / len(rpe_values) if rpe_values else None

    # Count unique workout days
    unique_dates = len(set(log.completed_at.date() for log in logs))

    return {
        "total_sets": total_sets,
        "total_reps": total_reps,
        "total_volume": round(total_volume, 2),
        "unique_exercises": unique_exercises,
        "workouts_completed": unique_dates,
        "average_rpe": round(average_rpe, 1) if average_rpe else None,
        "period_days": days_back
    }
