"""Structured FITS interpretation; contract in docs/api-contracts.md §1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InterpResultType = Literal[
    "image_stats",
    "photometry",
    "spectroscopy",
    "wcs",
    "custom",
]


class InterpMetric(BaseModel):
    """One human-readable measurement extracted from raw analysis output."""

    label: str = Field(..., min_length=1, description="Human-readable name, e.g. 'Sky background'.")
    value: str = Field(..., min_length=1, description="Formatted value with units.")
    interpretation: str = Field(..., min_length=1, description="One sentence on astronomical meaning.")


class InterpResult(BaseModel):
    """Interpretation of one analysis step (one entry per chosen analysis_type)."""

    type: InterpResultType
    headline: str = Field(..., min_length=1)
    metrics: list[InterpMetric] = Field(default_factory=list)
    interpretation: str = Field(..., min_length=1)
    anomalies: list[str] = Field(default_factory=list)


class InterpContext(BaseModel):
    """File-level context surfaced to the user (never the UUID file_id)."""

    filename: str = Field(..., min_length=1)
    image_type: str = Field(..., min_length=1)
    dimensions: str = Field(..., min_length=1)
    instrument: str | None = None
    filter: str | None = None


class InterpDecision(BaseModel):
    """Which analyses the agent chose to run and why."""

    analysis_types: list[str] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=1)


class ReflexionMeta(BaseModel):
    """Symbolic-critic metadata; deterministic, 0-token, <50ms per file."""

    symbolic_violations: int = 0
    # Capped at 1 round; interpretation step is structured enough.
    reflection_rounds: int = 0
    # Severity counts so UI badge avoids re-parsing anomalies lists.
    error_count: int = 0
    warning_count: int = 0
    summary: str = ""


class FitsInterpretation(BaseModel):
    """Final payload returned by FitsAnalystAgent (and persisted to analyses)."""

    context: InterpContext
    decision: InterpDecision
    results: list[InterpResult] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    # Optional so pre-Reflexion legacy interpretations still validate.
    reflexion: ReflexionMeta | None = None
