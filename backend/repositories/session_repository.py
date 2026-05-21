"""DB access for SessionModel."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from models.fits_file_model import FitsFileModel
from models.session_model import SessionModel, session_fits_files
from repositories.base_repository import BaseRepository


class SessionRepository(BaseRepository[SessionModel]):
    """Conversation session table operations."""

    model = SessionModel

    async def get(self, id: uuid.UUID) -> SessionModel | None:
        """Fetch with fits_files eager-loaded (lazy load fails in async)."""
        stmt = (
            select(SessionModel)
            .options(selectinload(SessionModel.fits_files))
            .where(SessionModel.id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        notebook_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[SessionModel]:
        """Return sessions for user_id, newest first; optional notebook filter."""
        stmt = (
            select(SessionModel)
            .options(selectinload(SessionModel.fits_files))
            .where(SessionModel.user_id == user_id)
        )
        if notebook_id is not None:
            stmt = stmt.where(SessionModel.notebook_id == notebook_id)
        stmt = (
            stmt.order_by(SessionModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_with_messages(self, session_id: uuid.UUID) -> SessionModel | None:
        """Fetch session with messages eager-loaded (avoids async lazy-load)."""
        stmt = (
            select(SessionModel)
            .options(
                selectinload(SessionModel.messages),
                selectinload(SessionModel.fits_files),
            )
            .where(SessionModel.id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_title_if_unset(
        self,
        session_id: uuid.UUID,
        title: str,
    ) -> bool:
        """Write title only if currently NULL; True iff a row was updated."""
        if not title:
            return False
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.title.is_(None),
            )
            .values(title=title)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def attach_fits_file(
        self, session_id: uuid.UUID, fits_file_id: uuid.UUID
    ) -> SessionModel | None:
        """Add FITS file to the session's attachment set (idempotent)."""
        # Eager load lets us dedupe client-side; duplicate PK would raise.
        row = await self.get(session_id)
        if row is None:
            return None
        if any(f.id == fits_file_id for f in row.fits_files):
            return row
        file_row = await self.session.get(FitsFileModel, fits_file_id)
        if file_row is None:
            return None
        row.fits_files.append(file_row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def detach_fits_file(
        self, session_id: uuid.UUID, fits_file_id: uuid.UUID
    ) -> bool:
        """Remove one row from session_fits_files; True if removed."""
        stmt = delete(session_fits_files).where(
            session_fits_files.c.session_id == session_id,
            session_fits_files.c.fits_file_id == fits_file_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def list_solely_attached_fits_ids(
        self,
        session_id: uuid.UUID,
        candidate_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Return subset of candidate_ids attached only to this session."""
        if not candidate_ids:
            return []
        # COUNT(*) = 1 finds files with exactly one attachment row.
        stmt = (
            select(session_fits_files.c.fits_file_id)
            .where(session_fits_files.c.fits_file_id.in_(candidate_ids))
            .group_by(session_fits_files.c.fits_file_id)
            .having(func.count(session_fits_files.c.session_id) == 1)
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        # Re-intersect with our session_id; a sole attachment elsewhere isn't ours.
        own_stmt = select(session_fits_files.c.fits_file_id).where(
            session_fits_files.c.session_id == session_id,
            session_fits_files.c.fits_file_id.in_(rows),
        )
        own_result = await self.session.execute(own_stmt)
        return list(own_result.scalars().all())
