"""Cached output of summarize/quiz/flashcard runs for a notebook."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base_model import Base, IdMixin, TimestampMixin

# Validated at schema layer (Literal); no DB enum keeps migrations light.
NOTEBOOK_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {"summary", "quiz", "flashcards"}
)


class NotebookArtifactModel(Base, IdMixin, TimestampMixin):
    """Last-generated payload per (notebook, kind); survives query-cache evictions."""

    __tablename__ = "notebook_artifacts"
    __table_args__ = (
        UniqueConstraint("notebook_id", "kind", name="uq_notebook_artifact_kind"),
    )

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Generation params; UI uses to show "what was last asked".
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # Full response body; shape depends on kind, narrowed at schema layer.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
