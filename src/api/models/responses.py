"""
Pydantic Response Models for FastAPI
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class JobResponse(BaseModel):
    """Response model when starting a job"""
    job_id: str
    status: str
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "pending",
                "message": "Program generation started"
            }
        }


class JobStatusResponse(BaseModel):
    """Response model for job status check"""
    job_id: str
    status: str  # pending, in_progress, completed, failed
    progress: int  # 0-100
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    program_id: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "in_progress",
                "progress": 65,
                "created_at": "2025-10-20T22:00:00Z",
                "started_at": "2025-10-20T22:00:05Z",
                "completed_at": None,
                "program_id": None,
                "error_message": None
            }
        }


class ProgramResponse(BaseModel):
    """Response model for program data"""
    id: str
    name: str
    description: str
    duration_weeks: int
    created_at: datetime

    class Config:
        from_attributes = True  # Allows loading from SQLAlchemy models
