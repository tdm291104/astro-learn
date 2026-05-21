"""Request-scoped user-id ContextVar for LLM cost attribution."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None
)


def get_current_user_id() -> uuid.UUID | None:
    """Return the user-id bound to the current task, or None if unset."""
    return _current_user_id.get()


def set_current_user_id(user_id: uuid.UUID | None) -> Token[uuid.UUID | None]:
    """Bind user_id to the current task; returns token for optional reset."""
    return _current_user_id.set(user_id)


def reset_current_user_id(token: Token[uuid.UUID | None]) -> None:
    """Restore previous user-id binding."""
    _current_user_id.reset(token)
