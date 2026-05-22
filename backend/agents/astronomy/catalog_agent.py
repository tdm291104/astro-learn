"""Astronomical catalog lookup across Simbad, NED, and VizieR."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError
from core.llm.llm_client import LLMClient
from memory.long_term.catalog_cache import CatalogCache
from tools.base_tool import BaseTool

# Mirrors CatalogSource.
_VALID_SOURCES: frozenset[str] = frozenset({"simbad", "ned", "vizier"})

_DEFAULT_LIMIT: int = 20

# "RA,Dec" decimal-degree pair.
_RA_DEC_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$"
)


@AgentRegistry.register
class CatalogAgent(BaseAgent):
    """Look up astronomical objects in catalogs."""

    name: ClassVar[str] = "catalog"
    description: ClassVar[str] = (
        "Look up astronomical objects in SIMBAD, NED, VizieR, or NASA "
        "archives. Returns RA/Dec, object type, and references."
    )
    capabilities: ClassVar[list[str]] = ["simbad_query", "ned_query", "vizier_query"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        catalog_cache: CatalogCache | None = None,
    ) -> None:
        # catalog_cache=None disables caching (test path).
        super().__init__(llm=llm, tools=tools)
        self.catalog_cache = catalog_cache

    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self,
        task: dict[str, Any],
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        query, source, radius_arcsec, limit = self._validate_task(task)

        user_msg = AgentMessage(
            role="user",
            content=f"Catalog lookup: query={query!r} source={source} limit={limit}",
        )
        state.append(user_msg)
        yield user_msg

        # Coord queries skip cache (unbounded key space, cheap upstream).
        coords = _parse_ra_dec(query)
        is_name_form = coords is None
        cache_eligible = is_name_form and self.catalog_cache is not None

        if cache_eligible:
            cached = await self.catalog_cache.lookup(query, source)
            if cached is not None:
                # Tool-name matches a miss so transcript shape is identical.
                hit_tool_name = _tool_name_for_source(source)
                cache_tool_msg = AgentMessage(
                    role="tool",
                    name=hit_tool_name,
                    content=json.dumps(cached),
                    extra={"cache_hit": True},
                )
                state.append(cache_tool_msg)
                yield cache_tool_msg

                cache_assistant_msg = AgentMessage(
                    role="assistant",
                    content=_render_summary(list(cached), source),
                )
                state.append(cache_assistant_msg)
                yield cache_assistant_msg

                state.final_output = {"results": list(cached)}
                return

        tool_name, raw_rows = await self._call_catalog_tool(
            source, query, coords, radius_arcsec, limit,
        )

        tool_msg = AgentMessage(
            role="tool",
            name=tool_name,
            content=json.dumps(raw_rows),
        )
        state.append(tool_msg)
        yield tool_msg

        # Defensive normalisation guards against tool drift.
        results = [_normalise_row(r) for r in raw_rows]

        # Don't cache empties (would shadow future SIMBAD additions).
        if cache_eligible and results:
            try:
                await self.catalog_cache.store(query, source, results)
            except Exception:                                  # pragma: no cover
                pass

        # Actionable empty message distinguishes from tool/auth failure.
        if results:
            summary = _render_summary(results, source)
        else:
            summary = (
                f"No matches found in {source} for {query!r}. "
                f"Verify the spelling, try an alternate designation "
                f"(e.g. 'NGC 224' for M31), or widen radius_arcsec for "
                f"coordinate queries."
            )
        assistant_msg = AgentMessage(role="assistant", content=summary)
        state.append(assistant_msg)
        yield assistant_msg

        state.final_output = {"results": results}

    async def _call_catalog_tool(
        self,
        source: str,
        query: str,
        coords: tuple[float, float] | None,
        radius_arcsec: float | None,
        limit: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Dispatch to Astroquery wrapper for source; return rows."""
        # Shared calling convention: object_name XOR ra/dec/radius_arcsec.
        tool_name = _tool_name_for_source(source)
        tool = self.get_tool(tool_name)
        if tool is None:
            raise AgentError(
                message=(
                    f"CatalogAgent requires the {tool_name!r} tool for "
                    f"source={source!r}"
                ),
                code="missing_tool",
                details={"required": tool_name, "source": source},
            )

        if coords is None:
            kwargs: dict[str, Any] = {"object_name": query, "limit": limit}
        else:
            ra_deg, dec_deg = coords
            kwargs = {"ra_deg": ra_deg, "dec_deg": dec_deg, "limit": limit}
            if radius_arcsec is not None:
                kwargs["radius_arcsec"] = radius_arcsec

        rows = await tool(**kwargs)
        return tool_name, list(rows or [])

    @staticmethod
    def _validate_task(
        task: dict[str, Any],
    ) -> tuple[str, str, float | None, int]:
        query = task.get("query")
        if not isinstance(query, str) or not query.strip():
            raise AgentError(
                message="CatalogAgent requires task['query'] (non-empty str)",
                code="invalid_task",
            )

        # Normalize case so a planner LLM that hallucinates "SIMBAD" /
        # "Simbad" doesn't crash the run. The valid-source check still
        # catches genuinely unknown values.
        raw_source = task.get("source", "simbad")
        source = (
            raw_source.lower().strip()
            if isinstance(raw_source, str)
            else raw_source
        )
        if source not in _VALID_SOURCES:
            raise AgentError(
                message=f"Unknown catalog source: {raw_source!r}",
                code="invalid_task",
                details={"source": raw_source, "valid": sorted(_VALID_SOURCES)},
            )

        radius_arcsec = task.get("radius_arcsec")
        if radius_arcsec is not None:
            try:
                radius_arcsec = float(radius_arcsec)
            except (TypeError, ValueError) as exc:
                raise AgentError(
                    message=f"Invalid radius_arcsec: {radius_arcsec!r}",
                    code="invalid_task",
                ) from exc

        try:
            limit = int(task.get("limit", _DEFAULT_LIMIT))
        except (TypeError, ValueError) as exc:
            raise AgentError(
                message=f"Invalid limit: {task.get('limit')!r}",
                code="invalid_task",
            ) from exc
        if limit < 1:
            raise AgentError(
                message=f"limit must be >= 1, got {limit}",
                code="invalid_task",
            )

        return query.strip(), source, radius_arcsec, limit


# Centralised so cache + live dispatch naming stay in lock-step.
_SOURCE_TO_TOOL: dict[str, str] = {
    "simbad": "simbad_query",
    "ned": "ned_query",
    "vizier": "vizier_query",
}


def _tool_name_for_source(source: str) -> str:
    return _SOURCE_TO_TOOL[source]


_SUMMARY_PREVIEW_LIMIT: int = 3


def _render_summary(results: list[dict[str, Any]], source: str) -> str:
    """One-line summary naming top hits with coords."""
    if not results:
        return f"No matches found in {source}."

    pieces: list[str] = []
    for row in results[:_SUMMARY_PREVIEW_LIMIT]:
        name = str(row.get("name") or "?").strip() or "?"
        obj_type = row.get("object_type")
        ra = row.get("ra_deg")
        dec = row.get("dec_deg")
        chunk = name
        if isinstance(obj_type, str) and obj_type.strip():
            chunk = f"{chunk} ({obj_type.strip()})"
        if isinstance(ra, (int, float)) and isinstance(dec, (int, float)):
            chunk = f"{chunk} at RA {ra:.4f}°, Dec {dec:.4f}°"
        pieces.append(chunk)

    head = f"Found {len(results)} match(es) in {source}: " + "; ".join(pieces)
    if len(results) > _SUMMARY_PREVIEW_LIMIT:
        head += f"; and {len(results) - _SUMMARY_PREVIEW_LIMIT} more."
    else:
        head += "."
    return head


def _parse_ra_dec(query: str) -> tuple[float, float] | None:
    """Parse "RA,Dec" comma pair → (ra_deg, dec_deg) or None."""
    match = _RA_DEC_PATTERN.match(query)
    if match is None:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:  # pragma: no cover — regex enforced numeric
        return None


def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Defensive re-stamp to lock API contract against tool drift."""
    return {
        "name": str(row.get("name") or ""),
        "ra_deg": _coerce_float_or_none(row.get("ra_deg")),
        "dec_deg": _coerce_float_or_none(row.get("dec_deg")),
        "object_type": _str_or_none(row.get("object_type")),
        "references": list(row.get("references") or []),
        "extra": dict(row.get("extra") or {}),
    }


def _coerce_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
