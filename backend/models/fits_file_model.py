"""Uploaded FITS file ORM model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base_model import Base, IdMixin, TimestampMixin


class FitsFileModel(Base, IdMixin, TimestampMixin):
    """One uploaded FITS file."""

    __tablename__ = "fits_files"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)

    hdu_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hdus: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    primary_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # extract_header_summary projection; nullable for legacy rows.
    header_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="parsed", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SHA-256 hex of the raw file bytes. Used to dedupe re-uploads of the
    # same content by the same owner (FE was merging duplicates visually
    # while the backend kept N rows + N analyses, inflating the user's
    # "FITS analyzed" count). Nullable for legacy rows that predate this
    # column; new uploads always populate it.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_fits_files_owner_hash", "owner_id", "content_hash"),
    )
