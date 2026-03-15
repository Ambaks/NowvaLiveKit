"""
LiveKit router for generating room tokens and managing voice agent connections
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from livekit import api
import secrets

from auth.security import get_current_user
from db.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenRequest(BaseModel):
    """Optional request body — only the name field is used (email comes from auth)."""
    name: Optional[str] = None


class TokenResponse(BaseModel):
    """Response model containing LiveKit connection details"""
    token: str
    url: str
    room_name: str


@router.post("/token", response_model=TokenResponse)
async def create_room_token(
    request: TokenRequest = TokenRequest(),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a LiveKit room token for the website voice agent.

    Requires authentication.  The user's email is taken from the
    authenticated session — not from the request body.

    Args:
        request: Optional TokenRequest with a display name override

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

        # Use authenticated user's email
        email = current_user.email

        # Generate a unique room name for this session
        room_name = f"website-{secrets.token_urlsafe(8)}"

        # Create access token
        identity = request.name if request.name else current_user.name or email.split("@")[0]

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
            .with_metadata(f'{{"email": "{email}"}}')
        )

        # Generate the JWT token
        jwt_token = token.to_jwt()

        logger.info(f"Generated LiveKit token for {email} in room {room_name}")

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
