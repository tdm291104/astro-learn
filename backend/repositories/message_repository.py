"""DB access for MessageModel."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from models.message_model import MessageModel
from repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository[MessageModel]):
    """Message table operations."""

    model = MessageModel

    async def list_for_session(
        self,
        session_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[MessageModel]:
        """Return messages of `session_id` in chronological order."""
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
