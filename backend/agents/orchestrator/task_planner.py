"""LLM-driven decomposition of a task into a sequence of agent calls."""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, Field, ValidationError

from agents.base.agent_registry import AgentRegistry
from core.exceptions import AgentError
from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import (
    ORCHESTRATOR_PLANNER,
    build_planner_agents_block,
    build_planner_context_block,
    render,
)

# Total attempts = _MAX_RETRIES + 1; more rarely helps.
_MAX_RETRIES: Final[int] = 1


_RETRY_ERROR_SNIPPET_CHARS: Final[int] = 200


class PlannedStep(BaseModel):
    agent_name: str = Field(..., description="Registry key of the agent to invoke.")
    task_input: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None


class TaskPlan(BaseModel):
    steps: list[PlannedStep] = Field(default_factory=list)
    summary: str | None = None


class TaskPlanner:
    """Decompose a task into ordered PlannedSteps."""

    def __init__(
        self,
        llm: LLMClient,
        available_agents: list[str],
    ) -> None:
        self.llm = llm
        self.available_agents = available_agents

    async def plan(
        self,
        task: dict[str, Any],
        *,
        available_agents: list[str] | None = None,
    ) -> TaskPlan:
        """Return TaskPlan with one retry on failure.

        `available_agents` overrides the default list per call — used by the
        orchestrator to hide agents whose required resource (notebook_id /
        file_id) isn't bound, preventing the planner LLM from picking an
        agent that will then crash on validation.
        """
        effective_agents = (
            list(available_agents)
            if available_agents is not None
            else list(self.available_agents)
        )
        if not effective_agents:
            raise AgentError(
                message="No agents available for planning",
                code="empty_registry",
            )

        system_prompt = self._render_system_prompt(task, effective_agents)
        user_prompt = f"User task:\n{json.dumps(task, default=str)}"

        last_error: str | None = None
        for attempt in range(_MAX_RETRIES + 1):
            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            if attempt > 0 and last_error:
                # Corrective nudge; schema already in system prompt.
                messages.append({
                    "role": "user",
                    "content": (
                        "Return only valid JSON matching the schema above. "
                        f"Previous attempt failed: "
                        f"{last_error[:_RETRY_ERROR_SNIPPET_CHARS]}"
                    ),
                })
            try:
                raw = await self.llm.complete(
                    messages,
                    response_format={"type": "json_object"},
                    # Deterministic plan; creativity belongs in agent inputs.
                    temperature=0.0,
                )
                plan = self._parse_plan(raw)
                self._validate_agent_names(plan, effective_agents)
                return plan
            except Exception as exc:
                # Broad: LLMError, AgentError, ValidationError all retry.
                last_error = f"{type(exc).__name__}: {exc}"

        raise AgentError(
            message="Could not plan this task — try rephrasing your request",
            code="planner_failed",
            details={"last_error": last_error or "unknown"},
        )

    def _render_system_prompt(
        self,
        task: dict[str, Any],
        effective_agents: list[str] | None = None,
    ) -> str:
        """Build planner system prompt with live registry descriptions."""
        agents_for_prompt = effective_agents or self.available_agents
        descriptions: dict[str, str] = {}
        for name in agents_for_prompt:
            try:
                cls = AgentRegistry.get(name)
            except Exception:
                continue
            descriptions[name] = getattr(cls, "description", "") or ""
        agents_block = build_planner_agents_block(
            agents_for_prompt, descriptions
        )
        context_block = build_planner_context_block(task)
        return render(
            ORCHESTRATOR_PLANNER,
            agents_block=agents_block,
            context_block=context_block,
        )

    @staticmethod
    def _parse_plan(raw: str) -> TaskPlan:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(
                message=f"Planner LLM returned non-JSON: {raw[:200]!r}",
                code="invalid_output",
            ) from exc
        try:
            return TaskPlan.model_validate(payload)
        except ValidationError as exc:
            raise AgentError(
                message="Planner LLM output did not match TaskPlan schema",
                code="invalid_output",
                details={"errors": exc.errors(), "raw": raw[:500]},
            ) from exc

    def _validate_agent_names(
        self,
        plan: TaskPlan,
        effective_agents: list[str] | None = None,
    ) -> None:
        """Reject plans referencing agents outside the effective list."""
        allowed = set(effective_agents or self.available_agents)
        for i, step in enumerate(plan.steps):
            if step.agent_name not in allowed:
                raise AgentError(
                    message=(
                        f"Planner picked unknown agent {step.agent_name!r} "
                        f"at step {i}"
                    ),
                    code="invalid_output",
                    details={
                        "step_index": i,
                        "picked": step.agent_name,
                        "available": sorted(allowed),
                    },
                )
