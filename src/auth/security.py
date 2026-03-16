"""
Authentication & Authorization
Password hashing, JWT tokens, and FastAPI dependencies for protecting endpoints.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing (bcrypt — used directly, passlib is incompatible with
# bcrypt >= 4.x)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
_SECRET_KEY: Optional[str] = None
_ALGORITHM: str = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60


def _get_jwt_config():
    """Lazy-load JWT config from environment (allows .env to be loaded first)."""
    global _SECRET_KEY, _ALGORITHM, _ACCESS_TOKEN_EXPIRE_MINUTES
    if _SECRET_KEY is None:
        from dotenv import load_dotenv
        load_dotenv()
        _SECRET_KEY = os.getenv("JWT_SECRET_KEY")
        if not _SECRET_KEY:
            raise RuntimeError(
                "JWT_SECRET_KEY environment variable is not set. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        _ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        _ACCESS_TOKEN_EXPIRE_MINUTES = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        )
    return _SECRET_KEY, _ALGORITHM, _ACCESS_TOKEN_EXPIRE_MINUTES


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT containing *data* with an expiry claim."""
    secret, algorithm, default_minutes = _get_jwt_config()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=default_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises ``JWTError`` on failure."""
    secret, algorithm, _ = _get_jwt_config()
    return jwt.decode(token, secret, algorithms=[algorithm])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _get_service_api_key() -> Optional[str]:
    """Return the SERVICE_API_KEY from env, or None if not set."""
    return os.getenv("SERVICE_API_KEY")


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that returns the authenticated ``User``.

    Auth methods (checked in order):
    1. ``X-Service-Key`` header — for internal service-to-service calls.
       Returns a sentinel ``User`` with ``is_service=True`` attribute so
       callers can skip ownership checks when appropriate.
    2. Bearer JWT — standard user authentication.

    Raises 401 if neither method succeeds.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # --- Path 1: Service API key -------------------------------------------
    service_key = request.headers.get("X-Service-Key")
    if service_key:
        expected = _get_service_api_key()
        if expected and service_key == expected:
            # Return a lightweight sentinel — endpoints that need a real user
            # record should check ``getattr(user, 'is_service', False)``.
            sentinel = User.__new__(User)
            sentinel.id = None
            sentinel.email = "service@internal"
            sentinel.name = "Service Account"
            sentinel.is_service = True  # dynamic attribute
            return sentinel
        # Bad key → 401 (don't fall through to JWT)
        raise credentials_exception

    # --- Path 2: Bearer JWT ------------------------------------------------
    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    return user
