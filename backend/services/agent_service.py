"""Agent lifecycle management exposed to /agents/* routes."""

# Always goes through DefaultAgentFactory (CLAUDE.md rule); runs mirrored
# into AgentModel via AgentRunRecorder. Session is ensured first so a bad
# session_id never creates an orphan agent row.

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from core.agent_factory import DefaultAgentFactory
from core.exceptions import AuthorizationError
from repositories.agent_repository import AgentRepository
from repositories.session_repository import SessionRepository
from schemas.agent_schema import (
    AgentInfoResponse,
    AgentResponse,
    AgentRunRequest,
    AgentStatusResponse,
)
from services._agent_run_recorder import AgentRunRecorder

# Local copy to avoid circular dep on repo enum.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


class AgentService:
    """Run, stream, list, and inspect agent executions."""

    def __init__(
        self,
        agent_runs: AgentRepository,
        sessions: SessionRepository,
        factory: DefaultAgentFactory,
        recorder: AgentRunRecorder,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.agent_runs = agent_runs
        self.sessions = sessions
        self.factory = factory
        self.recorder = recorder
        # Lazy-create commits via independent tx so recorder FK sees the row.
        self._session_factory = session_factory

    async def run_agent(
        self,
        user_id: uuid.UUID,
        request: AgentRunRequest,
    ) -> AgentResponse:
        """Execute an agent to completion and return the persisted run record."""
        # Unknown session_id is lazy-created (see _ensure_session).
        await self._ensure_session(request.session_id, user_id)
        agent = self.factory(request.agent_name)

        async with self.recorder.run(
            user_id=user_id,
            session_id=request.session_id,
            agent_name=request.agent_name,
            task=request.task_input,
        ) as handle:
            state = AgentState(
                run_id=handle.run_id,
                agent_name=request.agent_name,
                user_id=user_id,
                session_id=request.session_id,
            )
            terminal_state = await agent.run(request.task_input, state=state)
            handle.set_output(terminal_state.final_output or {})

        # Re-fetch so response reflects what recorder's own session committed.
        row = await self.agent_runs.get(handle.run_id)
        assert row is not None
        return AgentResponse.model_validate(row)

    async def stream_agent(
        self,
        user_id: uuid.UUID,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentMessage]:
        """Yield incremental AgentMessage chunks as the agent works."""
        # Client disconnect → CancelledError → recorder marks 'cancelled'.
        await self._ensure_session(request.session_id, user_id)
        agent = self.factory(request.agent_name)

        async with self.recorder.run(
            user_id=user_id,
            session_id=request.session_id,
            agent_name=request.agent_name,
            task=request.task_input,
        ) as handle:
            # First frame carries run_id so SSE clients can stash for reconnect.
            yield AgentMessage(
                role="system",
                content="",
                extra={"run_id": str(handle.run_id)},
            )
            state = AgentState(
                run_id=handle.run_id,
                agent_name=request.agent_name,
                user_id=user_id,
                session_id=request.session_id,
            )
            async for message in agent.stream(request.task_input, state=state):
                yield message
            handle.set_output(state.final_output or {})

    async def get_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AgentResponse | None:
        """Owner-scoped run fetch; returns None for missing or non-owned rows."""
        # Single None avoids leaking existence of other users' runs.
        row = await self.agent_runs.get(run_id)
        if row is None or row.user_id != user_id:
            return None
        return AgentResponse.model_validate(row)

    async def list_runs(
        self,
        user_id: uuid.UUID,
        *,
        agent_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentResponse]:
        """Owner-scoped run history, optionally filtered by agent name."""
        rows = await self.agent_runs.list_for_user(
            user_id, agent_name=agent_name, limit=limit, offset=offset
        )
        return [AgentResponse.model_validate(r) for r in rows]

    async def get_status(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AgentStatusResponse | None:
        """Lightweight status for polling without re-fetching the full row."""
        row = await self.agent_runs.get(run_id)
        if row is None or row.user_id != user_id:
            return None
        # NULL progress expected for open-ended paths; UI falls back to step_count.
        return AgentStatusResponse(
            id=row.id,
            status=row.status,
            progress=row.progress,
            current_step=row.current_step,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )

    async def list_available_agents(self) -> list[AgentInfoResponse]:
        """List every registered agent class (in-memory)."""
        return [
            AgentInfoResponse(
                name=cls.name,
                description=cls.description,
                capabilities=list(cls.capabilities),
                input_schema=getattr(cls, "input_schema", None),
            )
            for cls in AgentRegistry.list_agents()
        ]

    async def cancel_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Mark a non-terminal run as cancelled (idempotent)."""
        # Cooperative: agent loop can't observe flag mid-run, but recorder
        # respects existing 'cancelled' so final state stays correct.
        row = await self.agent_runs.get(run_id)
        if row is None or row.user_id != user_id:
            return False
        if row.status in _TERMINAL_STATUSES:
            return False
        await self.agent_runs.set_status(
            run_id,
            "cancelled",
            finished_at=datetime.now(UTC),
        )
        return True

    async def _ensure_session(
        self,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> None:
        """Ensure session_id exists and is owned by user_id; lazy-create if missing."""
        # Lazy-create lets FE mint UUID client-side without POST /sessions round-trip.
        if session_id is None:
            return
        row = await self.sessions.get(session_id)
        if row is not None:
            if row.user_id != user_id:
                raise AuthorizationError(
                    message="Session belongs to another user",
                    code="forbidden",
                )
            return

        # Independent tx so recorder's separate session sees the row for FK.
        async with self._session_factory() as s:
            await SessionRepository(s).create(
                {
                    "id": session_id,
                    "user_id": user_id,
                    "notebook_id": None,
                    "title": None,
                }
            )
            await s.commit()
