"""Semantic search over indexed documents — wraps VectorStore."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from memory.long_term.vector_store import VectorStore
from tools.base_tool import BaseTool

SearchMode = Literal["search", "list"]


class VectorSearchInput(BaseModel):
    mode: SearchMode = "search"
    query: str | None = Field(None, max_length=4000)
    notebook_id: uuid.UUID | None = None
    top_k: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    # mode='list' only: corpus sampling, not narrow retrieval.
    limit: int = Field(200, ge=1, le=1000)

    @model_validator(mode="after")
    def _validate_mode_requirements(self) -> VectorSearchInput:
        if self.mode == "search":
            if not self.query or not self.query.strip():
                raise ValueError("mode='search' requires a non-empty 'query'")
        else:
            if self.notebook_id is None:
                raise ValueError("mode='list' requires 'notebook_id'")
        return self


class VectorSearchTool(BaseTool):
    """Semantic search (or queryless scan) over the configured vector backend."""

    name: ClassVar[str] = "vector_search"
    description: ClassVar[str] = (
        "Semantic search over previously-indexed documents. Returns chunks "
        "most relevant to the query, with provenance for citations. Use "
        "mode='list' to fetch up to `limit` chunks for a notebook without a "
        "query (corpus sampling for summarisation / quiz generation)."
    )
    input_schema: ClassVar[type[BaseModel]] = VectorSearchInput

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        mode: SearchMode = kwargs.get("mode", "search")
        if mode == "list":
            matches = await self.store.list_chunks(
                notebook_id=kwargs["notebook_id"],
                limit=kwargs.get("limit", 200),
            )
        else:
            matches = await self.store.search(
                query=kwargs["query"],
                notebook_id=kwargs.get("notebook_id"),
                top_k=kwargs.get("top_k", 5),
                min_score=kwargs.get("min_score", 0.0),
            )
        return [m.model_dump(mode="json") for m in matches]
