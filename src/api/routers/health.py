"""
Health Check Router
Simple endpoint to verify API is running
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Nowva Program Generator API",
        "version": "1.0.0"
    }
