"""DB access for AnalysisModel (astronomy analysis runs)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from models.analysis_model import AnalysisModel
from repositories.base_repository import BaseRepository


class AnalysisRepository(BaseRepository[AnalysisModel]):
    """Analysis table operations."""

    model = AnalysisModel

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AnalysisModel]:
        """Return analyses owned by owner_id, newest first."""
        stmt = (
            select(AnalysisModel)
            .where(AnalysisModel.owner_id == owner_id)
            .order_by(AnalysisModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_for_file(
        self,
        file_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AnalysisModel]:
        """Return analyses on `file_id`, newest first."""
        stmt = (
            select(AnalysisModel)
            .where(AnalysisModel.file_id == file_id)
            .order_by(AnalysisModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_running(
        self,
        analysis_id: uuid.UUID,
        started_at: datetime,
    ) -> AnalysisModel | None:
        """Flip 'pending' -> 'running' and stamp `started_at`."""
        instance = await self.session.get(AnalysisModel, analysis_id)
        if instance is None:
            return None

        instance.status = "running"
        instance.started_at = started_at

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def set_terminal(
        self,
        analysis_id: uuid.UUID,
        status: str,
        *,
        results: dict[str, Any] | None = None,
        artifacts: list[str] | None = None,
        error: str | None = None,
        finished_at: datetime,
    ) -> AnalysisModel | None:
        """Write a terminal status (succeeded/failed) plus result fields."""
        instance = await self.session.get(AnalysisModel, analysis_id)
        if instance is None:
            return None

        instance.status = status
        instance.finished_at = finished_at
        if results is not None:
            instance.results = results
        if artifacts is not None:
            instance.artifacts = artifacts
        if error is not None:
            instance.error = error

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def count_distinct_files(self, owner_id: uuid.UUID) -> int:
        """Number of unique FITS files this owner has analysed at least once.

        Dashboard previously displayed `COUNT(*) FROM analyses` for the
        "FITS analyzed" card, which double-counted files that received
        multiple analysis runs (also amplified by dup uploads pre-dedup).
        """
        stmt = (
            select(func.count(func.distinct(AnalysisModel.file_id)))
            .where(AnalysisModel.owner_id == owner_id)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_succeeded_for_file(
        self,
        file_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> Sequence[AnalysisModel]:
        """Newest-first succeeded analyses, used by the 'discuss prior' intent."""
        stmt = (
            select(AnalysisModel)
            .where(AnalysisModel.file_id == file_id)
            .where(AnalysisModel.status == "succeeded")
            .order_by(AnalysisModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def set_interpretation(
        self,
        analysis_id: uuid.UUID,
        interpretation: dict[str, Any] | None,
    ) -> AnalysisModel | None:
        """Persist a FitsInterpretation payload onto an existing analysis row."""
        instance = await self.session.get(AnalysisModel, analysis_id)
        if instance is None:
            return None
        instance.interpretation = interpretation
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
