from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..models.requests import ProgramGenerationRequest
from .v5_adapter import convert_v5_output_to_html_format, get_user_data_from_request


def convert_request_to_v7_input(request: ProgramGenerationRequest) -> Dict[str, Any]:
    return {
        "user_id": str(request.user_id),
        "name": request.name,
        "email": request.email,
        "height_cm": request.height_cm,
        "weight_kg": request.weight_kg,
        "goal_category": request.goal_category,
        "goal_raw": request.goal_raw,
        "duration_weeks": request.duration_weeks,
        "days_per_week": request.days_per_week,
        "fitness_level": request.fitness_level,
        "age": request.age,
        "sex": request.sex,
        "session_duration": request.session_duration or 60,
        "injury_history": request.injury_history or "none",
        "specific_sport": request.specific_sport or "none",
        "has_vbt_capability": bool(request.has_vbt_capability),
        "user_notes": request.user_notes,
        "send_email": bool(request.send_email),
        "training_season": request.training_season,
        "games_per_week": request.games_per_week or 0,
        "competition_date": request.competition_date,
        "equipment_tier": request.equipment_tier or 1,
    }


def convert_v7_output_to_html_format(
    v7_output: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return convert_v5_output_to_html_format(v7_output, user_data)


__all__ = [
    "convert_request_to_v7_input",
    "convert_v7_output_to_html_format",
    "get_user_data_from_request",
]
