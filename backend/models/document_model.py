"""Uploaded document ORM model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.notebook_model import NotebookModel


class DocumentModel(Base, IdMixin, TimestampMixin):
    """One uploaded document inside a notebook."""

    __tablename__ = "documents"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
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

    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    indexed_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    notebook: Mapped[NotebookModel] = relationship(back_populates="documents")
