"""Schemas for /users/me/token-usage and /users/me/cost-breakdown."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class UsageTotalsResponse(BaseModel):
    """Aggregate token counts for a window."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class DailyUsageItem(BaseModel):
    """One day's bucket in the rolling-window chart."""

    date: date
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TokenUsageSummary(BaseModel):
    """Dashboard payload combining headline + chart series."""

    # Calendar-month-to-date; resets UTC midnight on the 1st.
    month_total: UsageTotalsResponse
    month_start: date
    # Zero-filled rolling window so renderer doesn't handle gaps.
    window_days: int
    daily: list[DailyUsageItem]


class ModelUsageItem(BaseModel):
    """One row in the per-model usage breakdown."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    call_count: int
    cost_usd: float


class CostBreakdownResponse(BaseModel):
    """Cost breakdown payload (totals + per-model rows)."""

    window_days: int
    since: datetime
    total_cost_usd: float
    total_tokens: int
    items: list[ModelUsageItem]
