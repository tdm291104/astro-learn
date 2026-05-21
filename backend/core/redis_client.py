"""Process-wide async Redis client and lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator

from redis.asyncio import ConnectionPool, Redis

from core.config import get_settings


def _build_pool() -> ConnectionPool:
    """Build a connection pool bound to settings.REDIS_URL."""
    settings = get_settings()
    return ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )


_pool: ConnectionPool = _build_pool()

# Tests should override get_redis instead of reaching for this directly.
redis_client: Redis = Redis(connection_pool=_pool)


async def get_redis() -> AsyncIterator[Redis]:
    """FastAPI DI provider yielding the shared client."""
    yield redis_client


async def close_redis() -> None:
    """Close the connection pool on FastAPI shutdown."""
    await redis_client.aclose()
    await _pool.disconnect()
