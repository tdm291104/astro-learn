"""Workflow foundation: state, factory protocol, BaseWorkflow ABC."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field

from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent

# Separate from AgentRunStatus to allow workflow-only states (e.g. partial-success).
WorkflowStatus = str  # pending | running | succeeded | failed | cancelled


class AgentFactory(Protocol):
    def __call__(self, agent_name: str) -> BaseAgent: ...


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workflow_name: str
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None

    status: WorkflowStatus = "pending"
    current_step: str | None = None
    step_results: dict[str, AgentState] = Field(default_factory=dict)

    final_output: dict[str, Any] | None = None
    error: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_output(self, step_name: str) -> dict[str, Any] | None:
        result = self.step_results.get(step_name)
        return result.final_output if result is not None else None

    def to_redis(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_redis(cls, payload: str) -> WorkflowState:
        return cls.model_validate_json(payload)


# (step_name, step_index_0_based, total_steps).
StepProgressCallback = Callable[[str, int, int], Awaitable[None]]


class BaseWorkflow(ABC):
    """Abstract pipeline composing multiple agents."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init__(
        self,
        agent_factory: AgentFactory,
        *,
        on_step_complete: StepProgressCallback | None = None,
    ) -> None:
        self.agent_factory = agent_factory
        # Workers wire this to mirror progress onto agent_runs.
        self.on_step_complete = on_step_complete

    @abstractmethod
    async def run(
        self,
        input: dict[str, Any],
        *,
        state: WorkflowState | None = None,
    ) -> WorkflowState:
        ...
