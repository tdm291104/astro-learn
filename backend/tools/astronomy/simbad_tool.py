"""SIMBAD lookup via Astroquery."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from core.exceptions import ExternalServiceError
from tools.base_tool import BaseTool


class SimbadQueryInput(BaseModel):
    """Provide name OR coordinates."""

    object_name: str | None = None
    ra_deg: float | None = Field(None, ge=0.0, lt=360.0)
    dec_deg: float | None = Field(None, ge=-90.0, le=90.0)
    radius_arcsec: float | None = Field(None, ge=0.0, le=3600.0)
    fields: list[str] = Field(default_factory=list)
    limit: int = Field(20, ge=1, le=200)

    @model_validator(mode="after")
    def _name_or_coords(self) -> SimbadQueryInput:
        has_name = self.object_name is not None
        has_coords = self.ra_deg is not None and self.dec_deg is not None
        if not (has_name or has_coords):
            raise ValueError("Provide `object_name` or both `ra_deg` and `dec_deg`.")
        return self


class SimbadTool(BaseTool):
    """Query SIMBAD via Astroquery; return normalized rows."""

    name: ClassVar[str] = "simbad_query"
    description: ClassVar[str] = (
        "Look up astronomical objects in the SIMBAD database by name or coordinates. "
        "Returns RA, Dec, object type, and any requested catalog fields."
    )
    input_schema: ClassVar[type[BaseModel]] = SimbadQueryInput

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._query_sync,
            object_name=kwargs.get("object_name"),
            ra_deg=kwargs.get("ra_deg"),
            dec_deg=kwargs.get("dec_deg"),
            radius_arcsec=kwargs.get("radius_arcsec"),
            extra_fields=kwargs.get("fields") or [],
            limit=kwargs.get("limit", 20),
        )

    @staticmethod
    def _query_sync(
        *,
        object_name: str | None,
        ra_deg: float | None,
        dec_deg: float | None,
        radius_arcsec: float | None,
        extra_fields: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        # Lazy import: astroquery cold-import is slow.
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.simbad import Simbad

        # Per-call instance avoids polluting class-level votable cache.
        simbad = Simbad()
        simbad.ROW_LIMIT = limit
        # Best-effort: SIMBAD TAP capabilities hit may fail offline.
        try:
            simbad.add_votable_fields("otype", *extra_fields)
        except Exception:
            pass

        try:
            if object_name is not None:
                table = simbad.query_object(object_name)
            else:
                # Validator guarantees both ra_deg and dec_deg set.
                assert ra_deg is not None and dec_deg is not None
                radius = (radius_arcsec if radius_arcsec is not None else 5.0) * u.arcsec
                coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
                table = simbad.query_region(coord, radius=radius)
        except Exception as exc:
            raise ExternalServiceError(
                message=f"SIMBAD query failed: {exc}",
                code="simbad_query_failed",
            ) from exc

        if table is None or len(table) == 0:
            return []

        return [_row_to_object(table, idx) for idx in range(min(len(table), limit))]


def _row_to_object(table: Any, idx: int) -> dict[str, Any]:
    """Normalise Simbad row to CatalogObject shape."""
    row = table[idx]
    name = _pick_value(row, ("MAIN_ID", "main_id"))
    # New astroquery: ra/dec; older: RA_d/DEC_d or RA(d)/DEC(d).
    ra_deg = _pick_float(row, ("ra", "RA_d", "ra_d", "RA(d)"))
    dec_deg = _pick_float(row, ("dec", "DEC_d", "dec_d", "DEC(d)"))
    object_type = _pick_value(row, ("OTYPE", "otype"))

    extra: dict[str, Any] = {}
    core_columns = {"MAIN_ID", "main_id", "RA", "DEC", "RA_d", "ra_d",
                    "DEC_d", "dec_d", "ra", "dec", "OTYPE", "otype"}
    for col in table.colnames:
        if col in core_columns:
            continue
        try:
            value = row[col]
        except KeyError:  # pragma: no cover
            continue
        # Drop masked/None to keep payload small.
        if value is None or (hasattr(value, "mask") and bool(getattr(value, "mask", False))):
            continue
        extra[col] = _coerce_jsonable(value)

    return {
        "name": str(name) if name is not None else "",
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
        # MaskedColumn returns a sentinel for missing → None.
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
    """Reduce numpy/astropy scalars to plain Python."""
    if hasattr(value, "item"):  # numpy scalar
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
