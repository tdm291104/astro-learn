"""Chat message ORM model — one row per message in a session."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.session_model import SessionModel


# Role: system|user|assistant|tool (plain string for migration ease).
class MessageModel(Base, IdMixin, TimestampMixin):
    """A single chat message belonging to a session."""

    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[SessionModel] = relationship(back_populates="messages")
