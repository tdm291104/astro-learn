"""Conversation-session business logic."""

from __future__ import annotations

import uuid
from typing import Any

from core.exceptions import AuthorizationError, NotFoundError, ValidationError
from repositories.message_repository import MessageRepository
from repositories.session_repository import SessionRepository
from schemas.session_schema import (
    MessageResponse,
    SessionCreate,
    SessionMode,
    SessionResponse,
    SessionUpdate,
)


class SessionService:
    """Session lifecycle + message append."""

    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
    ) -> None:
        self.sessions = sessions
        self.messages = messages

    async def create(
        self,
        user_id: uuid.UUID,
        payload: SessionCreate,
    ) -> SessionResponse:
        """Create a new conversation row owned by user_id."""
        created = await self.sessions.create(
            {
                "user_id": user_id,
                "notebook_id": payload.notebook_id,
                "title": payload.title,
                "mode": payload.mode,
            }
        )
        # Refetch so fits_files relationship is selectinload-ed for response.
        row = await self.sessions.get(created.id)
        assert row is not None
        return SessionResponse.from_model(row)

    async def get_or_create(
        self,
        user_id: uuid.UUID,
        *,
        session_id: uuid.UUID | None = None,
        notebook_id: uuid.UUID | None = None,
        title: str | None = None,
        mode: SessionMode = "general",
    ) -> SessionResponse:
        if session_id is not None:
            row = await self.sessions.get(session_id)
            if row is None:
                raise NotFoundError(
                    message="Session not found",
                    code="session_not_found",
                )
            self._check_owner(row.user_id, user_id)
            return SessionResponse.from_model(row)

        return await self.create(
            user_id,
            SessionCreate(notebook_id=notebook_id, title=title, mode=mode),
        )

    async def get(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SessionResponse:
        row = await self.sessions.get(session_id)
        if row is None:
            raise NotFoundError(
                message="Session not found", code="session_not_found"
            )
        self._check_owner(row.user_id, user_id)
        return SessionResponse.from_model(row)

    async def update(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: SessionUpdate,
    ) -> SessionResponse:
        """Patch mode/title/notebook_id on a session owned by user_id."""
        row = await self.sessions.get(session_id)
        if row is None:
            raise NotFoundError(
                message="Session not found", code="session_not_found"
            )
        self._check_owner(row.user_id, user_id)

        # exclude_unset preserves omitted fields; explicit None still clears.
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return SessionResponse.from_model(row)

        await self.sessions.update(session_id, data)
        fresh = await self.sessions.get(session_id)
        assert fresh is not None
        return SessionResponse.from_model(fresh)

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        notebook_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionResponse]:
        rows = await self.sessions.list_for_user(
            user_id,
            notebook_id=notebook_id,
            limit=limit,
            offset=offset,
        )
        return [SessionResponse.from_model(r) for r in rows]

    async def delete(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[bool, list[uuid.UUID]]:
        """Delete session + return ids of FITS files orphaned (sole-attached to it)."""
        row = await self.sessions.get(session_id)
        if row is None:
            return False, []
        self._check_owner(row.user_id, user_id)

        # Compute orphans BEFORE delete so join rows still exist.
        orphan_ids = await self.sessions.list_solely_attached_fits_ids(
            session_id, [f.id for f in row.fits_files]
        )

        deleted = await self.sessions.delete(session_id)
        return deleted, orphan_ids if deleted else []

    async def list_messages(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[MessageResponse]:
        row = await self.sessions.get(session_id)
        if row is None:
            raise NotFoundError(
                message="Session not found",
                code="session_not_found",
            )
        self._check_owner(row.user_id, user_id)

        messages = await self.messages.list_for_session(session_id)
        return [MessageResponse.model_validate(m) for m in messages]

    async def append_message(
        self,
        session_id: uuid.UUID,
        *,
        role: str,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> MessageResponse:
        """Persist one message into a session (used by agents during a run)."""
        # Caller trusted (agent code); ownership checked upstream.
        created = await self.messages.create(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "extra": extra,
            }
        )
        return MessageResponse.model_validate(created)

    async def attach_fits_file(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        fits_file_id: uuid.UUID,
    ) -> SessionResponse:
        """Attach a FITS file to a conversation; idempotent on duplicates."""
        row = await self.sessions.get(session_id)
        if row is None:
            raise NotFoundError(
                message="Session not found", code="session_not_found"
            )
        self._check_owner(row.user_id, user_id)

        updated = await self.sessions.attach_fits_file(session_id, fits_file_id)
        if updated is None:
            # Repo returns None when FITS row missing; 422 distinguishes from session 404.
            raise ValidationError(
                message="FITS file not found",
                code="fits_file_not_found",
            )
        return SessionResponse.from_model(updated)

    async def detach_fits_file(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        fits_file_id: uuid.UUID,
    ) -> bool:
        """Remove a FITS file from a conversation; True if removed."""
        row = await self.sessions.get(session_id)
        if row is None:
            return False
        self._check_owner(row.user_id, user_id)
        return await self.sessions.detach_fits_file(session_id, fits_file_id)

    @staticmethod
    def _check_owner(row_owner: uuid.UUID, caller: uuid.UUID) -> None:
        if row_owner != caller:
            raise AuthorizationError(
                message="Session belongs to another user",
                code="forbidden",
            )
