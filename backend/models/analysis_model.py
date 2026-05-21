"""Astronomy analysis run ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base_model import Base, IdMixin, TimestampMixin


class AnalysisModel(Base, IdMixin, TimestampMixin):
    """One analysis execution against a stored FITS file."""

    __tablename__ = "analyses"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fits_files.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hdu_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Paths under STORAGE_ROOT/analyses/{id}/.
    artifacts: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # FitsInterpretation; null for legacy/non-chat runs.
    interpretation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
