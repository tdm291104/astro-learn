"""Flashcard generator."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import ValidationError as PydanticValidationError

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from agents.notebook._citations import chunks_to_citations
from agents.support.validator_agent import ValidatorAgent
from core.exceptions import AgentError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import FLASHCARD_GENERATOR, render
from schemas.notebook_schema import FlashcardResponse
from tools.base_tool import BaseTool

_FLASHCARD_SOURCE_CHAR_CAP: int = 8000

_LIST_CHUNKS_LIMIT: int = 50

# Pin exact shape so JSON mode + Pydantic validation are unambiguous.
_FLASHCARD_JSON_SHAPE: str = (
    "Response JSON shape (no other keys):\n"
    "{\n"
    '  "cards": [\n'
    "    {\n"
    '      "front": "<short prompt>",\n'
    '      "back": "<1-3 sentence answer>"\n'
    "    }\n"
    "  ]\n"
    "}"
)

_REPAIR_CRITERIA: list[str] = [
    "Top-level shape is exactly {\"cards\": [...]} with no other keys.",
    "Each card has both 'front' and 'back' string fields.",
    "Neither 'front' nor 'back' may be empty or whitespace-only.",
]


@AgentRegistry.register
class FlashcardAgent(BaseAgent):
    """Generate flashcards from a notebook's documents."""

    name: ClassVar[str] = "flashcard"
    description: ClassVar[str] = (
        "Generate front/back study flashcards from the notebook's documents. "
        "Front is a short prompt; back is a 1-3 sentence answer."
    )
    capabilities: ClassVar[list[str]] = ["concept_extraction", "schema_constrained_output"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        model: str | None = None,
    ) -> None:
        # `model` override (defaults to LLM_FAST_MODEL).
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
        n_cards = int(task.get("n_cards", 10))

        tool = self.get_tool("vector_search")
        if tool is None:
            raise AgentError(
                message="FlashcardAgent requires the 'vector_search' tool",
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

        # Raise on empty corpus; meaningless to generate from nothing.
        if not chunks:
            raise AgentError(
                message="No indexed chunks to generate flashcards from",
                code="no_source_material",
            )

        source = _build_numbered_source(chunks, char_cap=_FLASHCARD_SOURCE_CHAR_CAP)
        system_prompt = (
            render(FLASHCARD_GENERATOR, n_cards=n_cards)
            + f"\n\n{_FLASHCARD_JSON_SHAPE}"
        )
        user_prompt = f"Source material:\n{source}"

        # Same temp as QuizAgent: variety without drift.
        raw = await self.llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=self.model,
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        citations = chunks_to_citations(chunks)
        assistant_msg = AgentMessage(
            role="assistant",
            content=raw,
            # Citations let FE show source chips.
            extra={"citations": citations},
        )
        state.append(assistant_msg)
        yield assistant_msg

        validated = _try_validate_flashcards(raw)
        if validated is None:
            validated, repaired_raw = await self._repair_via_validator(raw)
            if validated is None:
                raise AgentError(
                    message="FlashcardAgent LLM output failed validation and repair",
                    code="invalid_output",
                    details={"raw": raw[:500]},
                )
            repaired_msg = AgentMessage(
                role="assistant",
                content=repaired_raw,
                extra={"repaired": True},
            )
            state.append(repaired_msg)
            yield repaired_msg

        state.final_output = {
            "cards": [c.model_dump() for c in validated.cards],
            "citations": citations,
        }

    async def _repair_via_validator(
        self,
        raw: str,
    ) -> tuple[FlashcardResponse | None, str]:
        """Ask ValidatorAgent to fix raw; return (validated, repaired_raw)."""
        # TODO: lift shared with QuizAgent into a mixin (v1.1).
        validator = ValidatorAgent(llm=self.llm, tools=[])
        validator_state = await validator.run(
            {
                "content": raw,
                "schema": FlashcardResponse.model_json_schema(),
                "criteria": _REPAIR_CRITERIA,
                "repair": True,
            }
        )
        output = validator_state.final_output or {}
        repaired = output.get("repaired")
        if repaired is None:
            return None, ""
        if isinstance(repaired, str):
            repaired_raw = repaired
        else:
            repaired_raw = json.dumps(repaired)
        return _try_validate_flashcards(repaired_raw), repaired_raw

    @staticmethod
    def _coerce_notebook_id(task: dict[str, Any]) -> uuid.UUID:
        raw = task.get("notebook_id")
        if raw is None:
            raise AgentError(
                message="FlashcardAgent requires task['notebook_id']",
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


# TODO: dedupe with quiz_agent helpers (v1.1).

def _build_numbered_source(
    chunks: list[dict[str, Any]],
    *,
    char_cap: int,
) -> str:
    """`[i] {text}` block stopping at char_cap."""
    out_lines: list[str] = []
    used = 0
    for i, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        line = f"[{i}] {text}"
        if used + len(line) + 1 > char_cap and out_lines:
            break
        out_lines.append(line)
        used += len(line) + 1
    return "\n".join(out_lines)


def _try_validate_flashcards(raw: str) -> FlashcardResponse | None:
    """JSON parse + Pydantic validate; None on failure."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return FlashcardResponse.model_validate(parsed)
    except PydanticValidationError:
        return None
