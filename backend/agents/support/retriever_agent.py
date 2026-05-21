"""RAG retrieval helper that fronts the vector store for other agents."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError

_EXPAND_SYSTEM_PROMPT = (
    "Rewrite the user's search query to be more effective for semantic "
    "vector search over indexed documents. Add likely synonyms or "
    "domain terms. Keep it under 30 words. Respond with ONLY the rewritten "
    "query — no preamble, no quoting, no explanation."
)


# Not registered: notebook agents use VectorSearchTool directly.
class RetrieverAgent(BaseAgent):
    """Run a vector search and return ranked chunks."""

    name: ClassVar[str] = "retriever"
    description: ClassVar[str] = (
        "Semantic retrieval over indexed documents. Used by other agents "
        "that need grounded context."
    )
    capabilities: ClassVar[list[str]] = ["vector_search", "query_expansion"]

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
        query = self._require_query(task)
        notebook_id = task.get("notebook_id")
        top_k = task.get("top_k", 5)
        min_score = task.get("min_score", 0.0)
        expand = bool(task.get("expand_query"))

        user_msg = AgentMessage(role="user", content=query)
        state.append(user_msg)
        yield user_msg

        query_used = query
        if expand:
            rewritten = await self._expand(query)
            assistant_msg = AgentMessage(role="assistant", content=rewritten)
            state.append(assistant_msg)
            yield assistant_msg
            query_used = rewritten

        tool = self.get_tool("vector_search")
        if tool is None:
            raise AgentError(
                message="RetrieverAgent requires the 'vector_search' tool",
                code="missing_tool",
                details={"required": "vector_search"},
            )

        matches = await tool(
            query=query_used,
            notebook_id=notebook_id,
            top_k=top_k,
            min_score=min_score,
        )

        tool_msg = AgentMessage(
            role="tool",
            name="vector_search",
            content=json.dumps(matches),
        )
        state.append(tool_msg)
        yield tool_msg

        state.final_output = {
            "matches": matches,
            "query_used": query_used,
            "expanded": expand,
        }

    async def _expand(self, query: str) -> str:
        """LLM-rewrite query for better semantic search; falls back to original."""
        rewritten = await self.llm.complete(
            [
                {"role": "system", "content": _EXPAND_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.2,
        )
        return rewritten.strip() or query

    @staticmethod
    def _require_query(task: dict[str, Any]) -> str:
        query = task.get("query")
        if not isinstance(query, str) or not query.strip():
            raise AgentError(
                message="RetrieverAgent requires task['query'] (non-empty str)",
                code="invalid_task",
            )
        return query.strip()
