"""Runtime state for one agent run, persisted to Redis between steps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.base.agent_message import AgentMessage

# Mirrors `schemas.agent_schema.AgentRunStatus`.
AgentRunStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    agent_name: str
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None

    messages: list[AgentMessage] = Field(default_factory=list)

    # Per-agent scratch; framework never reads this.
    scratchpad: dict[str, Any] = Field(default_factory=dict)

    status: AgentRunStatus = "pending"
    step_count: int = 0
    current_step: str | None = None

    final_output: dict[str, Any] | None = None
    error: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def append(self, message: AgentMessage) -> None:
        """Append message; bump updated_at and step_count."""
        self.messages.append(message)
        self.step_count += 1
        self.updated_at = datetime.now(UTC)

    def last_message(self) -> AgentMessage | None:
        return self.messages[-1] if self.messages else None

    def to_redis(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_redis(cls, payload: str) -> AgentState:
        return cls.model_validate_json(payload)
