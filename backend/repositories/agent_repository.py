"""DB access for AgentModel (agent run records)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from models.agent_model import AgentModel
from repositories.base_repository import BaseRepository

# Non-terminal statuses.
ACTIVE_STATUSES: tuple[str, ...] = ("pending", "running")


class AgentRepository(BaseRepository[AgentModel]):
    """Agent-run table operations."""

    model = AgentModel

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        agent_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AgentModel]:
        """Return runs for user_id, newest first; optional agent_name filter."""
        stmt = select(AgentModel).where(AgentModel.user_id == user_id)
        if agent_name is not None:
            stmt = stmt.where(AgentModel.agent_name == agent_name)
        stmt = (
            stmt.order_by(AgentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active(self) -> Sequence[AgentModel]:
        """Return pending/running runs, newest first."""
        stmt = (
            select(AgentModel)
            .where(AgentModel.status.in_(ACTIVE_STATUSES))
            .order_by(AgentModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def set_status(
        self,
        run_id: uuid.UUID,
        status: str,
        *,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        finished_at: datetime | None = None,
    ) -> AgentModel | None:
        """Mutate the status (and optional result fields) of a single run."""
        instance = await self.session.get(AgentModel, run_id)
        if instance is None:
            return None

        instance.status = status
        if output is not None:
            instance.output = output
        if error is not None:
            instance.error = error
        if finished_at is not None:
            instance.finished_at = finished_at

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update_progress(
        self,
        run_id: uuid.UUID,
        *,
        step_count: int,
        current_step: str | None = None,
        progress: float | None = None,
    ) -> AgentModel | None:
        """Mirror in-flight AgentState progress fields; status untouched here."""
        instance = await self.session.get(AgentModel, run_id)
        if instance is None:
            return None

        instance.step_count = step_count
        # None preserves previous label so UI doesn't flicker.
        if current_step is not None:
            instance.current_step = current_step
        if progress is not None:
            instance.progress = progress

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def search(
        self,
        *,
        status: str | None = None,
        agent_name: str | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AgentModel]:
        """Admin-wide paginated run list, newest first."""
        stmt = select(AgentModel)
        if status is not None:
            stmt = stmt.where(AgentModel.status == status)
        if agent_name is not None:
            stmt = stmt.where(AgentModel.agent_name == agent_name)
        if user_id is not None:
            stmt = stmt.where(AgentModel.user_id == user_id)
        stmt = stmt.order_by(AgentModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_search(
        self,
        *,
        status: str | None = None,
        agent_name: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> int:
        """Total rows matching the same filters as search()."""
        stmt = select(func.count()).select_from(AgentModel)
        if status is not None:
            stmt = stmt.where(AgentModel.status == status)
        if agent_name is not None:
            stmt = stmt.where(AgentModel.agent_name == agent_name)
        if user_id is not None:
            stmt = stmt.where(AgentModel.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def status_counts(self) -> dict[str, int]:
        """Return current count per status for monitor headline cards."""
        stmt = select(AgentModel.status, func.count()).group_by(AgentModel.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(row[0]): int(row[1]) for row in rows}
