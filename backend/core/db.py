"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config import get_settings


def _build_engine() -> AsyncEngine:
    """Construct the async engine from settings."""
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.APP_ENV == "development",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=3600,
    )


# Singleton so Alembic and FastAPI share the same engine.
engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to the request lifecycle."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close all pooled connections on FastAPI shutdown."""
    await engine.dispose()


# Celery's per-task asyncio loop breaks asyncpg pool reuse; workers need
# a fresh engine per task to avoid "connection bound to closed loop".

def build_task_engine() -> AsyncEngine:
    """Short-lived engine for a single Celery task; NullPool sidesteps loop reuse."""
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )


@asynccontextmanager
async def task_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield a sessionmaker bound to a fresh engine, disposed on exit."""
    task_engine = build_task_engine()
    try:
        yield async_sessionmaker(
            bind=task_engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    finally:
        await task_engine.dispose()
