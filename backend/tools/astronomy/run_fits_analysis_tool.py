"""Agent-callable FITS analysis wrapper; 120s hard cap with timeout error."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any, ClassVar

from celery.exceptions import TimeoutError as CeleryTimeoutError  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from core.exceptions import ToolError
from schemas.astronomy_schema import (
    AnalysisType,
    AnalyzeRequest,
    AnalyzeResponse,
)
from tools.base_tool import BaseTool

if TYPE_CHECKING:
    # TYPE_CHECKING import breaks cycle via agents → tools → services → agents.
    from services.astronomy_service import AstronomyService

# Hard cap; see docs/api-contracts.md.
DEFAULT_ANALYSIS_TIMEOUT_SECONDS: int = 120


class RunFitsAnalysisInput(BaseModel):
    """`owner_id` injected via constructor, not exposed to LLM."""

    file_id: uuid.UUID = Field(..., description="Uploaded FITS file id.")
    analysis_type: AnalysisType = Field(
        ...,
        description=(
            "One of: image_stats (cheap, inline), photometry, spectroscopy, "
            "wcs_solve, custom (heavy, queued)."
        ),
    )
    hdu_index: int = Field(0, ge=0, description="HDU to analyse (default 0).")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Analysis-specific parameters (threshold_sigma, fwhm, etc.).",
    )


class RunFitsAnalysisTool(BaseTool):
    """Run one FITS analysis end-to-end. Owner-scoped via constructor."""

    name: ClassVar[str] = "run_fits_analysis"
    description: ClassVar[str] = (
        "Run a stored astronomy analysis (image_stats, photometry, spectroscopy, "
        "wcs_solve, custom) on a previously uploaded FITS file. Blocks for up to "
        "120 s while the heavy pipeline runs; on timeout the call is surfaced to "
        "the user without blocking the chat indefinitely."
    )
    input_schema: ClassVar[type[BaseModel] | None] = RunFitsAnalysisInput

    def __init__(
        self,
        *,
        service: AstronomyService,
        owner_id: uuid.UUID,
        timeout_seconds: int = DEFAULT_ANALYSIS_TIMEOUT_SECONDS,
    ) -> None:
        self.service = service
        self.owner_id = owner_id
        self.timeout_seconds = timeout_seconds

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Dispatch, await Celery, return persisted response."""
        request = AnalyzeRequest(
            file_id=kwargs["file_id"],
            hdu_index=kwargs.get("hdu_index", 0),
            analysis_type=kwargs["analysis_type"],
            params=kwargs.get("params", {}),
        )

        response, async_result = await self.service.analyze_with_result(
            self.owner_id, request
        )

        # Inline path (image_stats): row already populated.
        if async_result is None:
            return _as_payload(response)

        try:
            # Wait for completion; we'll re-fetch row since Celery return is bookkeeping.
            await asyncio.to_thread(
                async_result.get, timeout=self.timeout_seconds, propagate=True
            )
        except CeleryTimeoutError as exc:
            raise ToolError(
                message=(
                    f"FITS analysis is taking longer than expected "
                    f"(>{self.timeout_seconds}s). The job is still running in "
                    f"the background — try again in a moment, or check the "
                    f"analysis history panel for the result."
                ),
                code="fits_analysis_timeout",
                details={"analysis_id": str(response.analysis_id)},
            ) from exc

        refreshed = await self.service.get_analysis(
            response.analysis_id, self.owner_id
        )
        return _as_payload(refreshed)


def _as_payload(response: AnalyzeResponse) -> dict[str, Any]:
    return response.model_dump(mode="json")
