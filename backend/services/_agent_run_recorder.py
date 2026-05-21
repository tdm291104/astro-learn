"""Encapsulates the AgentModel row state machine for agent runs."""

# Uses a session FACTORY (not request session) so each transition commits
# independently — lets GET /agents/{id}/status see updates mid-stream.
# _terminate respects existing terminal state (out-of-band cancellation).

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.agent_repository import AgentRepository

_TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


@dataclass
class RunHandle:
    """Returned from AgentRunRecorder.run; lets caller record the outcome."""

    run_id: uuid.UUID
    _output: dict[str, Any] | None = field(default=None, repr=False)
    _error: str | None = field(default=None, repr=False)

    def set_output(self, output: dict[str, Any]) -> None:
        """Record success; recorder marks the row 'succeeded' on context exit."""
        self._output = output

    def set_error(self, error: str) -> None:
        """Record a domain error without raising; recorder marks 'failed' on exit."""
        self._error = error


class AgentRunRecorder:
    """Owns the AgentModel state machine for a single agent run."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def run(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        agent_name: str,
        task: dict[str, Any],
    ) -> AsyncIterator[RunHandle]:
        """Async context manager wrapping one agent execution."""
        run_id = await self._create_pending(
            user_id=user_id,
            session_id=session_id,
            agent_name=agent_name,
            task=task,
        )
        await self._mark_running(run_id)

        handle = RunHandle(run_id=run_id)
        try:
            yield handle
        except asyncio.CancelledError:
            # Mark cancelled then propagate so asyncio machinery works.
            await self._terminate(run_id, "cancelled")
            raise
        except Exception as exc:
            await self._terminate(run_id, "failed", error=str(exc))
            raise
        else:
            status, output, error = self._resolve_terminal(handle)
            await self._terminate(run_id, status, output=output, error=error)

    @staticmethod
    def _resolve_terminal(
        handle: RunHandle,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        """Map the no-exception case to a terminal status."""
        if handle._output is not None:
            return ("succeeded", handle._output, None)
        if handle._error is not None:
            return ("failed", None, handle._error)
        # Surface as failed so missing-outcome bug is loud.
        return ("failed", None, "agent run completed without recording output")

    async def _create_pending(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        agent_name: str,
        task: dict[str, Any],
    ) -> uuid.UUID:
        """Insert the row in pending state and return its id."""
        async with self._session_factory() as session:
            repo = AgentRepository(session)
            row = await repo.create(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "agent_name": agent_name,
                    "status": "pending",
                    "task_input": task,
                }
            )
            await session.commit()
            return row.id

    async def _mark_running(self, run_id: uuid.UUID) -> None:
        """Flip pending to running with started_at=now."""
        async with self._session_factory() as session:
            repo = AgentRepository(session)
            row = await repo.get(run_id)
            if row is None:
                return
            row.status = "running"
            row.started_at = datetime.now(UTC)
            await session.commit()

    async def _terminate(
        self,
        run_id: uuid.UUID,
        status: str,
        *,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Write terminal status, no-op if row is already terminal."""
        async with self._session_factory() as session:
            repo = AgentRepository(session)
            current = await repo.get(run_id)
            if current is None:
                return
            if current.status in _TERMINAL_STATUSES:
                return
            await repo.set_status(
                run_id,
                status,
                output=output,
                error=error,
                finished_at=datetime.now(UTC),
            )
            await session.commit()
