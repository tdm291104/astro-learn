"""Schemas for /agents/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror AgentModel.status — keep in sync.
AgentRunStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]


class AgentRunRequest(BaseModel):
    """Body for POST /agents/run."""

    agent_name: str = Field(..., min_length=1, max_length=64)
    task_input: dict[str, Any]
    session_id: uuid.UUID | None = None
    stream: bool = False


class AgentResponse(BaseModel):
    """Snapshot of one agent run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID | None
    agent_name: str
    status: AgentRunStatus
    task_input: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    # NULL progress for open-ended runs; UI falls back to step_count/current_step.
    step_count: int = 0
    current_step: str | None = None
    progress: float | None = Field(None, ge=0.0, le=1.0)
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AgentInfoResponse(BaseModel):
    """Static description of a registered agent."""

    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None


class AgentStatusResponse(BaseModel):
    """Lightweight status payload for polling a run."""

    id: uuid.UUID
    status: AgentRunStatus
    progress: float | None = Field(None, ge=0.0, le=1.0)
    current_step: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
