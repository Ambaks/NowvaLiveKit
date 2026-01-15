"""
LiveKit router for generating room tokens and managing voice agent connections
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from livekit import api
import secrets

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenRequest(BaseModel):
    """Request model for LiveKit token generation"""
    email: EmailStr
    name: Optional[str] = None


class TokenResponse(BaseModel):
    """Response model containing LiveKit connection details"""
    token: str
    url: str
    room_name: str


@router.post("/token", response_model=TokenResponse)
async def create_room_token(request: TokenRequest):
    """
    Generate a LiveKit room token for the website voice agent.

    This endpoint:
    1. Generates a unique room name
    2. Creates a LiveKit access token
    3. Includes the user's email in room metadata for the agent to access

    Args:
        request: TokenRequest with user's email (and optional name)

    Returns:
        TokenResponse with token, LiveKit URL, and room name
    """
    try:
        # Get LiveKit credentials from environment
        livekit_url = os.getenv("LIVEKIT_URL")
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            logger.error("Missing LiveKit credentials in environment")
            raise HTTPException(
                status_code=500,
                detail="LiveKit configuration missing"
            )

        # Generate a unique room name for this session
        # Format: website-{random_id}
        room_name = f"website-{secrets.token_urlsafe(8)}"

        # Create access token
        identity = request.name if request.name else request.email.split("@")[0]

        token = (
            api.AccessToken(livekit_api_key, livekit_api_secret)
            .with_identity(identity)
            .with_name(identity)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_metadata(f'{{"email": "{request.email}"}}')
        )

        # Generate the JWT token
        jwt_token = token.to_jwt()

        logger.info(f"Generated LiveKit token for {request.email} in room {room_name}")

        return TokenResponse(
            token=jwt_token,
            url=livekit_url,
            room_name=room_name
        )

    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate room token: {str(e)}"
        )


@router.get("/health")
async def livekit_health():
    """
    Check if LiveKit credentials are configured
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    configured = all([livekit_url, livekit_api_key, livekit_api_secret])

    return {
        "configured": configured,
        "url": livekit_url if configured else None
    }
