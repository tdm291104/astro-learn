"""Generic async CRUD base class for concrete repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base_model import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async CRUD over a single ORM model."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        **filters: Any,
    ) -> Sequence[ModelT]:
        """Return a page of rows filtered by equality predicates."""
        # Unknown filter keys raise AttributeError to catch typos at call site.
        stmt = select(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """Return total matching filters."""
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: uuid.UUID) -> bool:
        """Existence check that avoids loading the row."""
        stmt = select(self.model.id).where(self.model.id == id).limit(1)
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def create(self, data: BaseModel | dict[str, Any]) -> ModelT:
        """Insert and flush a new row; returns the populated instance."""
        # No commit here; request-scoped get_db commits on clean exit.
        payload = (
            data.model_dump(exclude_unset=True)
            if isinstance(data, BaseModel)
            else dict(data)
        )
        instance = self.model(**payload)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(
        self,
        id: uuid.UUID,
        data: BaseModel | dict[str, Any],
    ) -> ModelT | None:
        """Apply a partial update; missing fields are left untouched."""
        # exclude_unset preserves stored values for omitted keys.
        instance = await self.session.get(self.model, id)
        if instance is None:
            return None

        payload = (
            data.model_dump(exclude_unset=True)
            if isinstance(data, BaseModel)
            else dict(data)
        )
        for key, value in payload.items():
            setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: uuid.UUID) -> bool:
        """Delete the row; True if a row was deleted."""
        instance = await self.session.get(self.model, id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True
