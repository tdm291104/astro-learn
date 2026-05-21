"""One-shot LLM commentary that contextualises a catalog search."""

from __future__ import annotations

import structlog
from redis.asyncio import Redis

from core.llm.llm_client import LLMClient
from core.llm.prompt_templates import HOUSE_STYLE
from schemas.astronomy_schema import CatalogObject

_CACHE_TTL_SECONDS: int = 3600
_PROMPT_RESULT_LIMIT: int = 5
# ~150 tokens, fits a single render paragraph.
_MAX_OUTPUT_CHARS: int = 600


_logger = structlog.get_logger(__name__)


_COMMENTARY_PROMPT_TEMPLATE: str = (
    "{house_style}\n\n"
    "Write 1-2 sentences of astronomical context for a catalog search "
    "result page. The user searched {source} for {query!r}. Below is a "
    "compact view of the top hits — describe what the objects share "
    "(class, region of sky, distance regime, notable identifiers) or "
    "anything striking. Plain prose only, no markdown, no JSON, no "
    "citations. Keep it under 50 words.\n\nResults:\n{rows}"
)


class CatalogCommentaryService:
    """Produce + cache short prose context for a catalog search result page."""

    def __init__(self, *, redis: Redis, llm: LLMClient) -> None:
        self._redis = redis
        self._llm = llm

    async def get_or_create(
        self,
        *,
        query: str,
        source: str,
        results: list[CatalogObject],
    ) -> str | None:
        """Return cached commentary or generate fresh; None on empty/failure."""
        if not results:
            return None

        cache_key = self._cache_key(query=query, source=source)
        try:
            cached_raw = await self._redis.get(cache_key)
        except Exception as exc:                      # pragma: no cover — defensive
            _logger.warning(
                "catalog_commentary.redis_get_failed", error=str(exc), key=cache_key,
            )
            cached_raw = None
        if cached_raw is not None:
            return _decode_cache_value(cached_raw)

        text = await self._generate(query=query, source=source, results=results)
        if not text:
            # Skip cache so transient hiccup doesn't poison the key.
            return None

        try:
            await self._redis.setex(cache_key, _CACHE_TTL_SECONDS, text)
        except Exception as exc:                      # pragma: no cover — defensive
            _logger.warning(
                "catalog_commentary.redis_setex_failed",
                error=str(exc), key=cache_key,
            )
        return text

    async def _generate(
        self,
        *,
        query: str,
        source: str,
        results: list[CatalogObject],
    ) -> str | None:
        prompt = _COMMENTARY_PROMPT_TEMPLATE.format(
            house_style=HOUSE_STYLE,
            source=source,
            query=query,
            rows=_format_rows(results),
        )
        try:
            raw = await self._llm.complete(
                [{"role": "system", "content": prompt}],
                temperature=0.4,
            )
        except Exception as exc:
            # Catalog search must not fail due to commentary LLM hiccup.
            _logger.warning(
                "catalog_commentary.llm_failed",
                error=str(exc), source=source, query=query,
            )
            return None
        cleaned = (raw or "").strip()
        if not cleaned:
            return None
        return cleaned[:_MAX_OUTPUT_CHARS]

    @staticmethod
    def _cache_key(*, query: str, source: str) -> str:
        # Normalise so "  Orion " and "orion" hit the same key.
        normalised = " ".join(query.strip().lower().split())
        return f"catalog_commentary:{source}:{normalised}"


def _decode_cache_value(value: bytes | str) -> str:
    """Redis-py default is bytes; tolerate both."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _format_rows(results: list[CatalogObject]) -> str:
    """Compact one-line-per-result view for prompt context."""
    lines: list[str] = []
    for row in results[:_PROMPT_RESULT_LIMIT]:
        coord = (
            f"RA={row.ra_deg:.4f}° Dec={row.dec_deg:.4f}°"
            if row.ra_deg is not None and row.dec_deg is not None
            else "no coords"
        )
        type_str = row.object_type or "unknown type"
        lines.append(f"- {row.name} | {type_str} | {coord}")
    if len(results) > _PROMPT_RESULT_LIMIT:
        lines.append(f"- … and {len(results) - _PROMPT_RESULT_LIMIT} more results.")
    return "\n".join(lines)
