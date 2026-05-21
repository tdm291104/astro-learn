"""Dashboard stat aggregation — counts for the overview cards."""

from __future__ import annotations

import asyncio
import uuid

from repositories.analysis_repository import AnalysisRepository
from repositories.document_repository import DocumentRepository
from repositories.fits_file_repository import FitsFileRepository
from repositories.notebook_repository import NotebookRepository
from schemas.stats_schema import UserStatsResponse


class UserStatsService:
    """Single-call COUNT(*) rollups for dashboard overview (replaces fan-out)."""

    def __init__(
        self,
        *,
        notebooks: NotebookRepository,
        documents: DocumentRepository,
        fits_files: FitsFileRepository,
        analyses: AnalysisRepository,
    ) -> None:
        self.notebooks = notebooks
        self.documents = documents
        self.fits_files = fits_files
        self.analyses = analyses

    async def summary(self, user_id: uuid.UUID) -> UserStatsResponse:
        """Return all four dashboard counts."""
        notebooks, documents, fits, analyses = await asyncio.gather(
            self.notebooks.count(owner_id=user_id),
            self.documents.count(owner_id=user_id),
            self.fits_files.count(owner_id=user_id),
            self.analyses.count(owner_id=user_id),
        )
        return UserStatsResponse(
            notebooks_count=notebooks,
            documents_count=documents,
            fits_files_count=fits,
            analyses_count=analyses,
        )
