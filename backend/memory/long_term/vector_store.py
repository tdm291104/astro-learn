"""Backend-agnostic interface over the configured vector DB."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.llm.llm_client import LLMClient

# Fixed namespace: same chunk_id deterministically maps to same point UUID.
_CHUNK_ID_NAMESPACE: uuid.UUID = uuid.UUID("6f1b2d4e-1c0a-4f5b-8a9c-2d3e4f5a6b7c")


class VectorChunk(BaseModel):
    chunk_id: str = Field(..., description="Stable id; use `f'{document_id}:{i}'`.")
    document_id: uuid.UUID
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorMatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: uuid.UUID
    text: str
    score: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorBackend(Protocol):
    """Duck-typed interface concrete backends must satisfy."""

    async def upsert(self, collection: str, points: list[dict[str, Any]]) -> None: ...
    async def query(
        self,
        collection: str,
        embedding: list[float],
        *,
        top_k: int,
        filter_: dict[str, Any] | None,
    ) -> list[dict[str, Any]]: ...
    async def scroll(
        self,
        collection: str,
        *,
        filter_: dict[str, Any] | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...
    async def delete(self, collection: str, filter_: dict[str, Any]) -> int: ...


class VectorStore:
    """High-level vector operations used by tools and workers."""

    def __init__(
        self,
        backend: VectorBackend,
        llm: LLMClient,
        *,
        collection: str = "astrolearn",
    ) -> None:
        self.backend = backend
        self.llm = llm
        self.collection = collection

    async def index(
        self,
        chunks: list[VectorChunk],
        *,
        notebook_id: uuid.UUID | None = None,
    ) -> int:
        """Embed and upsert; returns count indexed."""
        if not chunks:
            return 0

        embeddings = await self.llm.embed([c.text for c in chunks])
        await self._ensure_collection(dimension=len(embeddings[0]))

        points = [
            {
                "id": str(uuid.uuid5(_CHUNK_ID_NAMESPACE, chunk.chunk_id)),
                "vector": vector,
                "payload": _build_payload(chunk, notebook_id),
            }
            for chunk, vector in zip(chunks, embeddings, strict=True)
        ]
        await self.backend.upsert(self.collection, points)
        return len(points)

    async def search(
        self,
        query: str,
        *,
        notebook_id: uuid.UUID | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[VectorMatch]:
        """Embed query; return top matches scoped to notebook."""
        # Qdrant cosine [-1,1] clamped to [0,1] in _hit_to_match.
        embedding = (await self.llm.embed([query]))[0]
        filter_ = {"notebook_id": str(notebook_id)} if notebook_id is not None else None

        hits = await self.backend.query(
            self.collection,
            embedding,
            top_k=top_k,
            filter_=filter_,
        )
        return [_hit_to_match(hit) for hit in hits if hit["score"] >= min_score]

    async def list_chunks(
        self,
        *,
        notebook_id: uuid.UUID,
        limit: int = 200,
    ) -> list[VectorMatch]:
        """Up to `limit` unranked chunks via Qdrant scroll (score=1.0)."""
        hits = await self.backend.scroll(
            self.collection,
            filter_={"notebook_id": str(notebook_id)},
            limit=limit,
        )
        return [_scroll_hit_to_match(hit) for hit in hits]

    async def delete_document(self, document_id: uuid.UUID) -> int:
        return await self.backend.delete(
            self.collection, {"document_id": str(document_id)}
        )

    async def delete_notebook(self, notebook_id: uuid.UUID) -> int:
        return await self.backend.delete(
            self.collection, {"notebook_id": str(notebook_id)}
        )

    async def _ensure_collection(self, *, dimension: int) -> None:
        """Idempotently create collection sized to embedding dim."""
        from qdrant_client.models import Distance, VectorParams

        client = getattr(self.backend, "client", None)
        if client is None:
            # Non-Qdrant backend (test fake); assume lifecycle handled.
            return
        if await client.collection_exists(self.collection):
            return
        await client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )


def _build_payload(
    chunk: VectorChunk, notebook_id: uuid.UUID | None
) -> dict[str, Any]:
    """Qdrant payload; stable keys can't be overwritten by chunk.metadata."""
    payload: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "document_id": str(chunk.document_id),
        "text": chunk.text,
    }
    if notebook_id is not None:
        payload["notebook_id"] = str(notebook_id)
    for k, v in chunk.metadata.items():
        if k not in payload:
            payload[k] = v
    return payload


def _hit_to_match(hit: dict[str, Any]) -> VectorMatch:
    payload = hit.get("payload") or {}
    extra = {
        k: v
        for k, v in payload.items()
        if k not in {"chunk_id", "document_id", "text", "notebook_id"}
    }
    return VectorMatch(
        chunk_id=str(payload.get("chunk_id") or hit.get("id") or ""),
        document_id=uuid.UUID(payload["document_id"]),
        text=str(payload.get("text") or ""),
        # Clamp Qdrant cosine [-1,1] to schema [0,1].
        score=max(0.0, min(1.0, float(hit["score"]))),
        metadata=extra,
    )


def _scroll_hit_to_match(hit: dict[str, Any]) -> VectorMatch:
    """Scroll hit (no score) → VectorMatch with score=1.0."""
    payload = hit.get("payload") or {}
    extra = {
        k: v
        for k, v in payload.items()
        if k not in {"chunk_id", "document_id", "text", "notebook_id"}
    }
    return VectorMatch(
        chunk_id=str(payload.get("chunk_id") or hit.get("id") or ""),
        document_id=uuid.UUID(payload["document_id"]),
        text=str(payload.get("text") or ""),
        score=1.0,
        metadata=extra,
    )
