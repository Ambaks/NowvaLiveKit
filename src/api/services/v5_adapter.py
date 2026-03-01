"""
V5 Adapter Module

Converts between API request format and V5 program generator formats.
"""

from typing import Dict, Any, Tuple, Optional
from ..models.requests import ProgramGenerationRequest


def convert_request_to_v5_input(request: ProgramGenerationRequest) -> Dict[str, Any]:
    """
    Convert API ProgramGenerationRequest to V5 AthleteProfile input dict.

    Args:
        request: API request from voice agent or website

    Returns:
        Dict suitable for passing to generate_program_v5()
    """
    # Map goal_category to V5 training_goal
    goal_mapping = {
        "power": "power",
        "strength": "strength",
        "hypertrophy": "hypertrophy",
        "athletic_performance": "power",  # Map to power for athletic goals
    }
    training_goal = goal_mapping.get(request.goal_category, "hypertrophy")

    # Parse injury_history string into injuries list
    injuries = []
    if request.injury_history and request.injury_history.lower() not in ("none", "no", "n/a", ""):
        # Simple parsing - create an injury entry
        injuries.append({
            "area": "general",
            "description": request.injury_history,
            "avoid": [],  # V5 will handle avoidance through filtering
        })

    # Determine sport
    sport = None
    if request.specific_sport and request.specific_sport.lower() not in ("none", "no", "n/a", "general", ""):
        sport = request.specific_sport.lower()

    # Map sex format
    sex = request.sex.upper() if request.sex else None
    if sex in ("MALE", "M"):
        sex = "M"
    elif sex in ("FEMALE", "F"):
        sex = "F"

    return {
        "user_id": str(request.user_id),
        "name": request.name,
        "age": request.age,
        "sex": sex,
        "body_weight_kg": request.weight_kg,
        "training_goal": training_goal,
        "training_level": request.fitness_level,
        "program_duration_weeks": request.duration_weeks,
        "training_days_per_week": request.days_per_week,
        "session_duration_minutes": request.session_duration or 60,
        "equipment_tier": 2,  # Default to Tier 2 (dumbbells available)
        "injuries": injuries,
        "exercises_to_avoid": [],
        "exercises_to_include": [],
        "recovery_capacity": "normal",
        "weak_points": [],
        "sport": sport,
    }


def convert_v5_output_to_html_format(
    v5_output: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Convert V5 serialized output to HTML generator format.

    Args:
        v5_output: Output from serialize_to_v3()
        user_data: Optional user data for cover page

    Returns:
        (program_data, user_data) tuple for html_generator.generate_html()
    """
    overview = v5_output.get("overview", {})
    athlete = v5_output.get("athlete", {})

    # Build program_data in HTML generator format
    program_data = {
        "id": v5_output.get("program_id", ""),
        "program_name": overview.get("name", "Workout Program"),
        "description": overview.get("description", ""),
        "duration_weeks": overview.get("duration_weeks", 4),
        "goal": overview.get("training_goal", overview.get("effective_goal", "hypertrophy")),
        "progression_strategy": overview.get("periodization_model", "progressive_overload"),
        "overall_notes": f"Split: {overview.get('split_name', 'Upper/Lower')}. " +
                        f"Periodization: {overview.get('periodization_model', 'volume_ramp').replace('_', ' ').title()}.",
        "vbt_enabled": False,
        "vbt_setup_notes": None,
        "deload_schedule": None,
        "injury_accommodations": None,
        "weeks": [],
    }

    # Convert weeks
    for week in v5_output.get("weeks", []):
        week_dict = {
            "week_number": week.get("week_number", 1),
            "phase": week.get("phase", "Building"),
            "notes": None,
            "workouts": [],
        }

        for workout in week.get("workouts", []):
            workout_dict = {
                "day_number": workout.get("day_number", 1),
                "name": workout.get("day_label", "Workout"),
                "description": f"Estimated duration: {workout.get('estimated_duration_minutes', 60)} minutes",
                "exercises": [],
            }

            for exercise in workout.get("exercises", []):
                # Get primary muscle from muscle_contributions
                muscle_contributions = exercise.get("muscle_contributions", {})
                primary_muscle = "general"
                max_contribution = 0
                for muscle, contribution in muscle_contributions.items():
                    if contribution > max_contribution:
                        max_contribution = contribution
                        primary_muscle = muscle

                # Map exercise_type to category
                exercise_type = exercise.get("exercise_type", "isolation")
                category_mapping = {
                    "heavy_compound": "Strength",
                    "light_compound": "Hypertrophy",
                    "isolation": "Hypertrophy",
                    "power": "Power",
                    "plyometric": "Power",
                }
                category = category_mapping.get(exercise_type, "Hypertrophy")

                exercise_dict = {
                    "exercise_name": exercise.get("exercise_name", "Exercise"),
                    "exercise_id": exercise.get("exercise_id", ""),
                    "muscle_group": primary_muscle.replace("_", " ").title(),
                    "category": category,
                    "notes": exercise.get("rationale", ""),
                    "sets": [],
                }

                # Convert sets
                for set_data in exercise.get("sets", []):
                    set_dict = {
                        "reps": set_data.get("reps", 10),
                        "intensity_percent": set_data.get("intensity_percent"),
                        "rpe": set_data.get("rpe"),
                        "rir": set_data.get("rir"),
                        "rest_seconds": set_data.get("rest_seconds", 90),
                        "tempo": set_data.get("tempo", ""),
                        "notes": set_data.get("notes", ""),
                    }
                    exercise_dict["sets"].append(set_dict)

                workout_dict["exercises"].append(exercise_dict)

            week_dict["workouts"].append(workout_dict)

        program_data["weeks"].append(week_dict)

    # Build user_data if not provided
    if user_data is None:
        user_data = {
            "name": athlete.get("name", "Athlete"),
            "age": athlete.get("age"),
            "weight_kg": athlete.get("body_weight_kg"),
            "training_level": athlete.get("training_level", "intermediate"),
        }

    return program_data, user_data


def get_user_data_from_request(request: ProgramGenerationRequest) -> Dict[str, Any]:
    """
    Extract user data from request for HTML cover page.
    """
    return {
        "name": request.name,
        "email": request.email,
        "age": request.age,
        "weight_kg": request.weight_kg,
        "height_cm": request.height_cm,
        "sex": request.sex,
        "fitness_level": request.fitness_level,
        "goal": request.goal_category,
    }
