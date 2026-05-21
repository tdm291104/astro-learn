"""DB access for FitsFileModel (uploaded FITS files)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from models.fits_file_model import FitsFileModel
from repositories.base_repository import BaseRepository


class FitsFileRepository(BaseRepository[FitsFileModel]):
    """FITS file table operations."""

    model = FitsFileModel

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[FitsFileModel]:
        """Return FITS files owned by `owner_id`, newest first."""
        stmt = (
            select(FitsFileModel)
            .where(FitsFileModel.owner_id == owner_id)
            .order_by(FitsFileModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def set_status(
        self,
        file_id: uuid.UUID,
        status: str,
        *,
        error: str | None = None,
    ) -> FitsFileModel | None:
        """Advance a FITS file through its ingest lifecycle."""
        instance = await self.session.get(FitsFileModel, file_id)
        if instance is None:
            return None

        instance.status = status
        if error is not None:
            instance.error = error

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
    ) -> Sequence[FitsFileModel]:
        """Admin-wide list across all owners; newest first."""
        stmt = select(FitsFileModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(func.lower(FitsFileModel.filename).like(pattern))
        if owner_id is not None:
            stmt = stmt.where(FitsFileModel.owner_id == owner_id)
        stmt = (
            stmt.order_by(FitsFileModel.created_at.desc())
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
        """Total FITS files matching the same filters as `search_all()`."""
        stmt = select(func.count()).select_from(FitsFileModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(func.lower(FitsFileModel.filename).like(pattern))
        if owner_id is not None:
            stmt = stmt.where(FitsFileModel.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def storage_total_bytes(self) -> int:
        """Sum of `size_bytes` across all FITS files (admin storage gauge)."""
        stmt = select(func.coalesce(func.sum(FitsFileModel.size_bytes), 0))
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)
