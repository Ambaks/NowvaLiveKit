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


class ProgramSummary(BaseModel):
    """Response model for program summary (for listing)"""
    id: int
    name: str
    description: str
    duration_weeks: int
    type: str  # "user_generated" or "partner"
    created_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": 42,
                "name": "Summer Shred 2025",
                "description": "12-week hypertrophy program",
                "duration_weeks": 12,
                "type": "user_generated",
                "created_at": "2025-10-15T14:30:00"
            }
        }


class ProgramListResponse(BaseModel):
    """Response model for listing user's programs"""
    programs: list[ProgramSummary]
    total_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "programs": [
                    {
                        "id": 42,
                        "name": "Summer Shred 2025",
                        "description": "12-week hypertrophy program",
                        "duration_weeks": 12,
                        "type": "user_generated",
                        "created_at": "2025-10-15T14:30:00"
                    }
                ],
                "total_count": 1
            }
        }


class UpdateStatusResponse(BaseModel):
    """Response model for update job status (extends JobStatusResponse)"""
    job_id: str
    status: str  # pending, in_progress, completed, failed
    progress: int  # 0-100
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    program_id: Optional[str] = None
    error_message: Optional[str] = None
    diff: Optional[list[str]] = None  # List of changes made

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "completed",
                "progress": 100,
                "created_at": "2025-10-20T22:00:00Z",
                "started_at": "2025-10-20T22:00:05Z",
                "completed_at": "2025-10-20T22:01:30Z",
                "program_id": "42",
                "error_message": None,
                "diff": [
                    "Training frequency changed: 5 → 3 days/week",
                    "Exercise selection modified (sample from Week 1 Day 1)"
                ]
            }
        }
