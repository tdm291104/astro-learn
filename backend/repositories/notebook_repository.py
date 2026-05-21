"""DB access for NotebookModel."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from models.notebook_model import NotebookModel
from repositories.base_repository import BaseRepository


class NotebookRepository(BaseRepository[NotebookModel]):
    """Notebook table operations."""

    model = NotebookModel

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[NotebookModel]:
        """Return notebooks owned by owner_id, newest first."""
        stmt = (
            select(NotebookModel)
            .where(NotebookModel.owner_id == owner_id)
            .order_by(NotebookModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_share_token(
        self,
        share_token: str,
    ) -> NotebookModel | None:
        """Look up a notebook by share_token; None if not found or revoked."""
        stmt = select(NotebookModel).where(NotebookModel.share_token == share_token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_share_token(
        self,
        notebook_id: uuid.UUID,
        token: str,
    ) -> NotebookModel | None:
        """Stamp share_token on the row and return the refreshed model."""
        # Callers must check existing token first to avoid rotating live URLs.
        instance = await self.session.get(NotebookModel, notebook_id)
        if instance is None:
            return None
        instance.share_token = token
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def clear_share_token(
        self,
        notebook_id: uuid.UUID,
    ) -> NotebookModel | None:
        """Revoke the row's share_token (set to NULL)."""
        instance = await self.session.get(NotebookModel, notebook_id)
        if instance is None:
            return None
        instance.share_token = None
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def search_all(
        self,
        *,
        query: str | None = None,
        owner_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[NotebookModel]:
        """Admin-wide list across all owners; newest first."""
        stmt = select(NotebookModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(NotebookModel.title).like(pattern),
                    func.lower(func.coalesce(NotebookModel.description, "")).like(
                        pattern
                    ),
                )
            )
        if owner_id is not None:
            stmt = stmt.where(NotebookModel.owner_id == owner_id)
        stmt = (
            stmt.order_by(NotebookModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_search_all(
        self,
        *,
        query: str | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> int:
        """Total notebooks matching the same filters as search_all()."""
        stmt = select(func.count()).select_from(NotebookModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(NotebookModel.title).like(pattern),
                    func.lower(func.coalesce(NotebookModel.description, "")).like(
                        pattern
                    ),
                )
            )
        if owner_id is not None:
            stmt = stmt.where(NotebookModel.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()
