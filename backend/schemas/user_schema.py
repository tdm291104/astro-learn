"""Schemas for /users/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Body for POST /users/register."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=255)


class UserLoginRequest(BaseModel):
    """JSON-body login alternative to OAuth2 form."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Public user profile — never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT bundle returned by login."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserUpdateRequest(BaseModel):
    """Body for PATCH /users/me; email is not mutable here (JWT subject)."""

    full_name: str | None = Field(None, max_length=255)


class PasswordChangeRequest(BaseModel):
    """Body for POST /users/me/password."""

    # Verified vs stored hash to defend against session hijacking.
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
