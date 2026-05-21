"""DB access for DocumentModel (uploaded notebook documents)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from models.document_model import DocumentModel
from repositories.base_repository import BaseRepository


class DocumentRepository(BaseRepository[DocumentModel]):
    """Document table operations."""

    model = DocumentModel

    async def list_for_notebook(
        self,
        notebook_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[DocumentModel]:
        """Return documents in `notebook_id`, newest first."""
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.notebook_id == notebook_id)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_notebook(self, notebook_id: uuid.UUID) -> int:
        """Return the total document count for `notebook_id`."""
        return await self.count(notebook_id=notebook_id)

    async def set_status(
        self,
        document_id: uuid.UUID,
        status: str,
        *,
        indexed_chunks: int | None = None,
        error: str | None = None,
    ) -> DocumentModel | None:
        """Advance a document through its indexing lifecycle."""
        instance = await self.session.get(DocumentModel, document_id)
        if instance is None:
            return None

        instance.status = status
        if indexed_chunks is not None:
            instance.indexed_chunks = indexed_chunks
        if error is not None:
            instance.error = error

        await self.session.flush()
        await self.session.refresh(instance)
        return instance
