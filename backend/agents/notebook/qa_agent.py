"""Question-answering over indexed documents (NotebookLM-style)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.config import get_settings
from core.exceptions import AgentError
from core.llm.prompt_templates import QA_FROM_CONTEXT, render

# Context cap; full chunk available via citations.
_CONTEXT_SNIPPET_CHAR_CAP: int = 300

_CITATION_SNIPPET_CHAR_CAP: int = 300

_REFUSAL_TEXT: str = "I cannot answer from the provided documents."


@AgentRegistry.register
class QAAgent(BaseAgent):
    """Answer a question grounded in indexed documents."""

    name: ClassVar[str] = "qa"
    description: ClassVar[str] = (
        "Answer a question using only the documents indexed for the given "
        "notebook. Returns citations pointing at the source chunks."
    )
    capabilities: ClassVar[list[str]] = ["rag", "citations", "refusal_when_unsure"]

    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self,
        task: dict[str, Any],
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        question = self._require_question(task)
        notebook_id = self._coerce_notebook_id(task)
        top_k = int(task.get("top_k", 5))

        user_msg = AgentMessage(role="user", content=question)
        state.append(user_msg)
        yield user_msg

        tool = self.get_tool("vector_search")
        if tool is None:
            raise AgentError(
                message="QAAgent requires the 'vector_search' tool",
                code="missing_tool",
                details={"required": "vector_search"},
            )
        # Two-stage retrieval: pull a wider candidate pool, then cross-encoder
        # rerank to top_k. Reranker is the single biggest precision lever per
        # the retrieval evaluation (hit@1 0.25 -> 0.63, MRR 0.48 -> 0.68).
        candidate_multiplier = max(
            1, int(task.get("rerank_candidates_mult") or get_settings().RERANK_CANDIDATE_MULTIPLIER)
        )
        wide_top_k = min(top_k * candidate_multiplier, 20)  # VectorSearchInput caps top_k at 20
        candidates: list[dict[str, Any]] = await tool(
            mode="search",
            query=question,
            notebook_id=notebook_id,
            top_k=wide_top_k,
        )
        matches = await self._rerank(question, candidates, top_n=top_k)

        tool_msg = AgentMessage(
            role="tool",
            name="vector_search",
            content=json.dumps(matches),
        )
        state.append(tool_msg)
        yield tool_msg

        if not matches:
            refusal = AgentMessage(role="assistant", content=_REFUSAL_TEXT)
            state.append(refusal)
            yield refusal
            state.final_output = {"answer": _REFUSAL_TEXT, "citations": []}
            return

        context = _build_numbered_context(matches)
        system_prompt = render(QA_FROM_CONTEXT, context=context)

        # Low temp: grounded over creative.
        answer = await self.llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.2,
        )
        answer = (answer or "").strip() or _REFUSAL_TEXT

        citations = [_match_to_citation(m) for m in matches]
        assistant_msg = AgentMessage(
            role="assistant",
            content=answer,
            # Citations on extra so FE chat bubble can render source chips.
            extra={"citations": citations},
        )
        state.append(assistant_msg)
        yield assistant_msg

        state.final_output = {"answer": answer, "citations": citations}

    async def _rerank(
        self,
        question: str,
        candidates: list[dict[str, Any]],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Cross-encoder rerank; on failure, fall back to vector-score order."""
        if len(candidates) <= top_n:
            return candidates
        try:
            ranked = await self.llm.rerank(
                question,
                [str(c.get("text") or "") for c in candidates],
                top_n=top_n,
            )
        except Exception:
            # Reranker is best-effort; vector ordering still works.
            return candidates[:top_n]
        out: list[dict[str, Any]] = []
        for idx, score in ranked:
            if 0 <= idx < len(candidates):
                hit = dict(candidates[idx])
                hit["score"] = score
                out.append(hit)
        return out

    @staticmethod
    def _require_question(task: dict[str, Any]) -> str:
        question = task.get("question")
        if not isinstance(question, str) or not question.strip():
            raise AgentError(
                message="QAAgent requires task['question'] (non-empty str)",
                code="invalid_task",
            )
        return question.strip()

    @staticmethod
    def _coerce_notebook_id(task: dict[str, Any]) -> uuid.UUID:
        raw = task.get("notebook_id")
        if raw is None:
            raise AgentError(
                message="QAAgent requires task['notebook_id']",
                code="invalid_task",
            )
        if isinstance(raw, uuid.UUID):
            return raw
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError) as exc:
            raise AgentError(
                message=f"Invalid notebook_id: {raw!r}",
                code="invalid_task",
            ) from exc


def _build_numbered_context(matches: list[dict[str, Any]]) -> str:
    """`[i] {snippet}` block from matches."""
    lines: list[str] = []
    for i, match in enumerate(matches, start=1):
        text = str(match.get("text") or "").strip()
        if len(text) > _CONTEXT_SNIPPET_CHAR_CAP:
            text = text[:_CONTEXT_SNIPPET_CHAR_CAP].rstrip() + "..."
        lines.append(f"[{i}] {text}")
    return "\n".join(lines)


def _match_to_citation(match: dict[str, Any]) -> dict[str, Any]:
    """Normalise vector-search hit into Citation schema shape."""
    snippet = str(match.get("text") or "").strip()
    if len(snippet) > _CITATION_SNIPPET_CHAR_CAP:
        snippet = snippet[:_CITATION_SNIPPET_CHAR_CAP].rstrip() + "..."
    raw_score = match.get("score", 0.0)
    try:
        score = max(0.0, min(1.0, float(raw_score)))
    except (TypeError, ValueError):
        score = 0.0
    # Page lives inside metadata (VectorMatch.metadata carries chunker payload).
    page: int | None = None
    raw_page = (match.get("metadata") or {}).get("page")
    if raw_page is not None:
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            page = None
    return {
        "document_id": match["document_id"],
        "chunk_id": str(match.get("chunk_id") or ""),
        "snippet": snippet,
        "score": score,
        "page": page,
    }
