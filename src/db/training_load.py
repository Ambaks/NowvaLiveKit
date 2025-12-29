"""
Training load monitoring and deload week recommendations.

Tracks weekly training metrics (volume, intensity, velocity) and calculates
fatigue scores to recommend optimal deload timing.
"""
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from .models import (
    TrainingLoadMetrics, DeloadHistory, ProgressLog,
    Schedule, Set, WorkoutExercise, User
)
from .schedule_utils import apply_deload_week


# Configuration
FATIGUE_SCORE_THRESHOLD = 75.0
HIGH_RPE_THRESHOLD = 8.0
VELOCITY_DECLINE_THRESHOLD = 10.0
MIN_WEEKS_BETWEEN_DELOADS = 3
BASELINE_VELOCITY_WEEKS = 4


def get_week_bounds(target_date: date) -> Tuple[date, date]:
    """Get Monday-Sunday bounds for the week containing target_date"""
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def calculate_weekly_training_load(
    db: Session,
    user_id: str,
    week_start: date
) -> Optional[TrainingLoadMetrics]:
    """
    Calculate and store training load metrics for a specific week.

    Args:
        db: Database session
        user_id: User UUID
        week_start: Start of week (Monday)

    Returns:
        TrainingLoadMetrics object or None if no data

    Algorithm:
    1. Get all completed schedules for the week
    2. Aggregate ProgressLog data (volume, RPE, velocity)
    3. Calculate fatigue score
    4. Store in training_load_metrics table
    """
    week_end = week_start + timedelta(days=6)

    # Get completed schedules for the week
    completed_schedules = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= week_start,
            Schedule.scheduled_date <= week_end,
            Schedule.completed == True
        )
    ).all()

    if not completed_schedules:
        return None

    # Aggregate metrics from ProgressLog
    total_sets = 0
    total_reps = 0
    total_volume = 0.0
    rpe_values = []
    high_rpe_count = 0
    velocity_values = []

    for schedule in completed_schedules:
        # Get progress logs for this workout
        logs = db.query(ProgressLog).join(Set).join(WorkoutExercise).join(Schedule).filter(
            Schedule.id == schedule.id
        ).all()

        for log in logs:
            total_sets += 1
            if log.performed_reps:
                total_reps += log.performed_reps
            if log.performed_weight:
                total_volume += float(log.performed_weight * (log.performed_reps or 0))
            if log.rpe:
                rpe_values.append(float(log.rpe))
                if log.rpe >= HIGH_RPE_THRESHOLD:
                    high_rpe_count += 1
            if log.measured_velocity:
                velocity_values.append(float(log.measured_velocity))

    # Calculate averages
    avg_rpe = sum(rpe_values) / len(rpe_values) if rpe_values else None
    avg_velocity = sum(velocity_values) / len(velocity_values) if velocity_values else None

    # Get baseline velocity for comparison
    baseline_velocity = get_baseline_velocity(db, user_id)
    velocity_decline = None
    if avg_velocity and baseline_velocity:
        velocity_decline = ((baseline_velocity - avg_velocity) / baseline_velocity) * 100

    # Get volume trend
    volume_trend = get_volume_trend(db, user_id, week_start)

    # Calculate fatigue score
    fatigue_score = calculate_fatigue_score(
        avg_rpe=avg_rpe,
        high_rpe_ratio=high_rpe_count / total_sets if total_sets > 0 else 0,
        velocity_decline=velocity_decline,
        volume_trend=volume_trend
    )

    # Check existing metrics for this week
    existing = db.query(TrainingLoadMetrics).filter(
        and_(
            TrainingLoadMetrics.user_id == user_id,
            TrainingLoadMetrics.week_start_date == week_start
        )
    ).first()

    if existing:
        # Update existing
        existing.total_sets = total_sets
        existing.total_reps = total_reps
        existing.total_volume_kg = total_volume
        existing.avg_rpe = avg_rpe
        existing.high_rpe_sets = high_rpe_count
        existing.avg_velocity = avg_velocity
        existing.velocity_decline_percent = velocity_decline
        existing.fatigue_score = fatigue_score
        existing.deload_recommended = fatigue_score >= FATIGUE_SCORE_THRESHOLD
        existing.workouts_completed = len(completed_schedules)
        existing.calculated_at = datetime.utcnow()
        metrics = existing
    else:
        # Create new
        metrics = TrainingLoadMetrics(
            user_id=user_id,
            week_start_date=week_start,
            week_end_date=week_end,
            total_sets=total_sets,
            total_reps=total_reps,
            total_volume_kg=total_volume,
            avg_rpe=avg_rpe,
            high_rpe_sets=high_rpe_count,
            avg_velocity=avg_velocity,
            velocity_decline_percent=velocity_decline,
            fatigue_score=fatigue_score,
            deload_recommended=fatigue_score >= FATIGUE_SCORE_THRESHOLD,
            workouts_completed=len(completed_schedules)
        )
        db.add(metrics)

    db.commit()
    db.refresh(metrics)

    return metrics


def calculate_fatigue_score(
    avg_rpe: Optional[float],
    high_rpe_ratio: float,
    velocity_decline: Optional[float],
    volume_trend: Optional[float]
) -> float:
    """
    Calculate composite fatigue score (0-100) from multiple signals.

    Weights:
    - 40%: Average RPE (normalized to 0-100)
    - 20%: High RPE ratio (sets with RPE ≥ 8)
    - 25%: Velocity decline from baseline
    - 15%: Volume trend (increasing = more fatigue)

    Args:
        avg_rpe: Average RPE for the week (0-10)
        high_rpe_ratio: Ratio of sets with RPE ≥ 8 (0-1)
        velocity_decline: Percent decline from baseline (0-100)
        volume_trend: Percent change vs 3-week average (negative or positive)

    Returns:
        Fatigue score (0-100), higher = more fatigued
    """
    score = 0.0
    components_used = 0

    # Component 1: Average RPE (40% weight)
    if avg_rpe is not None:
        # Normalize RPE from 0-10 scale to 0-100
        rpe_score = (avg_rpe / 10.0) * 100
        score += rpe_score * 0.40
        components_used += 0.40

    # Component 2: High RPE ratio (20% weight)
    high_rpe_score = high_rpe_ratio * 100
    score += high_rpe_score * 0.20
    components_used += 0.20

    # Component 3: Velocity decline (25% weight)
    if velocity_decline is not None:
        # Cap at 100% decline
        velocity_score = min(velocity_decline, 100.0)
        score += velocity_score * 0.25
        components_used += 0.25

    # Component 4: Volume trend (15% weight)
    if volume_trend is not None:
        # Positive trend (increasing volume) = more fatigue
        # Normalize: +20% volume = 100 fatigue points
        volume_score = min(max((volume_trend / 20.0) * 100, 0), 100)
        score += volume_score * 0.15
        components_used += 0.15

    # Normalize by components actually used
    if components_used > 0:
        score = score / components_used * 1.0  # Scale back to full weight

    return round(score, 2)


def get_baseline_velocity(db: Session, user_id: str) -> Optional[float]:
    """
    Get baseline velocity from first 4 weeks of training.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Average velocity from baseline period or None
    """
    # Get first 4 weeks of metrics
    baseline_metrics = db.query(TrainingLoadMetrics).filter(
        TrainingLoadMetrics.user_id == user_id
    ).order_by(TrainingLoadMetrics.week_start_date).limit(BASELINE_VELOCITY_WEEKS).all()

    if not baseline_metrics:
        return None

    velocities = [m.avg_velocity for m in baseline_metrics if m.avg_velocity]

    if not velocities:
        return None

    return sum(velocities) / len(velocities)


def get_volume_trend(db: Session, user_id: str, current_week_start: date) -> Optional[float]:
    """
    Calculate volume trend vs 3-week average.

    Args:
        db: Database session
        user_id: User UUID
        current_week_start: Start of current week

    Returns:
        Percent change vs 3-week average (e.g., 15.5 = 15.5% increase)
    """
    # Get current week metrics
    current_metrics = db.query(TrainingLoadMetrics).filter(
        and_(
            TrainingLoadMetrics.user_id == user_id,
            TrainingLoadMetrics.week_start_date == current_week_start
        )
    ).first()

    if not current_metrics or not current_metrics.total_volume_kg:
        return None

    # Get previous 3 weeks
    three_weeks_ago = current_week_start - timedelta(weeks=3)
    previous_metrics = db.query(TrainingLoadMetrics).filter(
        and_(
            TrainingLoadMetrics.user_id == user_id,
            TrainingLoadMetrics.week_start_date >= three_weeks_ago,
            TrainingLoadMetrics.week_start_date < current_week_start
        )
    ).all()

    if not previous_metrics:
        return None

    volumes = [float(m.total_volume_kg) for m in previous_metrics if m.total_volume_kg]

    if not volumes:
        return None

    avg_volume = sum(volumes) / len(volumes)
    current_volume = float(current_metrics.total_volume_kg)

    percent_change = ((current_volume - avg_volume) / avg_volume) * 100

    return round(percent_change, 2)


def check_deload_recommendation(
    db: Session,
    user_id: str
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Check if user needs a deload week based on training load.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        (needs_deload: bool, recommendation: Optional[Dict], reason: Optional[str])

    Criteria for deload recommendation:
    1. Fatigue score ≥ 75
    2. Velocity decline ≥ 10%
    3. Sustained high RPE (2+ weeks at RPE ≥ 8)
    4. Time-based (6+ weeks since last deload)
    """
    # Get most recent metrics
    latest_metrics = db.query(TrainingLoadMetrics).filter(
        TrainingLoadMetrics.user_id == user_id
    ).order_by(desc(TrainingLoadMetrics.week_start_date)).first()

    if not latest_metrics:
        return (False, None, "No training data available")

    # Check last deload
    last_deload = db.query(DeloadHistory).filter(
        and_(
            DeloadHistory.user_id == user_id,
            DeloadHistory.applied == True
        )
    ).order_by(desc(DeloadHistory.applied_at)).first()

    if last_deload:
        weeks_since_deload = (date.today() - last_deload.week_start_date).days // 7
        if weeks_since_deload < MIN_WEEKS_BETWEEN_DELOADS:
            return (False, None, f"Too soon - only {weeks_since_deload} weeks since last deload")
    else:
        weeks_since_deload = None

    # Criteria checks
    reasons = []

    # 1. Fatigue score
    if latest_metrics.fatigue_score and latest_metrics.fatigue_score >= FATIGUE_SCORE_THRESHOLD:
        reasons.append(f"High fatigue score ({latest_metrics.fatigue_score:.1f}/100)")

    # 2. Velocity decline
    if latest_metrics.velocity_decline_percent and latest_metrics.velocity_decline_percent >= VELOCITY_DECLINE_THRESHOLD:
        reasons.append(f"Velocity decline ({latest_metrics.velocity_decline_percent:.1f}%)")

    # 3. Sustained high RPE (2+ weeks)
    high_rpe_weeks = db.query(TrainingLoadMetrics).filter(
        and_(
            TrainingLoadMetrics.user_id == user_id,
            TrainingLoadMetrics.avg_rpe >= HIGH_RPE_THRESHOLD
        )
    ).order_by(desc(TrainingLoadMetrics.week_start_date)).limit(2).all()

    if len(high_rpe_weeks) >= 2:
        reasons.append(f"Sustained high RPE ({len(high_rpe_weeks)} weeks)")

    # 4. Time-based
    if weeks_since_deload and weeks_since_deload >= 6:
        reasons.append(f"Time for planned deload ({weeks_since_deload} weeks since last)")

    if not reasons:
        return (False, None, "No deload indicators detected")

    # Recommend deload for next week
    next_week_start, next_week_end = get_week_bounds(date.today() + timedelta(weeks=1))

    recommendation = {
        "week_start": next_week_start,
        "week_end": next_week_end,
        "intensity_modifier": 0.7,
        "trigger_reasons": reasons,
        "fatigue_score": float(latest_metrics.fatigue_score) if latest_metrics.fatigue_score else None
    }

    reason_text = "; ".join(reasons)

    return (True, recommendation, reason_text)


def apply_deload_recommendation(
    db: Session,
    user_id: str,
    recommendation: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Apply a deload week recommendation.

    Args:
        db: Database session
        user_id: User UUID
        recommendation: Recommendation dict from check_deload_recommendation()

    Returns:
        (success: bool, error_message: Optional[str])
    """
    week_start = recommendation["week_start"]
    intensity_modifier = recommendation["intensity_modifier"]

    # Apply deload to schedule
    success, error, modified_count = apply_deload_week(
        db, user_id, week_start, intensity_modifier=intensity_modifier
    )

    if not success:
        return (False, error)

    # Log to deload history
    deload_entry = DeloadHistory(
        user_id=user_id,
        week_start_date=week_start,
        week_end_date=recommendation["week_end"],
        intensity_modifier=intensity_modifier,
        trigger_reason="; ".join(recommendation["trigger_reasons"]),
        fatigue_score_at_trigger=recommendation.get("fatigue_score"),
        applied=True,
        applied_at=datetime.utcnow()
    )

    db.add(deload_entry)
    db.commit()

    return (True, None)
