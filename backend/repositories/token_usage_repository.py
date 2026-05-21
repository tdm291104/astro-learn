"""DB access for TokenUsageEventModel."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from models.token_usage_event_model import TokenUsageEventModel
from repositories.base_repository import BaseRepository


@dataclass(slots=True, frozen=True)
class DailyUsage:
    """One day's aggregated token usage."""

    day: date
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True, frozen=True)
class UsageTotals:
    """Sum of all events in a window."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True, frozen=True)
class UserUsageRow:
    """One user's aggregated usage (admin top-users list)."""

    user_id: uuid.UUID
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True, frozen=True)
class ModelUsageRow:
    """One model's aggregated usage system-wide."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    call_count: int


class TokenUsageRepository(BaseRepository[TokenUsageEventModel]):
    """LLM-call token usage table operations."""

    model = TokenUsageEventModel

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> TokenUsageEventModel:
        """Insert one usage event."""
        return await self.create(
            {
                "user_id": user_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        )

    async def totals_since(
        self,
        user_id: uuid.UUID,
        since: datetime,
    ) -> UsageTotals:
        """Sum events since `since` (UTC) for this user."""
        stmt = select(
            func.coalesce(func.sum(TokenUsageEventModel.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsageEventModel.completion_tokens), 0),
            func.coalesce(func.sum(TokenUsageEventModel.total_tokens), 0),
        ).where(
            TokenUsageEventModel.user_id == user_id,
            TokenUsageEventModel.created_at >= since,
        )
        row = (await self.session.execute(stmt)).one()
        return UsageTotals(
            prompt_tokens=int(row[0]),
            completion_tokens=int(row[1]),
            total_tokens=int(row[2]),
        )

    async def daily_breakdown(
        self,
        user_id: uuid.UUID,
        since: datetime,
    ) -> Sequence[DailyUsage]:
        """Sum events grouped by UTC day, oldest first; zero-days omitted."""
        day_col = func.date_trunc(
            "day", TokenUsageEventModel.created_at
        ).label("day")
        stmt = (
            select(
                day_col,
                func.sum(TokenUsageEventModel.prompt_tokens),
                func.sum(TokenUsageEventModel.completion_tokens),
                func.sum(TokenUsageEventModel.total_tokens),
            )
            .where(
                TokenUsageEventModel.user_id == user_id,
                TokenUsageEventModel.created_at >= since,
            )
            .group_by(day_col)
            .order_by(day_col.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        out: list[DailyUsage] = []
        for r in rows:
            # date_trunc returns timestamp; normalize to date.
            ts = r[0]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                day = ts.date()
            else:
                day = ts
            out.append(
                DailyUsage(
                    day=day,
                    prompt_tokens=int(r[1] or 0),
                    completion_tokens=int(r[2] or 0),
                    total_tokens=int(r[3] or 0),
                )
            )
        return out

    async def totals_all_since(self, since: datetime) -> UsageTotals:
        """System-wide token totals since `since` (UTC)."""
        stmt = select(
            func.coalesce(func.sum(TokenUsageEventModel.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsageEventModel.completion_tokens), 0),
            func.coalesce(func.sum(TokenUsageEventModel.total_tokens), 0),
        ).where(TokenUsageEventModel.created_at >= since)
        row = (await self.session.execute(stmt)).one()
        return UsageTotals(
            prompt_tokens=int(row[0]),
            completion_tokens=int(row[1]),
            total_tokens=int(row[2]),
        )

    async def daily_breakdown_all(self, since: datetime) -> Sequence[DailyUsage]:
        """System-wide per-day token usage since `since` (UTC)."""
        day_col = func.date_trunc(
            "day", TokenUsageEventModel.created_at
        ).label("day")
        stmt = (
            select(
                day_col,
                func.sum(TokenUsageEventModel.prompt_tokens),
                func.sum(TokenUsageEventModel.completion_tokens),
                func.sum(TokenUsageEventModel.total_tokens),
            )
            .where(TokenUsageEventModel.created_at >= since)
            .group_by(day_col)
            .order_by(day_col.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        out: list[DailyUsage] = []
        for r in rows:
            ts = r[0]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                day = ts.date()
            else:
                day = ts
            out.append(
                DailyUsage(
                    day=day,
                    prompt_tokens=int(r[1] or 0),
                    completion_tokens=int(r[2] or 0),
                    total_tokens=int(r[3] or 0),
                )
            )
        return out

    async def top_users(
        self,
        since: datetime,
        *,
        limit: int = 10,
    ) -> Sequence[UserUsageRow]:
        """Heaviest `limit` token consumers since `since`."""
        stmt = (
            select(
                TokenUsageEventModel.user_id,
                func.coalesce(func.sum(TokenUsageEventModel.prompt_tokens), 0),
                func.coalesce(func.sum(TokenUsageEventModel.completion_tokens), 0),
                func.coalesce(func.sum(TokenUsageEventModel.total_tokens), 0),
            )
            .where(TokenUsageEventModel.created_at >= since)
            .group_by(TokenUsageEventModel.user_id)
            .order_by(func.sum(TokenUsageEventModel.total_tokens).desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            UserUsageRow(
                user_id=r[0],
                prompt_tokens=int(r[1] or 0),
                completion_tokens=int(r[2] or 0),
                total_tokens=int(r[3] or 0),
            )
            for r in rows
        ]

    async def count_active_users_since(self, since: datetime) -> int:
        """Distinct users with at least one event since `since`."""
        stmt = select(
            func.count(func.distinct(TokenUsageEventModel.user_id))
        ).where(TokenUsageEventModel.created_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def breakdown_by_model(
        self,
        since: datetime,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[ModelUsageRow]:
        """Sum events by model; user_id=None for system-wide admin view."""
        stmt = (
            select(
                TokenUsageEventModel.model,
                func.coalesce(func.sum(TokenUsageEventModel.prompt_tokens), 0),
                func.coalesce(func.sum(TokenUsageEventModel.completion_tokens), 0),
                func.coalesce(func.sum(TokenUsageEventModel.total_tokens), 0),
                func.count(),
            )
            .where(TokenUsageEventModel.created_at >= since)
            .group_by(TokenUsageEventModel.model)
            .order_by(func.sum(TokenUsageEventModel.total_tokens).desc())
        )
        if user_id is not None:
            stmt = stmt.where(TokenUsageEventModel.user_id == user_id)
        rows = (await self.session.execute(stmt)).all()
        return [
            ModelUsageRow(
                model=str(r[0]),
                prompt_tokens=int(r[1] or 0),
                completion_tokens=int(r[2] or 0),
                total_tokens=int(r[3] or 0),
                call_count=int(r[4] or 0),
            )
            for r in rows
        ]
