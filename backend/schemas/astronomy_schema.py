"""Schemas for /astronomy/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FitsHduSummary(BaseModel):
    """One Header/Data Unit inside a FITS file."""

    index: int
    name: str | None
    type: str
    shape: list[int] | None
    n_keywords: int


class FitsUploadResponse(BaseModel):
    """Response from POST /astronomy/upload-fits."""

    file_id: uuid.UUID
    filename: str
    size_bytes: int
    hdu_count: int
    hdus: list[FitsHduSummary]
    primary_headers: dict[str, Any] = Field(default_factory=dict)
    # Structured projection driving the agent's analysis-type decision.
    header_summary: dict[str, Any] | None = None


AnalysisType = Literal[
    "image_stats",
    "photometry",
    "spectroscopy",
    "wcs_solve",
    "custom",
]

AnalysisStatus = Literal["pending", "running", "succeeded", "failed"]


class AnalyzeRequest(BaseModel):
    """Body for POST /astronomy/analyze."""

    file_id: uuid.UUID
    hdu_index: int = 0
    analysis_type: AnalysisType
    params: dict[str, Any] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    """Result of an analysis run."""

    model_config = ConfigDict(from_attributes=True)

    analysis_id: uuid.UUID
    file_id: uuid.UUID
    analysis_type: AnalysisType
    status: AnalysisStatus = "succeeded"
    results: dict[str, Any]
    # Filenames relative to STORAGE_ROOT/fits_artifacts/{file_id}/.
    artifacts: list[str] = Field(default_factory=list)
    # FitsAnalystAgent FitsInterpretation; null for non-chat or legacy runs.
    interpretation: dict[str, Any] | None = None
    generated_at: datetime


CatalogSource = Literal["simbad", "ned", "vizier"]


class CatalogSearchRequest(BaseModel):
    """Query params for GET /astronomy/catalog/search."""

    query: str = Field(..., min_length=1, description="Object name or RA,Dec")
    source: CatalogSource = "simbad"
    radius_arcsec: float | None = Field(None, ge=0.0, le=3600.0)
    limit: int = Field(20, ge=1, le=200)


class CatalogObject(BaseModel):
    """A single catalog row, normalized across providers."""

    name: str
    ra_deg: float | None
    dec_deg: float | None
    object_type: str | None
    references: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class CatalogSearchResponse(BaseModel):
    """Catalog search results envelope."""

    query: str
    source: CatalogSource
    results: list[CatalogObject]
    # One-paragraph LLM context above the table; null on empty hits / LLM failure.
    commentary: str | None = None


ReportFormat = Literal["pdf", "markdown", "html"]


class ReportRequest(BaseModel):
    """Body for POST /astronomy/report."""

    analysis_id: uuid.UUID
    title: str | None = None
    format: ReportFormat = "markdown"
    include_plots: bool = True


class ReportResponse(BaseModel):
    """Generated report descriptor."""

    report_id: uuid.UUID
    title: str
    format: ReportFormat
    url: str
    generated_at: datetime


class SampleFitsItem(BaseModel):
    """One curated FITS file offered on the anomaly-audit landing page."""

    file_id: uuid.UUID
    display_name: str
    description: str
    instrument: str
    size_mb: float
    expected_anomalies: int
    seeded: bool


class SampleFitsListResponse(BaseModel):
    """Response from GET /astronomy/sample-fits."""

    items: list[SampleFitsItem]
