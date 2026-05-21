"""Schemas for /sessions/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror MessageModel.role — keep in sync.
MessageRole = Literal["system", "user", "assistant", "tool"]

# Mirror frontend ChatMode; not a DB enum so adding modes needs no migration.
SessionMode = Literal["general", "notebook", "fits", "catalog"]


class SessionResponse(BaseModel):
    """Conversation session metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    notebook_id: uuid.UUID | None
    title: str | None
    mode: SessionMode
    # Populated from session_fits_files; clients fetch full metadata separately.
    fits_file_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: Any) -> SessionResponse:
        """Build the response from a SessionModel row (projects fits_files → ids)."""
        file_ids = [f.id for f in getattr(row, "fits_files", []) or []]
        return cls(
            id=row.id,
            user_id=row.user_id,
            notebook_id=row.notebook_id,
            title=row.title,
            mode=row.mode,
            fits_file_ids=file_ids,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SessionCreate(BaseModel):
    """Request body for POST /sessions/."""

    title: str | None = None
    mode: SessionMode = "general"
    notebook_id: uuid.UUID | None = None


class SessionUpdate(BaseModel):
    """Request body for PATCH /sessions/{id} — partial update."""

    title: str | None = None
    mode: SessionMode | None = None
    notebook_id: uuid.UUID | None = None


class SessionFileAttachRequest(BaseModel):
    """Request body for POST /sessions/{id}/files."""

    fits_file_id: uuid.UUID


class MessageResponse(BaseModel):
    """One message inside a session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    extra: dict[str, Any] | None
    created_at: datetime
