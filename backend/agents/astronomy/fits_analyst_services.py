"""Request-scoped service bundle for FitsAnalystAgent (DB + Celery plumbing)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.exceptions import AgentError, AuthorizationError, NotFoundError
from repositories.analysis_repository import AnalysisRepository
from repositories.fits_file_repository import FitsFileRepository
from repositories.report_repository import ReportRepository
from services._agent_run_recorder import AgentRunRecorder
from tools.astronomy.run_fits_analysis_tool import DEFAULT_ANALYSIS_TIMEOUT_SECONDS

# astronomy_service imported lazily in run_analysis to break import cycle.

if TYPE_CHECKING:
    from core.agent_factory import DefaultAgentFactory


class FitsAnalystServicesProtocol(Protocol):
    """Surface needed by the agent; tests inject a stub."""

    async def load_file_summary(
        self, owner_id: uuid.UUID, file_id: uuid.UUID
    ) -> tuple[str, dict[str, Any]]:
        ...

    async def run_analysis(
        self,
        owner_id: uuid.UUID,
        *,
        file_id: uuid.UUID,
        hdu_index: int,
        analysis_type: str,
        params: dict[str, Any],
        timeout_seconds: int = DEFAULT_ANALYSIS_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        ...

    async def persist_interpretation(
        self,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        interpretation: dict[str, Any],
    ) -> None:
        ...


class DefaultFitsAnalystServices:
    """Production implementation backed by SQLAlchemy + AstronomyService."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage_root: Path,
        recorder: AgentRunRecorder,
        agent_factory: DefaultAgentFactory,
    ) -> None:
        self._session_factory = session_factory
        self._storage_root = storage_root
        self._recorder = recorder
        self._agent_factory = agent_factory

    async def load_file_summary(
        self, owner_id: uuid.UUID, file_id: uuid.UUID
    ) -> tuple[str, dict[str, Any]]:
        async with self._session_factory() as session:
            row = await FitsFileRepository(session).get(file_id)
            if row is None:
                raise AgentError(
                    message=f"FITS file {file_id} not found",
                    code="fits_not_found",
                )
            if row.owner_id != owner_id:
                # Don't leak existence; same code as missing.
                raise AgentError(
                    message=f"FITS file {file_id} not found",
                    code="fits_not_found",
                )
            return row.filename, dict(row.header_summary or {})

    async def run_analysis(
        self,
        owner_id: uuid.UUID,
        *,
        file_id: uuid.UUID,
        hdu_index: int,
        analysis_type: str,
        params: dict[str, Any],
        timeout_seconds: int = DEFAULT_ANALYSIS_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        # Three-phase: dispatch+commit, await Celery off-session, refetch.
        # Single long-lived session would hide the uncommitted row from worker.
        from celery.exceptions import (  # type: ignore[import-untyped]  # noqa: PLC0415
            TimeoutError as CeleryTimeoutError,
        )

        from schemas.astronomy_schema import AnalyzeRequest  # noqa: PLC0415 — lazy
        from services.astronomy_service import (
            AstronomyService,  # noqa: PLC0415 — lazy to break import cycle
        )

        request = AnalyzeRequest(
            file_id=file_id,
            hdu_index=hdu_index,
            analysis_type=analysis_type,
            params=params,
        )

        try:
            async with self._session_factory() as dispatch_session:
                dispatch_service = AstronomyService(
                    fits_files=FitsFileRepository(dispatch_session),
                    analyses=AnalysisRepository(dispatch_session),
                    reports=ReportRepository(dispatch_session),
                    factory=self._agent_factory,
                    recorder=self._recorder,
                    storage_root=self._storage_root,
                )
                response, async_result = (
                    await dispatch_service.analyze_with_result(owner_id, request)
                )
                # Commit so Celery worker can SELECT the row.
                await dispatch_session.commit()
        except (NotFoundError, AuthorizationError) as exc:
            raise AgentError(
                message=exc.message,
                code=exc.code or "fits_not_found",
            ) from exc

        # image_stats runs inline → response already terminal.
        if async_result is not None:
            try:
                await asyncio.to_thread(
                    async_result.get, timeout=timeout_seconds, propagate=True
                )
            except CeleryTimeoutError as exc:
                from core.exceptions import ToolError  # noqa: PLC0415

                raise ToolError(
                    message=(
                        f"FITS analysis is taking longer than expected "
                        f"(>{timeout_seconds}s). The job is still running "
                        f"in the background — try again in a moment, or "
                        f"check the analysis history panel for the result."
                    ),
                    code="fits_analysis_timeout",
                    details={"analysis_id": str(response.analysis_id)},
                ) from exc

            async with self._session_factory() as fetch_session:
                fetch_service = AstronomyService(
                    fits_files=FitsFileRepository(fetch_session),
                    analyses=AnalysisRepository(fetch_session),
                    reports=ReportRepository(fetch_session),
                    factory=self._agent_factory,
                    recorder=self._recorder,
                    storage_root=self._storage_root,
                )
                response = await fetch_service.get_analysis(
                    response.analysis_id, owner_id
                )

        return response.model_dump(mode="json")

    async def persist_interpretation(
        self,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        interpretation: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session:
            repo = AnalysisRepository(session)
            row = await repo.get(analysis_id)
            # Defence in depth: enforce owner scope on persist too.
            if row is None or row.owner_id != owner_id:
                return
            await repo.set_interpretation(analysis_id, interpretation)
            await session.commit()
