"""Follow-up Q&A grounded in recent catalog rows (no re-search)."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError, ExternalServiceError, ToolError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import HOUSE_STYLE
from tools.base_tool import BaseTool

# Bounded token budget for catalog rows in prompt.
_PROMPT_ROW_LIMIT: int = 10

# ~300 tokens; sentence-aware trim to avoid mid-sentence cut.
_MAX_OUTPUT_CHARS: int = 1200

_MIN_TRIMMED_CHARS: int = 400

# Cap snapshots on the assistant frame; FE shows "Grounded in N rows" footer.
_GROUNDING_FOOTER_ROW_LIMIT: int = 5

_GROUNDING_FOOTER_WEB_LIMIT: int = 3

_WEB_CONTEXT_LIMIT: int = 3


_FOLLOWUP_SYSTEM_PROMPT: str = (
    "{house_style}\n\n"
    "The user just ran a catalog search and is asking a follow-up question. "
    "The catalog rows below are the ANCHOR — the objects the user is "
    "looking at and is likely referring to with pronouns like \"it\", "
    "\"this object\", or \"the first one\". Resolve pronouns to the "
    "most-discussed row.\n\n"
    "When the user asks to compare against another well-known astronomical "
    "object (Milky Way, Sun, Sagittarius A*, Local Group, etc.) or asks a "
    "general astronomy / physics question, answer confidently and naturally "
    "from your training data. Cite a row by its name when relevant "
    "(e.g. \"M 31 in the results above…\"). Do NOT hedge with disclaimers "
    "like \"this isn't in the catalog\" or \"this isn't in your search "
    "results\" — the user knows the table is just an anchor; that kind of "
    "rail-guarding adds friction without adding value.\n\n"
    "Only refuse if the answer genuinely can't be derived from astronomy "
    "knowledge plus the rows. When refusing, suggest a concrete next step "
    "(open the row's SIMBAD references, search arXiv for recent papers, etc.). "
    "Never fabricate numbers or catalog identifiers — if you don't know a "
    "specific value, say so.\n\n"
    "Plain prose only, no markdown lists. 2-5 sentences; finish the last "
    "sentence even if you're near the budget — do not stop mid-thought.\n\n"
    "User's previous search: {query!r} via {source}.\n"
    "{web_context}"
    "Catalog rows (top {shown} of {total}):\n{rows}"
)


# Lower bar than router's web-search rule; this augments the prompt.
_RECENCY_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"latest|recent(?:ly)?|news|today|this\s+(?:week|month|year)|"
    r"2025|2026|update[ds]?|new\s+paper|new\s+study|breaking|"
    r"m[ớoò]i\s*nh[ấaă]t|g[ầaâ]n\s*[đdạa]ây|h[ôốồơ]m\s*nay"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_recency_query(question: str) -> bool:
    return bool(_RECENCY_RE.search(question))


@AgentRegistry.register
class CatalogChatAgent(BaseAgent):
    """Answer a follow-up question grounded in a recent catalog search."""

    name: ClassVar[str] = "catalog_chat"
    description: ClassVar[str] = (
        "Answer follow-up questions about the rows the user just retrieved "
        "from a catalog search (SIMBAD/NED/VizieR). Grounded in the visible "
        "table plus general astronomy knowledge; no extra catalog lookups."
    )
    capabilities: ClassVar[list[str]] = ["chat", "catalog_grounded"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
    ) -> None:
        # Optional web_search tool augments recency queries.
        super().__init__(llm=llm, tools=tools)

    async def run(
        self, task: dict[str, Any], *, state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self, task: dict[str, Any], *, state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self, task: dict[str, Any], state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        question = self._require_question(task)
        catalog_query = str(task.get("catalog_query") or "").strip() or "(unknown)"
        catalog_source = str(task.get("catalog_source") or "simbad").strip() or "simbad"
        results = task.get("catalog_results") or []
        if not isinstance(results, list) or len(results) == 0:
            raise AgentError(
                message=(
                    "CatalogChatAgent requires task['catalog_results'] to be "
                    "a non-empty list"
                ),
                code="invalid_task",
            )

        user_msg = AgentMessage(role="user", content=question)
        state.append(user_msg)
        yield user_msg

        # Best-effort web augmentation on recency-shaped questions.
        web_context = ""
        web_results: list[dict[str, Any]] = []
        web_tool = self.get_tool("web_search")
        if web_tool is not None and _looks_like_recency_query(question):
            web_results = await _safe_web_search(
                web_tool, _build_web_query(question, results)
            )
            if web_results:
                web_tool_msg = AgentMessage(
                    role="tool",
                    name="web_search",
                    content=json.dumps(web_results, default=str),
                )
                state.append(web_tool_msg)
                yield web_tool_msg
                web_context = _format_web_context(web_results)

        system_prompt = _FOLLOWUP_SYSTEM_PROMPT.format(
            house_style=HOUSE_STYLE,
            query=catalog_query,
            source=catalog_source,
            web_context=web_context,
            shown=min(len(results), _PROMPT_ROW_LIMIT),
            total=len(results),
            rows=_format_rows(results),
        )

        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.3,
            )
        except Exception as exc:
            # Catalog chat is best-effort; surface AgentError, not 500.
            raise AgentError(
                message=f"Catalog follow-up LLM call failed: {exc}",
                code="llm_failed",
            ) from exc

        answer = _truncate_at_sentence(raw or "")
        if not answer:
            answer = (
                "I couldn't generate a follow-up answer right now. The "
                "catalog rows on the right are still useful — try a more "
                "specific question, or open the row's references directly."
            )

        # Per-message snapshot so later searches don't mislabel old answers.
        row_snapshots = [
            {
                "name": str(r.get("name") or "?"),
                "object_type": (
                    str(r.get("object_type"))
                    if isinstance(r.get("object_type"), str)
                    else None
                ),
                "ra_deg": r.get("ra_deg") if isinstance(r.get("ra_deg"), (int, float)) else None,
                "dec_deg": r.get("dec_deg") if isinstance(r.get("dec_deg"), (int, float)) else None,
            }
            for r in results[:_GROUNDING_FOOTER_ROW_LIMIT]
            if isinstance(r, dict)
        ]
        grounding_extra: dict[str, Any] = {
            "query": catalog_query,
            "source": catalog_source,
            "row_count": len(results),
            "rows": row_snapshots,
        }
        if web_results:
            grounding_extra["web_sources"] = [
                {
                    "title": str(r.get("title") or "")[:120],
                    "url": str(r.get("url") or ""),
                }
                for r in web_results[:_GROUNDING_FOOTER_WEB_LIMIT]
                if isinstance(r, dict) and r.get("url")
            ]

        assistant_msg = AgentMessage(
            role="assistant",
            name=self.name,
            content=answer,
            extra={"catalog_grounding": grounding_extra},
        )
        state.append(assistant_msg)
        yield assistant_msg

        state.final_output = {
            "answer": answer,
            "row_count": len(results),
            "web_source_count": len(web_results),
        }

    @staticmethod
    def _require_question(task: dict[str, Any]) -> str:
        # FE uses question/query interchangeably.
        raw = task.get("question") or task.get("query")
        if not isinstance(raw, str) or not raw.strip():
            raise AgentError(
                message="CatalogChatAgent requires a non-empty question or query",
                code="invalid_task",
            )
        return raw.strip()


# Includes VI/CN sentence punctuation; lookahead avoids "Dr." false-hits.
_SENTENCE_END_RE: re.Pattern[str] = re.compile(r"[.!?…。!?](?=\s|$)")


def _truncate_at_sentence(text: str) -> str:
    """Trim to _MAX_OUTPUT_CHARS at sentence boundary; word boundary fallback."""
    cleaned = (text or "").strip()
    if len(cleaned) <= _MAX_OUTPUT_CHARS:
        return cleaned
    window = cleaned[:_MAX_OUTPUT_CHARS]
    last_end = -1
    for match in _SENTENCE_END_RE.finditer(window):
        last_end = match.end()
    if last_end >= _MIN_TRIMMED_CHARS:
        return window[:last_end].rstrip()
    # No sentence end; fall back to word boundary.
    word_break = window.rfind(" ")
    if word_break >= _MIN_TRIMMED_CHARS:
        return window[:word_break].rstrip() + "…"
    return window.rstrip() + "…"


def _format_rows(results: list[Any]) -> str:
    """One-line-per-row view for system prompt."""
    lines: list[str] = []
    for idx, row in enumerate(results[:_PROMPT_ROW_LIMIT], start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "?").strip() or "?"
        obj_type = row.get("object_type")
        type_str = (
            obj_type.strip()
            if isinstance(obj_type, str) and obj_type.strip()
            else "unknown type"
        )
        ra = row.get("ra_deg")
        dec = row.get("dec_deg")
        if isinstance(ra, (int, float)) and isinstance(dec, (int, float)):
            coord = f"RA={ra:.4f}° Dec={dec:.4f}°"
        else:
            coord = "no coords"
        refs = row.get("references")
        ref_count = len(refs) if isinstance(refs, list) else 0
        lines.append(
            f"  {idx}. {name} | {type_str} | {coord} | {ref_count} references"
        )
    if len(results) > _PROMPT_ROW_LIMIT:
        lines.append(
            f"  …and {len(results) - _PROMPT_ROW_LIMIT} more rows not shown."
        )
    return "\n".join(lines)


def _build_web_query(question: str, rows: list[Any]) -> str:
    """Prefix question with top row's name to resolve pronouns for the search engine."""
    head = next(
        (
            str(r.get("name")).strip()
            for r in rows
            if isinstance(r, dict)
            and isinstance(r.get("name"), str)
            and r.get("name", "").strip()
        ),
        "",
    )
    if not head:
        return question
    return f"{head} {question}"


async def _safe_web_search(tool: BaseTool, query: str) -> list[dict[str, Any]]:
    """Fail open: tool errors → empty list; catalog rows still anchor."""
    try:
        result = await tool(query=query, max_results=_WEB_CONTEXT_LIMIT)
    except (ToolError, ExternalServiceError):
        return []
    if isinstance(result, dict):
        hits = result.get("results")
        if isinstance(hits, list):
            return [r for r in hits if isinstance(r, dict)]
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    return []


def _format_web_context(hits: list[dict[str, Any]]) -> str:
    """Web results as labeled block for system prompt."""
    if not hits:
        return ""
    lines = ["Recent web results (cite as 'web source N' if used):"]
    for idx, hit in enumerate(hits[:_WEB_CONTEXT_LIMIT], start=1):
        title = str(hit.get("title") or "(untitled)").strip()
        url = str(hit.get("url") or "")
        snippet = str(hit.get("snippet") or hit.get("content") or "").strip()
        if len(snippet) > 220:
            snippet = snippet[:220].rstrip() + "…"
        line = f"  {idx}. {title}"
        if url:
            line += f" — {url}"
        if snippet:
            line += f"\n     {snippet}"
        lines.append(line)
    return "\n".join(lines) + "\n\n"
