"""Qdrant adapter implementing the `VectorBackend` Protocol."""

from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)


class QdrantBackend:
    """VectorBackend over Qdrant async client."""

    def __init__(self, client: AsyncQdrantClient) -> None:
        self.client = client

    async def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> None:
        # Don't auto-create collection: would mask schema drift.
        qpoints = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]
        await self.client.upsert(collection_name=collection, points=qpoints)

    async def query(
        self,
        collection: str,
        embedding: list[float],
        *,
        top_k: int,
        filter_: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """`top_k` nearest neighbours; optional filter."""
        # `search` removed in qdrant-client 1.17; use query_points.
        response = await self.client.query_points(
            collection_name=collection,
            query=embedding,
            limit=top_k,
            query_filter=self._to_qdrant_filter(filter_) if filter_ else None,
        )
        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload or {},
            }
            for hit in response.points
        ]

    async def scroll(
        self,
        collection: str,
        *,
        filter_: dict[str, Any] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Up to `limit` matching points, no ANN scoring. Single page only."""
        response, _next_offset = await self.client.scroll(
            collection_name=collection,
            scroll_filter=self._to_qdrant_filter(filter_) if filter_ else None,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id": point.id,
                "payload": point.payload or {},
            }
            for point in response
        ]

    async def delete(self, collection: str, filter_: dict[str, Any]) -> int:
        """Delete matching points; return count (two roundtrips since delete has no count)."""
        qfilter = self._to_qdrant_filter(filter_)

        count_result = await self.client.count(
            collection_name=collection,
            count_filter=qfilter,
            exact=True,
        )
        matched = count_result.count

        if matched > 0:
            await self.client.delete(
                collection_name=collection,
                points_selector=qfilter,
            )
        return matched

    @staticmethod
    def _to_qdrant_filter(filter_: dict[str, Any]) -> Filter:
        """AND-of-equalities Qdrant Filter from flat dict."""
        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filter_.items()
            ]
        )
