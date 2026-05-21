"""Validates or reformats output from another agent."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError
from core.llm.prompt_templates import HOUSE_STYLE

_VALIDATOR_SYSTEM_PROMPT = (
    f"{HOUSE_STYLE}\n\n"
    "You are a validation agent. Given some content and validation rules, "
    "decide whether the content satisfies the rules and (when asked) "
    "produce a corrected version.\n\n"
    "Respond with a single JSON object — no prose, no markdown fences — "
    "matching exactly:\n"
    '{"valid": <bool>, "errors": <array of short strings>, '
    '"repaired": <corrected content OR null>}\n\n'
    "Rules:\n"
    "- `errors` must be an empty array when `valid` is true.\n"
    "- When `repair` is false, set `repaired` to null.\n"
    "- When `repair` is true and the content is invalid, output a fixed "
    "version that satisfies every rule. Preserve the original structure "
    "as much as possible. When the content is already valid, `repaired` "
    "may be null."
)


@AgentRegistry.register
class ValidatorAgent(BaseAgent):
    """Validate or repair an upstream agent's output."""

    name: ClassVar[str] = "validator"
    description: ClassVar[str] = (
        "Check that an agent's output meets a schema or set of criteria. "
        "Optionally rewrite the output to make it valid."
    )
    capabilities: ClassVar[list[str]] = ["schema_check", "content_check", "repair"]

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
        content, schema, criteria, repair = self._parse_task(task)
        user_prompt = self._build_user_prompt(content, schema, criteria, repair)

        system_msg = AgentMessage(role="system", content=_VALIDATOR_SYSTEM_PROMPT)
        user_msg = AgentMessage(role="user", content=user_prompt)
        state.append(system_msg)
        yield system_msg
        state.append(user_msg)
        yield user_msg

        raw = await self.llm.complete(
            [m.to_chat_dict() for m in state.messages],
            response_format={"type": "json_object"},
            # Deterministic validation.
            temperature=0.0,
        )

        assistant_msg = AgentMessage(role="assistant", content=raw)
        state.append(assistant_msg)
        yield assistant_msg

        parsed = self._parse_llm_response(raw)
        # Force repair=null even if LLM ignored the flag.
        if not repair:
            parsed["repaired"] = None

        state.final_output = {
            "valid": bool(parsed.get("valid")),
            "errors": list(parsed.get("errors") or []),
            "repaired": parsed.get("repaired"),
        }

    @staticmethod
    def _parse_task(task: dict[str, Any]) -> tuple[Any, Any, Any, bool]:
        if "content" not in task:
            raise AgentError(
                message="ValidatorAgent requires task['content']",
                code="invalid_task",
            )
        schema = task.get("schema")
        criteria = task.get("criteria")
        if schema is None and not criteria:
            raise AgentError(
                message="ValidatorAgent needs at least one of 'schema' or 'criteria'",
                code="invalid_task",
            )
        return task["content"], schema, criteria, bool(task.get("repair", False))

    @staticmethod
    def _build_user_prompt(
        content: Any,
        schema: Any,
        criteria: Any,
        repair: bool,
    ) -> str:
        """Serialise task into a single user message."""
        # default=str handles UUIDs/datetimes.
        try:
            content_json = json.dumps(content, default=str, ensure_ascii=False)
        except TypeError:
            content_json = str(content)
        schema_str = json.dumps(schema, default=str) if schema is not None else "none"
        criteria_str = (
            "\n".join(f"- {c}" for c in criteria) if criteria else "none"
        )
        return (
            f"Content to validate:\n{content_json}\n\n"
            f"JSON schema:\n{schema_str}\n\n"
            f"Criteria:\n{criteria_str}\n\n"
            f"Repair: {'true' if repair else 'false'}"
        )

    @staticmethod
    def _parse_llm_response(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(
                message=f"Validator LLM returned non-JSON output: {raw[:200]!r}",
                code="invalid_output",
            ) from exc
        if not isinstance(parsed, dict) or "valid" not in parsed:
            raise AgentError(
                message="Validator LLM output is missing required fields",
                code="invalid_output",
                details={"raw": raw[:500]},
            )
        return parsed
