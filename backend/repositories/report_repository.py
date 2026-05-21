"""DB access for ReportModel (generated analysis reports)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from models.report_model import ReportModel
from repositories.base_repository import BaseRepository


class ReportRepository(BaseRepository[ReportModel]):
    """Report table operations."""

    model = ReportModel

    async def list_for_analysis(
        self,
        analysis_id: uuid.UUID,
    ) -> Sequence[ReportModel]:
        """Return reports built from `analysis_id`, newest first."""
        stmt = (
            select(ReportModel)
            .where(ReportModel.analysis_id == analysis_id)
            .order_by(ReportModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
