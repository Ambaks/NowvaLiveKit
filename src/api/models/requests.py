"""
Pydantic Request Models for FastAPI
"""
from pydantic import BaseModel, Field
from uuid import UUID


class ProgramGenerationRequest(BaseModel):
    """Request model for starting program generation"""
    user_id: UUID
    height_cm: float = Field(gt=0, lt=300, description="Height in centimeters")
    weight_kg: float = Field(gt=0, lt=500, description="Weight in kilograms")
    goal_category: str = Field(pattern="^(power|strength|hypertrophy)$", description="Primary training goal")
    goal_raw: str = Field(min_length=1, max_length=500, description="User's goal in their own words")
    duration_weeks: int = Field(ge=2, le=52, description="Program duration in weeks")
    days_per_week: int = Field(ge=1, le=7, description="Training days per week")
    fitness_level: str = Field(pattern="^(beginner|intermediate|advanced)$", description="User's fitness level")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "ee611076-e172-45c9-8562-c30aeebd037f",
                "height_cm": 190.5,
                "weight_kg": 87.5,
                "goal_category": "hypertrophy",
                "goal_raw": "muscle gain",
                "duration_weeks": 12,
                "days_per_week": 4,
                "fitness_level": "intermediate"
            }
        }
