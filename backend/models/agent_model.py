"""Agent run record persisting each agent execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.session_model import SessionModel
    from models.user_model import UserModel


# Status string: pending|running|succeeded|failed|cancelled (no DB enum).
class AgentModel(Base, IdMixin, TimestampMixin):
    """One agent execution record."""

    __tablename__ = "agent_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    agent_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    task_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # progress: 0.0-1.0 fraction or NULL (treat as unknown).
    step_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="agent_runs")
    session: Mapped[SessionModel | None] = relationship(back_populates="agent_runs")
