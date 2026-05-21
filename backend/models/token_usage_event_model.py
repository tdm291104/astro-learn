"""Per-LLM-call token usage event row."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base_model import Base, IdMixin


class TokenUsageEventModel(Base, IdMixin):
    """Per-call usage row; rolled up at read time via the (user_id, created_at) index."""

    __tablename__ = "token_usage_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # LiteLLM response.model; drives per-model cost breakdown.
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # BigInteger so 32K-context runs can't overflow Int4.
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # LLM-call wall-clock; (user_id, created_at) indexed for daily aggregation.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_token_usage_user_created", "user_id", "created_at"),
    )
