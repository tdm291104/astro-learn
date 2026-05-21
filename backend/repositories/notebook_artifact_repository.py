"""DB access for NotebookArtifactModel."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from models.notebook_artifact_model import NotebookArtifactModel
from repositories.base_repository import BaseRepository


class NotebookArtifactRepository(BaseRepository[NotebookArtifactModel]):
    """Per-notebook cached summary/quiz/flashcard payload operations."""

    model = NotebookArtifactModel

    async def get_by_kind(
        self,
        notebook_id: uuid.UUID,
        kind: str,
    ) -> NotebookArtifactModel | None:
        """Return the cached artifact of `kind` for `notebook_id`, or None."""
        stmt = select(NotebookArtifactModel).where(
            NotebookArtifactModel.notebook_id == notebook_id,
            NotebookArtifactModel.kind == kind,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        notebook_id: uuid.UUID,
        kind: str,
        *,
        params: dict[str, Any],
        payload: dict[str, Any],
    ) -> NotebookArtifactModel:
        """Insert or overwrite the artifact for (notebook_id, kind)."""
        existing = await self.get_by_kind(notebook_id, kind)
        if existing is None:
            return await self.create(
                {
                    "notebook_id": notebook_id,
                    "kind": kind,
                    "params": params,
                    "payload": payload,
                }
            )
        existing.params = params
        existing.payload = payload
        await self.session.flush()
        await self.session.refresh(existing)
        return existing
