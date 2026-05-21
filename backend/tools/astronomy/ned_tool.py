"""NED lookup via Astroquery (`astroquery.ipac.ned`)."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from core.exceptions import ExternalServiceError
from tools.base_tool import BaseTool


class NedQueryInput(BaseModel):
    """Provide name OR coordinates."""

    object_name: str | None = None
    ra_deg: float | None = Field(None, ge=0.0, lt=360.0)
    dec_deg: float | None = Field(None, ge=-90.0, le=90.0)
    radius_arcsec: float | None = Field(None, ge=0.0, le=3600.0)
    limit: int = Field(20, ge=1, le=200)

    @model_validator(mode="after")
    def _name_or_coords(self) -> NedQueryInput:
        has_name = self.object_name is not None
        has_coords = self.ra_deg is not None and self.dec_deg is not None
        if not (has_name or has_coords):
            raise ValueError("Provide `object_name` or both `ra_deg` and `dec_deg`.")
        return self


class NedTool(BaseTool):
    """Query NED via Astroquery; return normalized rows."""

    name: ClassVar[str] = "ned_query"
    description: ClassVar[str] = (
        "Look up astronomical objects in the NASA/IPAC Extragalactic Database (NED) "
        "by name or coordinates. Returns RA, Dec, object type, and references."
    )
    input_schema: ClassVar[type[BaseModel]] = NedQueryInput

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._query_sync,
            object_name=kwargs.get("object_name"),
            ra_deg=kwargs.get("ra_deg"),
            dec_deg=kwargs.get("dec_deg"),
            radius_arcsec=kwargs.get("radius_arcsec"),
            limit=kwargs.get("limit", 20),
        )

    @staticmethod
    def _query_sync(
        *,
        object_name: str | None,
        ra_deg: float | None,
        dec_deg: float | None,
        radius_arcsec: float | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        # Lazy import: astroquery cold-import is slow.
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.ipac.ned import Ned

        try:
            if object_name is not None:
                table = Ned.query_object(object_name)
            else:
                assert ra_deg is not None and dec_deg is not None
                # 5" default matches SimbadTool.
                radius = (radius_arcsec if radius_arcsec is not None else 5.0) * u.arcsec
                coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
                table = Ned.query_region(coord, radius=radius)
        except Exception as exc:
            raise ExternalServiceError(
                message=f"NED query failed: {exc}",
                code="ned_query_failed",
            ) from exc

        if table is None or len(table) == 0:
            return []

        return [_row_to_object(table, idx) for idx in range(min(len(table), limit))]


# Astroquery version drift; probe variants.
_NAME_COLS: tuple[str, ...] = ("Object Name", "object_name", "main_id")
_RA_COLS: tuple[str, ...] = ("RA", "RA(deg)", "ra")
_DEC_COLS: tuple[str, ...] = ("DEC", "DEC(deg)", "dec")
_TYPE_COLS: tuple[str, ...] = ("Type", "object_type", "OType")
_REF_COLS: tuple[str, ...] = ("References", "references")
_CORE_COLS: frozenset[str] = frozenset(_NAME_COLS + _RA_COLS + _DEC_COLS + _TYPE_COLS + _REF_COLS)


def _row_to_object(table: Any, idx: int) -> dict[str, Any]:
    """Normalize NED row to CatalogObject shape."""
    row = table[idx]
    name = _pick_value(row, _NAME_COLS)
    ra_deg = _pick_float(row, _RA_COLS)
    dec_deg = _pick_float(row, _DEC_COLS)
    object_type = _pick_value(row, _TYPE_COLS)

    refs_raw = _pick_value(row, _REF_COLS)
    if refs_raw is None:
        references: list[str] = []
    elif isinstance(refs_raw, (list, tuple)):
        references = [str(r) for r in refs_raw if r is not None]
    else:
        # Scalar count or single ref string; one entry for provenance.
        references = [str(refs_raw)]

    extra: dict[str, Any] = {}
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

    return {
        "name": str(name) if name is not None else "",
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "object_type": str(object_type) if object_type is not None else None,
        "references": references,
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
