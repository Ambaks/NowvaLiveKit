from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.models.requests import ProgramGenerationRequest
from api.services.v5_adapter import convert_request_to_v5_input


RAW_V7_PERSONAS = {
    "hypertrophy_general": {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "name": "Alex Volume",
        "email": "alex@example.com",
        "height_cm": 182.0,
        "weight_kg": 86.0,
        "goal_category": "hypertrophy",
        "goal_raw": "Build muscle while keeping sessions efficient.",
        "duration_weeks": 4,
        "days_per_week": 4,
        "fitness_level": "intermediate",
        "age": 31,
        "sex": "M",
        "session_duration": 65,
        "injury_history": "none",
        "specific_sport": "none",
        "has_vbt_capability": False,
        "training_season": None,
        "games_per_week": 0,
        "competition_date": None,
        "equipment_tier": 2,
        "user_notes": "Prefer upper lower if possible. Bring up upper chest and lats.",
        "send_email": False,
    },
    "strength_powerlifting": {
        "user_id": "22222222-2222-4222-8222-222222222222",
        "name": "Mia Strength",
        "email": "mia@example.com",
        "height_cm": 168.0,
        "weight_kg": 72.5,
        "goal_category": "strength",
        "goal_raw": "Peak basic barbell strength for a local meet.",
        "duration_weeks": 6,
        "days_per_week": 4,
        "fitness_level": "advanced",
        "age": 29,
        "sex": "F",
        "session_duration": 75,
        "injury_history": "previous shoulder irritation with high-volume overhead work",
        "specific_sport": "powerlifting",
        "has_vbt_capability": True,
        "training_season": "off_season",
        "games_per_week": 0,
        "competition_date": "2026-08-15",
        "equipment_tier": 2,
        "user_notes": "Prefer front squats over back squats. Keep the main lifts stable week to week.",
        "send_email": False,
    },
    "power_basketball_inseason": {
        "user_id": "33333333-3333-4333-8333-333333333333",
        "name": "Jordan Jump",
        "email": "jordan@example.com",
        "height_cm": 191.0,
        "weight_kg": 88.0,
        "goal_category": "power",
        "goal_raw": "Stay explosive during the season without getting crushed.",
        "duration_weeks": 4,
        "days_per_week": 3,
        "fitness_level": "intermediate",
        "age": 24,
        "sex": "M",
        "session_duration": 50,
        "injury_history": "minor patellar tendon soreness",
        "specific_sport": "basketball",
        "has_vbt_capability": False,
        "training_season": "in_season",
        "games_per_week": 2,
        "competition_date": None,
        "equipment_tier": 1,
        "user_notes": "Keep fatigue low. Focus on jumps, posterior chain, and knee-friendly lower work.",
        "send_email": False,
    },
}


def build_v7_input(persona_name: str) -> dict:
    return deepcopy(RAW_V7_PERSONAS[persona_name])


def build_v5_input(persona_name: str) -> dict:
    request = ProgramGenerationRequest(**RAW_V7_PERSONAS[persona_name])
    return convert_request_to_v5_input(request)
