"""DB access for CatalogCacheModel (cached catalog lookups)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.catalog_cache_model import CatalogCacheModel
from repositories.base_repository import BaseRepository


class CatalogCacheRepository(BaseRepository[CatalogCacheModel]):
    """Catalog cache table; uses ON CONFLICT DO UPDATE to dedupe races."""

    model = CatalogCacheModel

    async def get_by_query(
        self,
        query_norm: str,
        source: str,
    ) -> CatalogCacheModel | None:
        """Return row for (query_norm, source) or None; callers check expires_at."""
        stmt = select(CatalogCacheModel).where(
            CatalogCacheModel.query_norm == query_norm,
            CatalogCacheModel.source == source,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        query_norm: str,
        source: str,
        results: list[dict[str, Any]],
        ttl_days: int,
        extra: dict[str, Any] | None = None,
    ) -> CatalogCacheModel:
        """Insert-or-replace row; ttl_days <= 0 writes an already-expired row."""
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

        stmt = pg_insert(CatalogCacheModel).values(
            query_norm=query_norm,
            source=source,
            results=results,
            result_count=len(results),
            expires_at=expires_at,
            extra=extra,
        )
        # Explicit updated_at bump; server_onupdate won't fire on no-op UPDATE.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_catalog_cache_query_source",
            set_={
                "results": stmt.excluded.results,
                "result_count": stmt.excluded.result_count,
                "expires_at": stmt.excluded.expires_at,
                "extra": stmt.excluded.extra,
                "updated_at": func.now(),
            },
        ).returning(CatalogCacheModel)

        result = await self.session.execute(stmt)
        await self.session.flush()
        instance = result.scalar_one()
        # Refresh: ORM identity-map keeps stale attrs even after RETURNING.
        await self.session.refresh(instance)
        return instance

    async def purge_expired(self) -> int:
        """Delete expired rows; keeps NULL expires_at. Returns deleted count."""
        stmt = (
            delete(CatalogCacheModel)
            .where(CatalogCacheModel.expires_at.is_not(None))
            .where(CatalogCacheModel.expires_at <= func.now())
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)
