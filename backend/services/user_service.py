"""Auth and profile business logic for user routes."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from core.security import (
    DEFAULT_ACCESS_TOKEN_EXPIRE,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from repositories.user_repository import UserRepository
from schemas.user_schema import (
    PasswordChangeRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)


class UserService:
    """User lifecycle: register, authenticate, fetch."""

    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def register(self, request: UserRegisterRequest) -> UserResponse:
        """Create a new user."""
        if await self.users.get_by_email(request.email) is not None:
            raise ConflictError(
                message="Email already registered",
                code="email_taken",
            )

        # bcrypt is CPU-bound; offload to thread.
        password_hash = await asyncio.to_thread(hash_password, request.password)

        try:
            user = await self.users.create(
                {
                    "email": request.email,
                    "password_hash": password_hash,
                    "full_name": request.full_name,
                }
            )
        except IntegrityError as exc:
            # Race between pre-check and insert.
            raise ConflictError(
                message="Email already registered",
                code="email_taken",
            ) from exc

        return UserResponse.model_validate(user)

    async def authenticate(self, email: str, password: str) -> TokenResponse:
        """Verify credentials and return a signed access token."""
        # Single error to avoid leaking which side failed.
        user = await self.users.get_by_email(email)
        if user is None:
            raise AuthenticationError(
                message="Invalid email or password",
                code="invalid_credentials",
            )

        is_valid = await asyncio.to_thread(
            verify_password, password, user.password_hash
        )
        if not is_valid:
            raise AuthenticationError(
                message="Invalid email or password",
                code="invalid_credentials",
            )

        if not user.is_active:
            raise AuthenticationError(
                message="User account is disabled",
                code="user_inactive",
            )

        token = create_access_token(user.id)
        expires_at = datetime.now(UTC) + DEFAULT_ACCESS_TOKEN_EXPIRE
        return TokenResponse(access_token=token, expires_at=expires_at)

    async def get_from_token(self, token: str) -> UserResponse:
        """Decode token, load the user, and return the public profile."""
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise AuthenticationError(
                message="Token missing subject claim",
                code="invalid_token",
            )

        try:
            user_id = uuid.UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise AuthenticationError(
                message="Token subject is not a valid user id",
                code="invalid_token",
            ) from exc

        user = await self.users.get(user_id)
        if user is None:
            raise AuthenticationError(
                message="User no longer exists",
                code="invalid_token",
            )
        return UserResponse.model_validate(user)

    async def get_by_id(self, user_id: uuid.UUID) -> UserResponse | None:
        user = await self.users.get(user_id)
        return UserResponse.model_validate(user) if user is not None else None

    async def update_profile(
        self,
        user_id: uuid.UUID,
        request: UserUpdateRequest,
    ) -> UserResponse:
        """Patch editable profile fields; normalises empty full_name to None."""
        data = request.model_dump(exclude_unset=True)
        if "full_name" in data:
            raw = data["full_name"]
            data["full_name"] = (
                raw.strip() if isinstance(raw, str) and raw.strip() else None
            )

        if not data:
            existing = await self.users.get(user_id)
            if existing is None:
                raise NotFoundError(
                    message="User not found", code="user_not_found"
                )
            return UserResponse.model_validate(existing)

        updated = await self.users.update(user_id, data)
        if updated is None:
            raise NotFoundError(
                message="User not found", code="user_not_found"
            )
        return UserResponse.model_validate(updated)

    async def change_password(
        self,
        user_id: uuid.UUID,
        request: PasswordChangeRequest,
    ) -> None:
        """Verify the current password and replace it with a new hash."""
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found", code="user_not_found"
            )

        # bcrypt verify is CPU-bound; offload to thread.
        is_valid = await asyncio.to_thread(
            verify_password, request.current_password, user.password_hash
        )
        if not is_valid:
            # Distinct code so FE highlights the right field.
            raise AuthenticationError(
                message="Current password is incorrect",
                code="invalid_current_password",
            )

        if request.new_password == request.current_password:
            # Reject no-op rotation to keep audit story honest.
            raise ValidationError(
                message="New password must differ from the current one",
                code="password_unchanged",
            )

        new_hash = await asyncio.to_thread(hash_password, request.new_password)
        await self.users.update(user_id, {"password_hash": new_hash})
