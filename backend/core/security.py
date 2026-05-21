"""JWT issue/verify and password hashing helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from core.config import get_settings
from core.exceptions import AuthenticationError, ValidationError

DEFAULT_ACCESS_TOKEN_EXPIRE: timedelta = timedelta(hours=24)

JWT_ALGORITHM: str = "HS256"


# Raise (not silently truncate) on overflow so failure is explicit.
BCRYPT_MAX_BYTES: int = 72

# 12 rounds = ~250ms per hash on commodity CPU.
BCRYPT_ROUNDS: int = 12


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash; CPU-bound, wrap with asyncio.to_thread when async."""
    encoded = plain_password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValidationError(
            message=f"Password must be at most {BCRYPT_MAX_BYTES} bytes when UTF-8 encoded",
            code="password_too_long",
        )
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(encoded, salt).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time check of plain_password against a stored bcrypt hash."""
    encoded = plain_password.encode("utf-8")
    # Truncate so too-long inputs mismatch rather than 500.
    if len(encoded) > BCRYPT_MAX_BYTES:
        encoded = encoded[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode("ascii"))
    except ValueError:
        return False


def create_access_token(
    subject: str | int,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a signed JWT."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + (expires_delta if expires_delta is not None else DEFAULT_ACCESS_TOKEN_EXPIRE)

    # Reserved claims layered on top so callers can't override sub/iat/exp.
    claims: dict[str, Any] = dict(extra_claims) if extra_claims else {}
    claims.update({
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    })

    return jwt.encode(claims, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature + expiry and return the claims payload."""
    if not token:
        raise AuthenticationError(message="Token is missing", code="invalid_token")

    settings = get_settings()
    try:
        # JWTError covers both invalid-signature and expired-token.
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise AuthenticationError(
            message="Invalid or expired token",
            code="invalid_token",
        ) from exc
