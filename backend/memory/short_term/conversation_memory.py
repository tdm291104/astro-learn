"""Redis-backed working window for an agent's conversation context."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from agents.base.agent_message import AgentMessage

_KEY_PREFIX = "conv"

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_MESSAGES = 100


class ConversationMemory:
    """Per-session conversation window stored in Redis."""

    def __init__(
        self,
        redis: Redis,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages

    async def history(
        self,
        session_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> list[AgentMessage]:
        """Most recent `limit` messages, oldest-first."""
        effective_limit = limit if limit is not None else self.max_messages
        if effective_limit <= 0:
            return []
        # LRANGE -N -1: last N, oldest-first within slice (RPUSH order).
        raw = await self.redis.lrange(
            self._key(session_id), -effective_limit, -1
        )
        return [AgentMessage.model_validate_json(item) for item in raw]

    async def length(self, session_id: uuid.UUID) -> int:
        return int(await self.redis.llen(self._key(session_id)))

    async def append(self, session_id: uuid.UUID, message: AgentMessage) -> None:
        """Append, trim, refresh TTL atomically."""
        key = self._key(session_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, message.model_dump_json())
            pipe.ltrim(key, -self.max_messages, -1)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def append_many(
        self,
        session_id: uuid.UUID,
        messages: list[AgentMessage],
    ) -> None:
        """Append batch atomically."""
        if not messages:
            return
        key = self._key(session_id)
        encoded = [m.model_dump_json() for m in messages]
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, *encoded)
            pipe.ltrim(key, -self.max_messages, -1)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def trim_to(self, session_id: uuid.UUID, max_messages: int) -> None:
        """Drop oldest so at most `max_messages` remain."""
        if max_messages <= 0:
            await self.clear(session_id)
            return
        await self.redis.ltrim(
            self._key(session_id), -max_messages, -1
        )

    async def clear(self, session_id: uuid.UUID) -> None:
        await self.redis.delete(self._key(session_id))

    @staticmethod
    def _key(session_id: uuid.UUID) -> str:
        return f"{_KEY_PREFIX}:{session_id}"
