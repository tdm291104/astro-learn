"""Shared citation projection for notebook RAG agents."""

from __future__ import annotations

from typing import Any

# 5 chips fits the chat bubble; user can scroll full list elsewhere.
_CITATION_CAP: int = 5

_CITATION_SNIPPET_CHAR_CAP: int = 300


def chunks_to_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project vector-search chunks → FE Citation shape."""
    out: list[dict[str, Any]] = []
    for c in chunks[:_CITATION_CAP]:
        snippet = str(c.get("text") or "").strip()
        if len(snippet) > _CITATION_SNIPPET_CHAR_CAP:
            snippet = snippet[:_CITATION_SNIPPET_CHAR_CAP].rstrip() + "..."
        raw_score = c.get("score", 0.0)
        try:
            score = max(0.0, min(1.0, float(raw_score)))
        except (TypeError, ValueError):
            score = 0.0
        out.append(
            {
                "document_id": str(c.get("document_id") or ""),
                "chunk_id": str(c.get("chunk_id") or ""),
                "snippet": snippet,
                "score": score,
            }
        )
    return out
