"""Catalog lookup cache ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base_model import Base, IdMixin, TimestampMixin


class CatalogCacheModel(Base, IdMixin, TimestampMixin):
    """One cached catalog lookup."""

    __tablename__ = "catalog_cache"

    # Capped at 256 to keep the index cheap.
    query_norm: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # Denormalized so popularity queries skip JSON deserialisation.
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # NULL = never expires; callers treat expired rows as misses.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Additive metadata to avoid schema migration per new field.
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("query_norm", "source", name="uq_catalog_cache_query_source"),
        Index("ix_catalog_cache_expires_at", "expires_at"),
    )
