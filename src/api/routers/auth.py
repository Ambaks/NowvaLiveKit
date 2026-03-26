"""
Auth Router
Login, registration, and current-user endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from db.database import get_db
from db.models import User
from utils.username_generator import generate_username

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class EmailStartRequest(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: Optional[UUID] = None


class UserProfile(BaseModel):
    id: UUID
    username: str
    name: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/register", response_model=UserProfile, status_code=201)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account with a hashed password."""
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    username = generate_username(request.name, db)
    user = User(
        username=username,
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2-compatible login.

    The ``username`` field of the form is treated as the user's **email**.
    Returns a JWT access token on success.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user.email})
    return TokenResponse(access_token=token)


@router.post("/email-start", response_model=TokenResponse)
async def email_start(request: EmailStartRequest, db: Session = Depends(get_db)):
    """
    Passwordless entry point.

    Finds an existing user by email or creates a new one, then returns a JWT
    along with the user's database ID so the frontend can reference it.
    Used by the simplified email-only gate on the frontend.
    """
    import secrets

    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        name = request.email.split("@")[0]
        username = generate_username(name, db)
        user = User(
            username=username,
            name=name,
            email=request.email,
            password_hash=hash_password(secrets.token_hex(32)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(data={"sub": user.email})
    return TokenResponse(access_token=token, user_id=user.id)


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
