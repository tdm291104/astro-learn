"""VizieR lookup via Astroquery (`astroquery.vizier`)."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from core.exceptions import ExternalServiceError
from tools.base_tool import BaseTool


class VizierQueryInput(BaseModel):
    """Provide name OR coordinates."""

    object_name: str | None = None
    ra_deg: float | None = Field(None, ge=0.0, lt=360.0)
    dec_deg: float | None = Field(None, ge=-90.0, le=90.0)
    radius_arcsec: float | None = Field(None, ge=0.0, le=3600.0)
    catalog: str | None = Field(
        None,
        description="Restrict to a single VizieR catalog code (e.g. 'I/239/hip_main')",
    )
    limit: int = Field(20, ge=1, le=200)

    @model_validator(mode="after")
    def _name_or_coords(self) -> VizierQueryInput:
        has_name = self.object_name is not None
        has_coords = self.ra_deg is not None and self.dec_deg is not None
        if not (has_name or has_coords):
            raise ValueError("Provide `object_name` or both `ra_deg` and `dec_deg`.")
        return self


class VizierTool(BaseTool):
    """Query VizieR via Astroquery; normalized rows across catalogs."""

    name: ClassVar[str] = "vizier_query"
    description: ClassVar[str] = (
        "Look up astronomical objects in VizieR catalog aggregator by name or "
        "coordinates. Optionally restrict to a single catalog code. Returns RA, "
        "Dec, object type, and per-row catalog provenance."
    )
    input_schema: ClassVar[type[BaseModel]] = VizierQueryInput

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._query_sync,
            object_name=kwargs.get("object_name"),
            ra_deg=kwargs.get("ra_deg"),
            dec_deg=kwargs.get("dec_deg"),
            radius_arcsec=kwargs.get("radius_arcsec"),
            catalog=kwargs.get("catalog"),
            limit=kwargs.get("limit", 20),
        )

    @staticmethod
    def _query_sync(
        *,
        object_name: str | None,
        ra_deg: float | None,
        dec_deg: float | None,
        radius_arcsec: float | None,
        catalog: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.vizier import Vizier

        # Per-call instance: ROW_LIMIT must not leak across calls.
        vizier = Vizier()
        vizier.ROW_LIMIT = limit
        catalog_filter = [catalog] if catalog else None

        try:
            if object_name is not None:
                tables = vizier.query_object(object_name, catalog=catalog_filter)
            else:
                assert ra_deg is not None and dec_deg is not None
                radius = (radius_arcsec if radius_arcsec is not None else 5.0) * u.arcsec
                coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
                tables = vizier.query_region(
                    coord,
                    radius=radius,
                    catalog=catalog_filter,
                )
        except Exception as exc:
            raise ExternalServiceError(
                message=f"VizieR query failed: {exc}",
                code="vizier_query_failed",
            ) from exc

        if tables is None or len(tables) == 0:
            return []

        rows: list[dict[str, Any]] = []
        # Deterministic key order so truncation by limit is stable.
        keys = list(getattr(tables, "keys", lambda: [])())
        if not keys:
            # Older astroquery exposes direct iteration.
            keys = list(range(len(tables)))

        for key in keys:
            table = tables[key]
            if table is None or len(table) == 0:
                continue
            catalog_code = str(key) if isinstance(key, str) else None
            for idx in range(len(table)):
                if len(rows) >= limit:
                    break
                rows.append(_row_to_object(table, idx, catalog_code=catalog_code))
            if len(rows) >= limit:
                break
        return rows


# Catalog-specific columns; RA/DEC variants are well-known.
_NAME_COLS: tuple[str, ...] = ("Name", "MAIN_ID", "main_id", "Object", "Source")
_RA_COLS: tuple[str, ...] = ("RAJ2000", "RA_ICRS", "_RAJ2000", "RA", "ra")
_DEC_COLS: tuple[str, ...] = ("DEJ2000", "DE_ICRS", "_DEJ2000", "DEC", "dec")
_TYPE_COLS: tuple[str, ...] = ("OType", "otype", "Type", "SpType")
_CORE_COLS: frozenset[str] = frozenset(_NAME_COLS + _RA_COLS + _DEC_COLS + _TYPE_COLS)


def _row_to_object(table: Any, idx: int, *, catalog_code: str | None) -> dict[str, Any]:
    """Normalize VizieR row; preserves catalog provenance."""
    row = table[idx]
    name = _pick_value(row, _NAME_COLS)
    ra_deg = _pick_float(row, _RA_COLS)
    dec_deg = _pick_float(row, _DEC_COLS)
    object_type = _pick_value(row, _TYPE_COLS)

    extra: dict[str, Any] = {}
    if catalog_code is not None:
        extra["catalog"] = catalog_code
    for col in table.colnames:
        if col in _CORE_COLS:
            continue
        try:
            value = row[col]
        except KeyError:  # pragma: no cover
            continue
        if value is None or (hasattr(value, "mask") and bool(getattr(value, "mask", False))):
            continue
        extra[col] = _coerce_jsonable(value)

    # Fallback to catalog code so label is never empty.
    fallback_name = catalog_code or ""
    return {
        "name": str(name) if name is not None else fallback_name,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "object_type": str(object_type) if object_type is not None else None,
        "references": [],
        "extra": extra,
    }


def _pick_value(row: Any, candidates: tuple[str, ...]) -> Any:
    for col in candidates:
        try:
            value = row[col]
        except (KeyError, IndexError):
            continue
        if hasattr(value, "mask") and bool(getattr(value, "mask", False)):
            return None
        return value
    return None


def _pick_float(row: Any, candidates: tuple[str, ...]) -> float | None:
    value = _pick_value(row, candidates)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
