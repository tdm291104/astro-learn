"""Document summarisation with single-call and map-reduce paths."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from agents.notebook._citations import chunks_to_citations
from core.exceptions import AgentError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import SUMMARIZER, language_directive, render
from tools.base_tool import BaseTool

# 6000 chars ≈ tokens that leaves headroom for prompt+output in 16K.
SUMMARIZER_SINGLE_CALL_CHAR_LIMIT: int = 6000

_MAP_REDUCE_WINDOW_CHAR_LIMIT: int = 6000

_LIST_CHUNKS_LIMIT: int = 200

# Anchored to start to avoid mid-sentence hyphen false-positives.
_BULLET_LINE_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$"
)


@AgentRegistry.register
class SummarizerAgent(BaseAgent):
    """Summarise a notebook's documents."""

    name: ClassVar[str] = "summarizer"
    description: ClassVar[str] = (
        "Produce a concise summary of the documents in a notebook. "
        "Map-reduces large corpora to fit the LLM context."
    )
    capabilities: ClassVar[list[str]] = ["summarization", "map_reduce"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        model: str | None = None,
    ) -> None:
        # `model` override (defaults to LLM_FAST_MODEL for cheap extraction).
        super().__init__(llm=llm, tools=tools)
        self.model = model

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
        notebook_id = self._coerce_notebook_id(task)
        max_bullets = int(task.get("max_bullets", 7))
        style = task.get("style", "bullets")
        if style not in {"bullets", "paragraph"}:
            raise AgentError(
                message=f"style must be 'bullets' or 'paragraph', got {style!r}",
                code="invalid_task",
            )
        source_document_count = int(task.get("source_document_count", 0))
        language = task.get("language") or task.get("locale")
        raw_filenames = task.get("source_filenames")
        source_filenames = (
            [str(f) for f in raw_filenames if isinstance(f, str) and f]
            if isinstance(raw_filenames, list)
            else []
        )

        tool = self.get_tool("vector_search")
        if tool is None:
            raise AgentError(
                message="SummarizerAgent requires the 'vector_search' tool",
                code="missing_tool",
                details={"required": "vector_search"},
            )
        chunks: list[dict[str, Any]] = await tool(
            mode="list",
            notebook_id=notebook_id,
            limit=_LIST_CHUNKS_LIMIT,
        )

        tool_msg = AgentMessage(
            role="tool",
            name="vector_search",
            content=json.dumps(chunks),
        )
        state.append(tool_msg)
        yield tool_msg

        if not chunks:
            # Style-specific empty shape; assistant content stays human-readable.
            empty_summary: list[str] | str = (
                [] if style == "bullets" else "No documents to summarise."
            )
            user_message = (
                "No sources are indexed for this notebook yet. Upload a PDF "
                "or document to the notebook first, then ask for a summary "
                "again."
            )
            assistant_msg = AgentMessage(
                role="assistant",
                content=user_message,
            )
            state.append(assistant_msg)
            yield assistant_msg
            state.final_output = {
                "summary": empty_summary,
                "source_document_count": source_document_count,
            }
            return

        texts = [str(c.get("text") or "") for c in chunks]
        total_chars = sum(len(t) for t in texts)
        if total_chars <= SUMMARIZER_SINGLE_CALL_CHAR_LIMIT:
            raw_output = await self._summarise_once(
                texts=texts,
                max_bullets=max_bullets,
                style=style,
                language=language,
                source_filenames=source_filenames,
            )
        else:
            raw_output = await self._summarise_map_reduce(
                texts=texts,
                max_bullets=max_bullets,
                style=style,
                language=language,
                source_filenames=source_filenames,
            )

        citations = chunks_to_citations(chunks)
        assistant_msg = AgentMessage(
            role="assistant",
            content=raw_output,
            # Citations on extra so FE renders source chips.
            extra={"citations": citations},
        )
        state.append(assistant_msg)
        yield assistant_msg

        summary: list[str] | str
        if style == "bullets":
            summary = _parse_bullets(raw_output, max_bullets=max_bullets)
        else:
            summary = raw_output.strip()

        state.final_output = {
            "summary": summary,
            "source_document_count": source_document_count,
            "citations": citations,
        }

    async def _summarise_once(
        self,
        *,
        texts: list[str],
        max_bullets: int,
        style: str,
        language: str | None,
        source_filenames: list[str],
    ) -> str:
        """One LLM call over the full corpus."""
        system_prompt = _append_language(
            render(SUMMARIZER, max_bullets=max_bullets), language
        )
        user_prompt = _build_user_prompt(
            "\n\n".join(texts),
            style=style,
            max_bullets=max_bullets,
            source_filenames=source_filenames,
        )
        return await self.llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=self.model,
            temperature=0.3,
        )

    async def _summarise_map_reduce(
        self,
        *,
        texts: list[str],
        max_bullets: int,
        style: str,
        language: str | None,
        source_filenames: list[str],
    ) -> str:
        """Per-window summaries fed into a reduce step."""
        # Map uses fewer bullets (granularity lost in reduce anyway).
        windows = _group_into_windows(texts, _MAP_REDUCE_WINDOW_CHAR_LIMIT)
        per_window_bullets = max(3, max_bullets // 2)

        partials: list[str] = []
        map_system_prompt = _append_language(
            render(SUMMARIZER, max_bullets=per_window_bullets), language
        )
        for window_text in windows:
            user_prompt = _build_user_prompt(
                window_text,
                style="bullets",
                max_bullets=per_window_bullets,
                source_filenames=source_filenames,
            )
            partial = await self.llm.complete(
                [
                    {"role": "system", "content": map_system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.3,
            )
            partials.append(partial)

        reduce_system_prompt = _append_language(
            render(SUMMARIZER, max_bullets=max_bullets), language
        )
        combined = "\n\n".join(
            f"--- partial {i + 1} ---\n{p}" for i, p in enumerate(partials)
        )
        reduce_user_prompt = _build_user_prompt(
            combined,
            style=style,
            max_bullets=max_bullets,
            source_filenames=source_filenames,
        )
        return await self.llm.complete(
            [
                {"role": "system", "content": reduce_system_prompt},
                {"role": "user", "content": reduce_user_prompt},
            ],
            model=self.model,
            temperature=0.3,
        )

    @staticmethod
    def _coerce_notebook_id(task: dict[str, Any]) -> uuid.UUID:
        raw = task.get("notebook_id")
        if raw is None:
            raise AgentError(
                message="SummarizerAgent requires task['notebook_id']",
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


def _append_language(system_prompt: str, language: str | None) -> str:
    """Append explicit OUTPUT LANGUAGE clause when caller pinned a locale."""
    directive = language_directive(language)
    if not directive:
        return system_prompt
    return f"{system_prompt}\n\n{directive}"


def _build_user_prompt(
    source_text: str,
    *,
    style: str,
    max_bullets: int,
    source_filenames: list[str] | None = None,
) -> str:
    """Wrap source text with style instruction + anchoring context."""
    # `-` prefix lets _parse_bullets reliably extract.
    if style == "bullets":
        instruction = (
            f"Produce up to {max_bullets} bullet points. Each bullet starts "
            "with '- ' on its own line. No headings, no preamble."
        )
    else:
        instruction = (
            "Produce a single paragraph of 3-5 sentences. No bullets, "
            "no headings, no preamble."
        )

    context_block = ""
    if source_filenames:
        if len(source_filenames) == 1:
            context_block = (
                f"You are summarising ONE paper: {source_filenames[0]!r}.\n"
                "All bullets must describe THIS paper's own contributions. "
                "If the source text below includes a references/bibliography "
                "section, ignore the cited works — they are background, not "
                "the paper itself.\n\n"
            )
        else:
            joined = ", ".join(repr(f) for f in source_filenames[:5])
            extra = (
                f" (and {len(source_filenames) - 5} more)"
                if len(source_filenames) > 5
                else ""
            )
            context_block = (
                f"You are summarising {len(source_filenames)} documents: "
                f"{joined}{extra}.\n"
                "Bullets must describe what these documents themselves say. "
                "Do not summarise references they cite.\n\n"
            )

    return f"{context_block}{instruction}\n\nSource:\n{source_text}"


def _group_into_windows(texts: list[str], window_char_limit: int) -> list[str]:
    """Greedy-pack texts into windows under char limit."""
    # Don't sub-split chunks; they came from upstream chunker.
    windows: list[str] = []
    current: list[str] = []
    current_len = 0
    separator_cost = len("\n\n")

    for text in texts:
        added_cost = len(text) + (separator_cost if current else 0)
        if current and current_len + added_cost > window_char_limit:
            windows.append("\n\n".join(current))
            current = [text]
            current_len = len(text)
        else:
            current.append(text)
            current_len += added_cost

    if current:
        windows.append("\n\n".join(current))
    return windows


def _parse_bullets(raw: str, *, max_bullets: int) -> list[str]:
    """Extract bullet lines; fall back to non-empty lines if LLM ignored format."""
    bullets: list[str] = []
    for line in raw.splitlines():
        match = _BULLET_LINE_RE.match(line)
        if match:
            bullets.append(match.group(1).strip())

    if not bullets:
        bullets = [line.strip() for line in raw.splitlines() if line.strip()]

    return bullets[:max_bullets]
