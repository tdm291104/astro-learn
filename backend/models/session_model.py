"""Conversation session ORM model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.agent_model import AgentModel
    from models.fits_file_model import FitsFileModel
    from models.message_model import MessageModel
    from models.notebook_model import NotebookModel
    from models.user_model import UserModel


# M2M: conversations may share physical FITS files.
session_fits_files = Table(
    "session_fits_files",
    Base.metadata,
    Column(
        "session_id",
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "fits_file_id",
        Uuid(as_uuid=True),
        ForeignKey("fits_files.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class SessionModel(Base, IdMixin, TimestampMixin):
    """A chat / agent-run session owned by a user."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    notebook_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notebooks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Mirrors FE ChatMode union; plain string for portability + no migration on new modes.
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="general", server_default="general"
    )

    user: Mapped[UserModel] = relationship(back_populates="sessions")
    notebook: Mapped[NotebookModel | None] = relationship(back_populates="sessions")
    messages: Mapped[list[MessageModel]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )
    agent_runs: Mapped[list[AgentModel]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    fits_files: Mapped[list[FitsFileModel]] = relationship(
        secondary=session_fits_files,
        lazy="selectin",
    )
