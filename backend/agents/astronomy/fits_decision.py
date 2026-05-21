"""Header-driven analysis-type inference for FITS files."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def extract_header_summary(
    primary_headers: dict[str, Any],
    hdu_shapes: list[list[int] | None],
) -> dict[str, Any]:
    """Project raw header dict into fixed-shape summary (missing → None)."""
    get_str = _string_getter(primary_headers)
    get_int = _int_getter(primary_headers)
    get_float = _float_getter(primary_headers)
    get_bool = _bool_getter(primary_headers)

    ctype1 = get_str("CTYPE1")
    ctype2 = get_str("CTYPE2")
    has_wcs = _looks_like_sky_wcs(ctype1, ctype2)

    return {
        "naxis": get_int("NAXIS"),
        "naxis1": get_int("NAXIS1"),
        "naxis2": get_int("NAXIS2"),
        "naxis3": get_int("NAXIS3"),
        "bitpix": get_int("BITPIX"),
        "simple": get_bool("SIMPLE"),
        "filter": get_str("FILTER"),
        "instrument": get_str("INSTRUME"),
        "telescope": get_str("TELESCOP"),
        "exptime": get_float("EXPTIME"),
        "object": get_str("OBJECT"),
        "bunit": get_str("BUNIT"),
        "ctype1": ctype1,
        "ctype2": ctype2,
        "crval1": get_float("CRVAL1"),
        "crval2": get_float("CRVAL2"),
        "has_wcs": has_wcs,
        "hdu_shapes": list(hdu_shapes),
    }


def infer_analysis_types(
    header_summary: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Map header summary → (analysis_types, notes). See docs/workflow-redesign.md §2.3."""
    naxis = header_summary.get("naxis")
    filter_ = header_summary.get("filter")
    has_wcs = bool(header_summary.get("has_wcs"))
    ctype1 = (header_summary.get("ctype1") or "").upper()
    bunit = (header_summary.get("bunit") or "").strip().lower()
    simple = header_summary.get("simple")

    notes: list[str] = []

    if simple is False:
        notes.append(
            "File is marked SIMPLE=F (non-standard FITS). Only basic image "
            "statistics are reliable."
        )
        return ["image_stats"], notes

    if naxis == 1 and ctype1 in {"WAVE", "WAVELENGTH"}:
        return ["spectroscopy"], notes

    if isinstance(naxis, int) and naxis >= 3:
        notes.append(
            f"Multi-dimensional cube (NAXIS={naxis}); statistics computed on "
            f"the first 2D slice."
        )
        return ["image_stats"], notes

    if naxis == 2 and filter_:
        types: list[str] = ["photometry", "image_stats"]
        if has_wcs:
            types.append("wcs")
        return types, notes

    # NAXIS=2 + WCS but no FILTER: WCS reads headers, no calibration needed.
    if naxis == 2 and has_wcs:
        return ["image_stats", "wcs"], notes

    if naxis == 2 and bunit == "counts":
        return ["image_stats"], notes

    if naxis == 2:
        # This branch: has_wcs=False AND filter_=None.
        notes.append(
            "Header lacks FILTER and WCS — running image_stats only; "
            "photometry would need explicit params."
        )
        return ["image_stats"], notes

    notes.append("Unrecognised FITS layout — running image_stats only.")
    return ["image_stats"], notes


def _looks_like_sky_wcs(ctype1: str | None, ctype2: str | None) -> bool:
    """True if CTYPE1/2 describe celestial projection."""
    if not ctype1 or not ctype2:
        return False
    head = ctype1.upper()
    return (
        head.startswith(("RA", "GLON", "ELON"))
        or "TAN" in head
        or "SIN" in head
    )


def _string_getter(headers: dict[str, Any]) -> Callable[[str], str | None]:
    def _get(key: str) -> str | None:
        raw = headers.get(key)
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None
    return _get


def _int_getter(headers: dict[str, Any]) -> Callable[[str], int | None]:
    def _get(key: str) -> int | None:
        raw = headers.get(key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return _get


def _float_getter(headers: dict[str, Any]) -> Callable[[str], float | None]:
    def _get(key: str) -> float | None:
        raw = headers.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return _get


def _bool_getter(headers: dict[str, Any]) -> Callable[[str], bool | None]:
    def _get(key: str) -> bool | None:
        raw = headers.get(key)
        if raw is None:
            return None
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            token = raw.strip().upper()
            if token in {"T", "TRUE", "1"}:
                return True
            if token in {"F", "FALSE", "0"}:
                return False
            return None
        if isinstance(raw, (int, float)):
            return bool(raw)
        return None
    return _get
