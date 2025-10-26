"""
Pydantic Request Models for FastAPI
"""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class ProgramGenerationRequest(BaseModel):
    """Request model for starting program generation"""
    # Original required parameters
    user_id: UUID
    height_cm: float = Field(gt=0, lt=300, description="Height in centimeters")
    weight_kg: float = Field(gt=0, lt=500, description="Weight in kilograms")
    goal_category: str = Field(pattern="^(power|strength|hypertrophy|athletic_performance)$", description="Primary training goal")
    goal_raw: str = Field(min_length=1, max_length=500, description="User's goal in their own words")
    duration_weeks: int = Field(ge=2, le=52, description="Program duration in weeks")
    days_per_week: int = Field(ge=1, le=7, description="Training days per week")
    fitness_level: str = Field(pattern="^(beginner|intermediate|advanced)$", description="User's fitness level")

    # Enhanced parameters for comprehensive programming
    age: int = Field(ge=13, le=100, description="User's age in years")
    sex: str = Field(pattern="^(M|F|male|female)$", description="Biological sex (M/F or male/female)")
    session_duration: Optional[int] = Field(default=60, ge=30, le=180, description="Available minutes per session")
    injury_history: Optional[str] = Field(
        default="none",
        max_length=1000,
        description="Current or past injuries affecting exercise selection (or 'none')"
    )
    specific_sport: Optional[str] = Field(
        default="none",
        max_length=100,
        description="Sport if applicable (e.g., 'basketball', 'powerlifting', or 'none')"
    )
    has_vbt_capability: Optional[bool] = Field(
        default=False,
        description="Whether user has velocity-based training equipment available"
    )
    user_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Any additional notes, preferences, or context from the user (e.g., 'prefer front squats', 'training for marathon in 3 months', 'avoid overhead pressing')"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "ee611076-e172-45c9-8562-c30aeebd037f",
                "height_cm": 190.5,
                "weight_kg": 87.5,
                "goal_category": "strength",
                "goal_raw": "build foundational strength",
                "duration_weeks": 12,
                "days_per_week": 4,
                "fitness_level": "intermediate",
                "age": 28,
                "sex": "M",
                "session_duration": 75,
                "injury_history": "previous right shoulder impingement (2 years ago, fully healed)",
                "specific_sport": "powerlifting",
                "has_vbt_capability": True,
                "user_notes": "Prefer front squats over back squats. Available equipment includes competition-spec barbell and calibrated plates. Training for a meet in 12 weeks."
            }
        }
