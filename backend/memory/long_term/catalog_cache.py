"""Astronomical catalog lookup cache for name-form SIMBAD/NED/VizieR queries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from repositories.catalog_cache_repository import CatalogCacheRepository


class CatalogCache:
    """Wrapper over CatalogCacheRepository."""

    def __init__(
        self,
        repo: CatalogCacheRepository,
        *,
        default_ttl_days: int,
    ) -> None:
        self.repo = repo
        self.default_ttl_days = default_ttl_days

    @staticmethod
    def normalize(query: str) -> str:
        """Lowercase + strip outer whitespace; preserve interior spaces."""
        return query.lower().strip()

    async def lookup(
        self,
        query: str,
        source: str,
    ) -> list[dict[str, Any]] | None:
        """Cached results or None on miss/expiry (expired = miss)."""
        query_norm = self.normalize(query)
        if not query_norm:
            return None
        row = await self.repo.get_by_query(query_norm, source)
        if row is None:
            return None
        if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
            return None
        return list(row.results or [])

    async def store(
        self,
        query: str,
        source: str,
        results: list[dict[str, Any]],
        *,
        ttl_days: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Idempotent cache write; empty normalised query is skipped."""
        query_norm = self.normalize(query)
        if not query_norm:
            return
        await self.repo.upsert(
            query_norm=query_norm,
            source=source,
            results=results,
            ttl_days=ttl_days if ttl_days is not None else self.default_ttl_days,
            extra=extra,
        )
