"""DB access for UserModel."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select

from models.user_model import UserModel
from repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[UserModel]):
    """User table operations."""

    model = UserModel

    async def get_by_email(self, email: str) -> UserModel | None:
        """Return user by email (case-insensitive) or None."""
        stmt = (
            select(UserModel)
            .where(func.lower(UserModel.email) == email.lower())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        query: str | None = None,
        is_active: bool | None = None,
        is_admin: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[UserModel]:
        """Paginated list with optional substring search on email/full_name."""
        stmt = select(UserModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(UserModel.email).like(pattern),
                    func.lower(func.coalesce(UserModel.full_name, "")).like(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(UserModel.is_active == is_active)
        if is_admin is not None:
            stmt = stmt.where(UserModel.is_admin == is_admin)
        stmt = stmt.order_by(UserModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_search(
        self,
        *,
        query: str | None = None,
        is_active: bool | None = None,
        is_admin: bool | None = None,
    ) -> int:
        """Count rows matching the same filters as search()."""
        stmt = select(func.count()).select_from(UserModel)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(UserModel.email).like(pattern),
                    func.lower(func.coalesce(UserModel.full_name, "")).like(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(UserModel.is_active == is_active)
        if is_admin is not None:
            stmt = stmt.where(UserModel.is_admin == is_admin)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_created_since(self, since: datetime) -> int:
        """Number of accounts registered on or after since (UTC)."""
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.created_at >= since)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
