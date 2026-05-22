"""Structural queries over notebooks/documents — bypasses vector search.

Use this when the user asks about *structure* of their data (counts, doc
names, page content, latest upload) rather than *semantics*. Vector search
is great for "what does the paper say about X" but terrible for "how many
documents are in this notebook" — it would return arbitrary chunks instead
of an accurate count.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from memory.long_term.vector_store import VectorStore
from repositories.document_repository import DocumentRepository
from repositories.notebook_repository import NotebookRepository
from tools.base_tool import BaseTool

# Cap to keep prompt payloads bounded — agents that need more can paginate.
_DEFAULT_LIST_LIMIT: int = 20
_MAX_LIST_LIMIT: int = 100

Operation = Literal[
    "count_notebooks",
    "list_notebooks",
    "count_documents",
    "list_documents",
    "latest_document",
    "find_document",
    "notebook_info",
    "document_page",
]


class NotebookMetadataInput(BaseModel):
    """Input shape — owner_id auto-injected by the agent, not the LLM."""

    operation: Operation
    owner_id: uuid.UUID | None = None
    notebook_id: uuid.UUID | None = None
    # Filename substring (case-insensitive) for find_document / document_page.
    name_like: str | None = Field(None, max_length=255)
    # 1-based page number for document_page.
    page: int | None = Field(None, ge=1)
    limit: int = Field(_DEFAULT_LIST_LIMIT, ge=1, le=_MAX_LIST_LIMIT)

    @model_validator(mode="after")
    def _check_required_args(self) -> NotebookMetadataInput:
        op = self.operation
        if op in {"count_notebooks", "list_notebooks"}:
            if self.owner_id is None:
                raise ValueError(f"operation={op!r} requires owner_id")
        elif op == "count_documents":
            if self.owner_id is None and self.notebook_id is None:
                raise ValueError(
                    "count_documents requires owner_id or notebook_id"
                )
        elif op in {"list_documents", "notebook_info"}:
            if self.notebook_id is None:
                raise ValueError(f"operation={op!r} requires notebook_id")
        elif op == "latest_document":
            if self.owner_id is None and self.notebook_id is None:
                raise ValueError(
                    "latest_document requires owner_id or notebook_id"
                )
        elif op == "find_document":
            if self.notebook_id is None:
                raise ValueError("find_document requires notebook_id")
            if not self.name_like or not self.name_like.strip():
                raise ValueError("find_document requires name_like")
        elif op == "document_page":
            if self.notebook_id is None:
                raise ValueError("document_page requires notebook_id")
            if self.page is None:
                raise ValueError("document_page requires page")
            if not self.name_like or not self.name_like.strip():
                raise ValueError("document_page requires name_like")
        return self


class NotebookMetadataTool(BaseTool):
    """DB-backed structural queries about notebooks + uploaded documents."""

    name: ClassVar[str] = "notebook_metadata"
    description: ClassVar[str] = (
        "Answer structural questions about the user's notebooks and uploaded "
        "documents (counts, file names, latest upload, document metadata, "
        "specific page content). Use this for 'how many', 'list', 'what is "
        "the name of', 'page N says what' style questions — NOT for "
        "semantic Q&A about the documents' content."
    )
    input_schema: ClassVar[type[BaseModel]] = NotebookMetadataInput

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: VectorStore,
    ) -> None:
        # Tool owns its own session lifecycle so agents don't have to hold one.
        self._session_factory = session_factory
        self._vector_store = vector_store

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        op: Operation = kwargs["operation"]
        owner_id: uuid.UUID | None = kwargs.get("owner_id")
        notebook_id: uuid.UUID | None = kwargs.get("notebook_id")
        name_like: str | None = kwargs.get("name_like")
        page: int | None = kwargs.get("page")
        limit: int = kwargs.get("limit", _DEFAULT_LIST_LIMIT)

        async with self._session_factory() as session:
            notebooks = NotebookRepository(session)
            documents = DocumentRepository(session)

            if op == "count_notebooks":
                assert owner_id is not None
                count = await notebooks.count_search_all(owner_id=owner_id)
                return {"operation": op, "count": count}

            if op == "list_notebooks":
                assert owner_id is not None
                rows = await notebooks.list_for_owner(owner_id, limit=limit)
                return {
                    "operation": op,
                    "count": len(rows),
                    "notebooks": [
                        {
                            "id": str(nb.id),
                            "title": nb.title,
                            "description": nb.description,
                            "created_at": nb.created_at.isoformat()
                            if nb.created_at
                            else None,
                        }
                        for nb in rows
                    ],
                }

            if op == "count_documents":
                if notebook_id is not None:
                    count = await documents.count_for_notebook(notebook_id)
                    return {"operation": op, "count": count, "scope": "notebook"}
                # owner-scoped fallback: count via filter on owner_id.
                assert owner_id is not None
                count = await documents.count(owner_id=owner_id)
                return {"operation": op, "count": count, "scope": "owner"}

            if op == "list_documents":
                assert notebook_id is not None
                rows = await documents.list_for_notebook(notebook_id, limit=limit)
                return {
                    "operation": op,
                    "count": len(rows),
                    "documents": [_doc_summary(d) for d in rows],
                }

            if op == "latest_document":
                rows = await _latest_documents(
                    documents,
                    owner_id=owner_id,
                    notebook_id=notebook_id,
                    limit=1,
                )
                if not rows:
                    return {"operation": op, "document": None}
                return {"operation": op, "document": _doc_summary(rows[0])}

            if op == "notebook_info":
                assert notebook_id is not None
                nb = await notebooks.get(notebook_id)
                if nb is None:
                    return {"operation": op, "notebook": None}
                doc_count = await documents.count_for_notebook(notebook_id)
                return {
                    "operation": op,
                    "notebook": {
                        "id": str(nb.id),
                        "title": nb.title,
                        "description": nb.description,
                        "created_at": nb.created_at.isoformat()
                        if nb.created_at
                        else None,
                        "document_count": doc_count,
                    },
                }

            if op == "find_document":
                assert notebook_id is not None and name_like is not None
                rows = await documents.list_for_notebook(notebook_id, limit=200)
                matches = _filter_by_name(rows, name_like)
                return {
                    "operation": op,
                    "name_like": name_like,
                    "matches": [_doc_summary(d) for d in matches[:limit]],
                }

            if op == "document_page":
                assert (
                    notebook_id is not None
                    and name_like is not None
                    and page is not None
                )
                rows = await documents.list_for_notebook(notebook_id, limit=200)
                matches = _filter_by_name(rows, name_like)
                if not matches:
                    return {
                        "operation": op,
                        "name_like": name_like,
                        "page": page,
                        "document": None,
                        "chunks": [],
                    }
                # Pick the best (first) name match; ambiguous names surfaced as
                # `candidates` so the calling LLM can ask the user to clarify.
                doc = matches[0]
                chunks = await self._page_chunks(notebook_id, doc.id, page)
                return {
                    "operation": op,
                    "name_like": name_like,
                    "page": page,
                    "document": _doc_summary(doc),
                    "candidates": [_doc_summary(d) for d in matches[1:5]],
                    "chunks": chunks,
                }

            # Shouldn't reach — Pydantic literal narrows op.
            raise ValueError(f"Unhandled operation: {op!r}")

    async def _page_chunks(
        self,
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        page: int,
    ) -> list[dict[str, Any]]:
        """Pull chunks tagged with `metadata.page == page` for one document."""
        # list_chunks returns up to 1000 chunks; filter in Python because the
        # vector store interface doesn't expose page filters today.
        all_chunks = await self._vector_store.list_chunks(
            notebook_id=notebook_id, limit=1000
        )
        out: list[dict[str, Any]] = []
        for chunk in all_chunks:
            chunk_dict = chunk.model_dump(mode="json")
            if str(chunk_dict.get("document_id")) != str(document_id):
                continue
            meta = chunk_dict.get("metadata") or {}
            raw_page = meta.get("page")
            try:
                chunk_page = int(raw_page) if raw_page is not None else None
            except (TypeError, ValueError):
                chunk_page = None
            if chunk_page == page:
                out.append({
                    "chunk_id": chunk_dict.get("chunk_id"),
                    "text": chunk_dict.get("text"),
                    "page": chunk_page,
                })
        return out


def _doc_summary(doc: Any) -> dict[str, Any]:
    """Project DocumentModel to a JSON-friendly summary."""
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "indexed_chunks": doc.indexed_chunks,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


async def _latest_documents(
    documents: DocumentRepository,
    *,
    owner_id: uuid.UUID | None,
    notebook_id: uuid.UUID | None,
    limit: int,
) -> list[Any]:
    """Notebook scope wins when both are provided; mirrors list_for_notebook."""
    if notebook_id is not None:
        rows = await documents.list_for_notebook(notebook_id, limit=limit)
        return list(rows)
    assert owner_id is not None
    # No owner-wide list method exists; reuse paginated search via base repo.
    # DocumentRepository.list with owner_id sorted by created_at desc.
    from sqlalchemy import select

    from models.document_model import DocumentModel

    stmt = (
        select(DocumentModel)
        .where(DocumentModel.owner_id == owner_id)
        .order_by(DocumentModel.created_at.desc())
        .limit(limit)
    )
    result = await documents.session.execute(stmt)
    return list(result.scalars().all())


def _filter_by_name(rows: Any, name_like: str) -> list[Any]:
    """Case-insensitive substring match; preserves source order (newest first)."""
    needle = name_like.strip().lower()
    return [
        r for r in rows
        if isinstance(r.filename, str) and needle in r.filename.lower()
    ]
