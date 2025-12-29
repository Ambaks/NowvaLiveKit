"""
Recovery analysis and automatic rest day suggestions.

Analyzes upcoming schedule for muscle group overlap and recovery issues.
Provides intelligent rest day recommendations based on workout composition.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .models import Schedule, Workout
from .schedule_utils import is_sufficient_rest_between_workouts, add_rest_day


# Configuration
DEFAULT_OVERLAP_THRESHOLD = 0.30  # 30% muscle group overlap
HIGH_OVERLAP_THRESHOLD = 0.50     # 50% = high priority
ANALYSIS_DAYS_AHEAD = 14          # Analyze next 2 weeks


def analyze_schedule_recovery(
    db: Session,
    user_id: str,
    days_ahead: int = ANALYSIS_DAYS_AHEAD,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD
) -> Dict:
    """
    Analyze upcoming schedule for recovery issues.

    Args:
        db: Database session
        user_id: User UUID
        days_ahead: How many days ahead to analyze (default: 14)
        overlap_threshold: Muscle group overlap threshold (default: 0.30)

    Returns:
        {
            "needs_rest_days": bool,
            "quality_score": float (0-100),
            "warnings": List[str],
            "recommendations": List[Dict],
            "analysis_summary": str
        }

    Example:
        >>> result = analyze_schedule_recovery(db, user_id)
        >>> print(result["quality_score"])
        75.5
        >>> print(result["recommendations"][0])
        {
            "date": date(2025, 12, 31),
            "reason": "High overlap (60%) between Leg Day and Lower Power",
            "priority": "high",
            "workouts_affected": ["Leg Day on Dec 30", "Lower Power on Dec 31"]
        }
    """
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    # Get upcoming schedule
    upcoming = db.query(Schedule).filter(
        and_(
            Schedule.user_id == user_id,
            Schedule.scheduled_date >= today,
            Schedule.scheduled_date <= end_date,
            Schedule.completed == False,
            Schedule.skipped == False
        )
    ).order_by(Schedule.scheduled_date).all()

    if len(upcoming) < 2:
        return {
            "needs_rest_days": False,
            "quality_score": 100.0,
            "warnings": [],
            "recommendations": [],
            "analysis_summary": "Not enough upcoming workouts to analyze recovery needs."
        }

    warnings = []
    recommendations = []
    violations = 0
    total_transitions = 0

    # Analyze consecutive workout days
    for i in range(len(upcoming) - 1):
        current = upcoming[i]
        next_workout = upcoming[i + 1]

        # Calculate days between
        days_between = (next_workout.scheduled_date - current.scheduled_date).days

        # Only analyze back-to-back or 1-day-apart workouts
        if days_between <= 1:
            total_transitions += 1

            # Check muscle group overlap
            has_sufficient_rest = is_sufficient_rest_between_workouts(
                db, current.workout_id, next_workout.workout_id,
                threshold=overlap_threshold
            )

            if not has_sufficient_rest:
                violations += 1

                # Determine priority based on overlap severity
                # Check with higher threshold to see if it's critical
                is_critical = not is_sufficient_rest_between_workouts(
                    db, current.workout_id, next_workout.workout_id,
                    threshold=HIGH_OVERLAP_THRESHOLD
                )

                priority = "high" if is_critical else "medium"

                current_name = current.workout.name if current.workout else "workout"
                next_name = next_workout.workout.name if next_workout.workout else "workout"

                # Calculate approximate overlap percentage for display
                overlap_pct = int((1 - overlap_threshold) * 100)

                recommendation = {
                    "date": next_workout.scheduled_date,
                    "reason": f"Muscle group overlap between {current_name} and {next_name}",
                    "priority": priority,
                    "workouts_affected": [
                        f"{current_name} on {current.scheduled_date.strftime('%b %d')}",
                        f"{next_name} on {next_workout.scheduled_date.strftime('%b %d')}"
                    ],
                    "suggested_action": f"Add rest day on {next_workout.scheduled_date.strftime('%b %d')}, shift {next_name} forward"
                }

                recommendations.append(recommendation)

                warning = f"⚠️  {current_name} ({current.scheduled_date.strftime('%b %d')}) → {next_name} ({next_workout.scheduled_date.strftime('%b %d')}): Insufficient recovery"
                warnings.append(warning)

    # Calculate quality score (0-100)
    if total_transitions == 0:
        quality_score = 100.0
    else:
        quality_score = 100.0 * (1 - (violations / total_transitions))

    # Determine if rest days are needed
    needs_rest_days = quality_score < 80.0

    # Generate summary
    if quality_score >= 90:
        summary = f"Your schedule looks excellent! Quality score: {quality_score:.1f}/100. Great muscle group separation."
    elif quality_score >= 70:
        summary = f"Pretty good schedule. Quality score: {quality_score:.1f}/100. A few areas could be optimized for better recovery."
    else:
        summary = f"I see some recovery concerns. Quality score: {quality_score:.1f}/100. Consider adding rest days to improve recovery."

    return {
        "needs_rest_days": needs_rest_days,
        "quality_score": quality_score,
        "warnings": warnings,
        "recommendations": recommendations,
        "analysis_summary": summary
    }


def get_next_recommended_rest_day(
    db: Session,
    user_id: str,
    days_ahead: int = ANALYSIS_DAYS_AHEAD
) -> Optional[Dict]:
    """
    Get the next most urgent rest day recommendation.

    Args:
        db: Database session
        user_id: User UUID
        days_ahead: Days ahead to analyze

    Returns:
        Most urgent recommendation dict or None if no recommendations
    """
    analysis = analyze_schedule_recovery(db, user_id, days_ahead=days_ahead)

    if not analysis["recommendations"]:
        return None

    # Sort by priority (high first) and date (soonest first)
    recommendations = sorted(
        analysis["recommendations"],
        key=lambda r: (r["priority"] != "high", r["date"])
    )

    return recommendations[0]


def apply_rest_day_recommendation(
    db: Session,
    user_id: str,
    recommendation: Dict,
    shift_future_workouts: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Apply a rest day recommendation from analysis.

    Args:
        db: Database session
        user_id: User UUID
        recommendation: Recommendation dict from analyze_schedule_recovery()
        shift_future_workouts: Whether to shift future workouts (default: True)

    Returns:
        (success: bool, error_message: Optional[str])
    """
    rest_date = recommendation["date"]

    # Use existing add_rest_day function
    success, error, shifted_count = add_rest_day(
        db, user_id, rest_date, shift_future_workouts=shift_future_workouts
    )

    if not success:
        return (False, error)

    return (True, None)


def apply_all_recommended_rest_days(
    db: Session,
    user_id: str,
    max_rest_days: int = 3,
    shift_future_workouts: bool = True
) -> Tuple[bool, Optional[str], int]:
    """
    Apply multiple rest day recommendations at once.

    Args:
        db: Database session
        user_id: User UUID
        max_rest_days: Maximum number of rest days to add (default: 3)
        shift_future_workouts: Whether to shift future workouts

    Returns:
        (success: bool, error_message: Optional[str], rest_days_added: int)
    """
    analysis = analyze_schedule_recovery(db, user_id)

    if not analysis["recommendations"]:
        return (False, "No rest days needed - your schedule looks good!", 0)

    # Sort by priority and date
    recommendations = sorted(
        analysis["recommendations"],
        key=lambda r: (r["priority"] != "high", r["date"])
    )

    # Limit to max_rest_days
    recommendations = recommendations[:max_rest_days]

    added_count = 0
    errors = []

    for rec in recommendations:
        success, error = apply_rest_day_recommendation(
            db, user_id, rec, shift_future_workouts=shift_future_workouts
        )

        if success:
            added_count += 1
        else:
            errors.append(f"{rec['date'].strftime('%b %d')}: {error}")

    if added_count == 0:
        return (False, "; ".join(errors), 0)

    if errors:
        return (True, f"Added {added_count} rest days. Some failed: {'; '.join(errors)}", added_count)

    return (True, None, added_count)


def format_recommendation_for_display(recommendation: Dict) -> str:
    """
    Format a recommendation for user-friendly display.

    Args:
        recommendation: Recommendation dict

    Returns:
        Formatted string

    Example:
        >>> format_recommendation_for_display(rec)
        "🔴 HIGH PRIORITY: Add rest day on Dec 31\\n  Reason: Muscle group overlap between Leg Day and Lower Power\\n  Affected: Leg Day on Dec 30, Lower Power on Dec 31"
    """
    priority_emoji = "🔴" if recommendation["priority"] == "high" else "🟡"
    priority_text = recommendation["priority"].upper()
    date_str = recommendation["date"].strftime("%b %d")
    reason = recommendation["reason"]
    affected = ", ".join(recommendation["workouts_affected"])

    return f"{priority_emoji} {priority_text}: Add rest day on {date_str}\n  Reason: {reason}\n  Affected: {affected}"
