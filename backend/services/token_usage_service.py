"""Aggregation helpers for the LLM token-usage dashboard."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from core.llm.pricing import estimate_cost_usd
from repositories.token_usage_repository import TokenUsageRepository
from schemas.token_usage_schema import (
    CostBreakdownResponse,
    DailyUsageItem,
    ModelUsageItem,
    TokenUsageSummary,
    UsageTotalsResponse,
)


class TokenUsageService:
    """Read-only aggregations over the token_usage_events table."""

    def __init__(self, repo: TokenUsageRepository) -> None:
        self.repo = repo

    async def summary(
        self,
        user_id: uuid.UUID,
        *,
        days: int = 30,
    ) -> TokenUsageSummary:
        """Monthly totals + zero-filled daily breakdown for the window."""
        now = datetime.now(UTC)
        today = now.date()

        month_start_dt = datetime(now.year, now.month, 1, tzinfo=UTC)
        month_totals = await self.repo.totals_since(user_id, month_start_dt)

        # Bound defensively so a misbehaving client can't request a year of rows.
        window_days = max(1, min(days, 90))
        window_start_date = today - timedelta(days=window_days - 1)
        window_start_dt = datetime(
            window_start_date.year,
            window_start_date.month,
            window_start_date.day,
            tzinfo=UTC,
        )
        rows = await self.repo.daily_breakdown(user_id, window_start_dt)

        # Zero-fill so chart X-axis is evenly spaced.
        by_day: dict[date, DailyUsageItem] = {
            r.day: DailyUsageItem(
                date=r.day,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
            )
            for r in rows
        }
        dense: list[DailyUsageItem] = []
        for i in range(window_days):
            d = window_start_date + timedelta(days=i)
            dense.append(
                by_day.get(
                    d,
                    DailyUsageItem(
                        date=d,
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                    ),
                )
            )

        return TokenUsageSummary(
            month_total=UsageTotalsResponse(
                prompt_tokens=month_totals.prompt_tokens,
                completion_tokens=month_totals.completion_tokens,
                total_tokens=month_totals.total_tokens,
            ),
            month_start=month_start_dt.date(),
            window_days=window_days,
            daily=dense,
        )

    async def cost_breakdown(
        self,
        user_id: uuid.UUID | None,
        *,
        days: int = 30,
    ) -> CostBreakdownResponse:
        """Per-model token + estimated USD cost; user_id=None for admin view."""
        window_days = max(1, min(days, 90))
        now = datetime.now(UTC)
        window_start_dt = now - timedelta(days=window_days)

        rows = await self.repo.breakdown_by_model(window_start_dt, user_id=user_id)
        items: list[ModelUsageItem] = []
        total_cost = 0.0
        total_tokens = 0
        for r in rows:
            cost = estimate_cost_usd(
                r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
            )
            total_cost += cost
            total_tokens += r.total_tokens
            items.append(
                ModelUsageItem(
                    model=r.model,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    total_tokens=r.total_tokens,
                    call_count=r.call_count,
                    cost_usd=round(cost, 4),
                )
            )

        return CostBreakdownResponse(
            window_days=window_days,
            since=window_start_dt,
            total_cost_usd=round(total_cost, 4),
            total_tokens=total_tokens,
            items=items,
        )
