"""Notebook ORM model — a NotebookLM-style container for documents + chats."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.document_model import DocumentModel
    from models.session_model import SessionModel
    from models.user_model import UserModel


class NotebookModel(Base, IdMixin, TimestampMixin):
    """A user-owned notebook grouping documents and chat sessions."""

    __tablename__ = "notebooks"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NULL = private; UNIQUE so token collisions surface as DB error.
    share_token: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )

    # Default hides filenames; JSONB lets us add toggles without migrations.
    share_settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default='{"show_filenames": false}',
        default=lambda: {"show_filenames": False},
    )

    owner: Mapped[UserModel] = relationship(back_populates="notebooks")
    sessions: Mapped[list[SessionModel]] = relationship(
        back_populates="notebook",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[DocumentModel]] = relationship(
        back_populates="notebook",
        cascade="all, delete-orphan",
    )
