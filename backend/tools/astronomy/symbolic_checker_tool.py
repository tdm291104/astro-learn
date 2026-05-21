"""Rule-based FITS quality checker (R01–R08)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from astropy.io import fits
from pydantic import BaseModel, Field

from core.exceptions import NotFoundError
from tools.base_tool import BaseTool

_REQUIRED_WCS_KEYS = {"CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2"}

# BITPIX → expected numpy dtype kind.
_BITPIX_KIND: dict[int, str] = {
    8: "u",
    16: "i",
    32: "i",
    64: "i",
    -32: "f",
    -64: "f",
}


class Violation(BaseModel):
    rule_id: str
    severity: str  # info | warning | error
    message: str
    hdu_index: int | None = None


class CheckResult(BaseModel):
    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    summary: str = ""


def _check_nan_ratio(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None or not hasattr(data, "shape") or data.ndim < 2:
            continue
        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            continue
        ratio = float(np.isnan(arr).mean())
        if ratio > 0.5:
            out.append(
                Violation(
                    rule_id="R01",
                    severity="warning",
                    message=f"HDU {i} has {ratio:.0%} NaN values — possible data quality issue.",
                    hdu_index=i,
                )
            )
    return out


def _check_exptime(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        try:
            if "EXPTIME" not in hdu.header:
                continue
            val = hdu.header["EXPTIME"]
        except Exception:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            out.append(
                Violation(
                    rule_id="R02",
                    severity="error",
                    message=f"HDU {i} has non-positive EXPTIME={v} — may be calibration frame or invalid.",
                    hdu_index=i,
                )
            )
    return out


def _check_empty_hdu(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None:
            continue
        try:
            size = int(np.asarray(data).size)
        except Exception:
            continue
        if size == 0:
            out.append(
                Violation(
                    rule_id="R03",
                    severity="warning",
                    message=f"HDU {i} has zero data elements.",
                    hdu_index=i,
                )
            )
    return out


def _check_naxis(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        try:
            naxis = int(hdu.header.get("NAXIS", 0))
        except Exception:
            continue
        data = getattr(hdu, "data", None)
        if data is None:
            if naxis != 0:
                out.append(
                    Violation(
                        rule_id="R04",
                        severity="error",
                        message=f"HDU {i} declares NAXIS={naxis} but has no data array.",
                        hdu_index=i,
                    )
                )
            continue
        if hasattr(data, "ndim") and data.ndim != naxis:
            out.append(
                Violation(
                    rule_id="R04",
                    severity="error",
                    message=f"HDU {i} NAXIS={naxis} does not match data ndim={data.ndim}.",
                    hdu_index=i,
                )
            )
    return out


def _check_wcs_keywords(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None or not hasattr(data, "ndim") or data.ndim != 2:
            continue
        present = {k for k in _REQUIRED_WCS_KEYS if k in hdu.header}
        missing = _REQUIRED_WCS_KEYS - present
        if missing and present:
            out.append(
                Violation(
                    rule_id="R05",
                    severity="info",
                    message=f"HDU {i} has partial WCS — missing {sorted(missing)}.",
                    hdu_index=i,
                )
            )
    return out


def _check_bitpix(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None:
            continue
        # BinTable record arrays don't have BITPIX semantics.
        if data.dtype.kind == "V":
            continue
        try:
            bitpix = int(hdu.header.get("BITPIX", 0))
        except Exception:
            continue
        expected_kind = _BITPIX_KIND.get(bitpix)
        if expected_kind is None:
            continue
        actual_kind = data.dtype.kind
        if actual_kind != expected_kind:
            dtype_str = str(data.dtype)
            if len(dtype_str) > 80:
                dtype_str = dtype_str[:77] + "..."
            out.append(
                Violation(
                    rule_id="R06",
                    severity="warning",
                    message=(
                        f"HDU {i} BITPIX={bitpix} (kind '{expected_kind}') "
                        f"does not match data dtype {dtype_str} (kind '{actual_kind}')."
                    ),
                    hdu_index=i,
                )
            )
    return out


def _check_all_zeros(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None or not hasattr(data, "shape") or data.ndim < 2:
            continue
        arr = np.asarray(data)
        if arr.size == 0:
            continue
        finite = arr[np.isfinite(arr)] if arr.dtype.kind == "f" else arr
        if finite.size and np.all(finite == 0):
            out.append(
                Violation(
                    rule_id="R07",
                    severity="warning",
                    message=f"HDU {i} contains all-zero image data.",
                    hdu_index=i,
                )
            )
    return out


def _check_header_bloat(hdul: fits.HDUList) -> list[Violation]:
    out: list[Violation] = []
    for i, hdu in enumerate(hdul):
        try:
            n = len(hdu.header)
        except Exception:
            continue
        if n > 1000:
            out.append(
                Violation(
                    rule_id="R08",
                    severity="info",
                    message=f"HDU {i} header has {n} cards (>1000) — possible bloat.",
                    hdu_index=i,
                )
            )
    return out


_RULES: list[tuple[str, str, Callable[[fits.HDUList], list[Violation]], str]] = [
    ("R01", "NaN ratio > 50% in image HDU", _check_nan_ratio, "warning"),
    ("R02", "Negative or zero EXPTIME", _check_exptime, "error"),
    ("R03", "Empty HDU (zero elements)", _check_empty_hdu, "warning"),
    ("R04", "NAXIS mismatch with data shape", _check_naxis, "error"),
    ("R05", "Missing required WCS keywords", _check_wcs_keywords, "info"),
    ("R06", "BITPIX inconsistent with data type", _check_bitpix, "warning"),
    ("R07", "All-zero image data", _check_all_zeros, "warning"),
    ("R08", "Header keyword count > 1000", _check_header_bloat, "info"),
]


def _summarize(violations: list[Violation]) -> str:
    if not violations:
        return "No issues detected by symbolic checker."
    order = {"error": 0, "warning": 1, "info": 2}
    sorted_v = sorted(violations, key=lambda v: order.get(v.severity, 3))
    return " ".join(f"[{v.severity.upper()}] {v.message}" for v in sorted_v)


def _check_file_sync(path: Path) -> CheckResult:
    """Apply 8 rules; retry without memmap for HST rescaling cards."""
    violations: list[Violation] = []

    def _open(memmap: bool):
        return fits.open(str(path), memmap=memmap)

    try:
        hdul_cm = _open(memmap=True)
    except (OSError, ValueError) as e:
        if any(k in str(e) for k in ("BZERO", "BSCALE", "BLANK")):
            hdul_cm = _open(memmap=False)
        else:
            return CheckResult(
                passed=False,
                violations=[
                    Violation(
                        rule_id="OPEN",
                        severity="error",
                        message=f"Cannot open FITS file: {type(e).__name__}: {e}",
                    )
                ],
                summary=f"File could not be opened: {e}",
            )

    with hdul_cm as hdul:
        for _, _, fn, _ in _RULES:
            try:
                violations.extend(fn(hdul))
            except (OSError, ValueError) as e:
                if any(k in str(e) for k in ("BZERO", "BSCALE", "BLANK")):
                    with _open(memmap=False) as hdul2:
                        try:
                            violations.extend(fn(hdul2))
                        except Exception as e2:
                            violations.append(
                                Violation(
                                    rule_id="INTERNAL",
                                    severity="info",
                                    message=f"Rule '{fn.__name__}' failed: {type(e2).__name__}: {e2}",
                                )
                            )
                else:
                    violations.append(
                        Violation(
                            rule_id="INTERNAL",
                            severity="info",
                            message=f"Rule '{fn.__name__}' failed: {type(e).__name__}: {e}",
                        )
                    )
            except Exception as e:
                violations.append(
                    Violation(
                        rule_id="INTERNAL",
                        severity="info",
                        message=f"Rule '{fn.__name__}' failed: {type(e).__name__}: {e}",
                    )
                )

    passed = not any(v.severity == "error" for v in violations)
    return CheckResult(passed=passed, violations=violations, summary=_summarize(violations))


class SymbolicFitsCheckerInput(BaseModel):
    file_id: uuid.UUID


class SymbolicFitsCheckerTool(BaseTool):
    """Deterministic rule-based quality checks on stored FITS file."""

    name: ClassVar[str] = "symbolic_fits_checker"
    description: ClassVar[str] = (
        "Run 8 deterministic FITS quality rules (NaN ratio, EXPTIME, "
        "NAXIS, BITPIX, WCS, header bloat, all-zero data, empty HDU) on "
        "a stored file. Returns structured violations and a summary "
        "string. No LLM involved — output is byte-for-byte reproducible."
    )
    input_schema: ClassVar[type[BaseModel]] = SymbolicFitsCheckerInput

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        file_id: uuid.UUID = kwargs["file_id"]
        target = self.storage_root / "fits" / f"{file_id}.fits"
        if not target.exists():
            raise NotFoundError(
                message=f"FITS file not found at {target}",
                code="fits_not_found",
            )
        result = await asyncio.to_thread(_check_file_sync, target)
        return result.model_dump()

    @staticmethod
    async def check_path(path: Path) -> CheckResult:
        """Caller already has a Path; skip file_id lookup."""
        if not path.exists():
            raise NotFoundError(
                message=f"FITS file not found at {path}",
                code="fits_not_found",
            )
        return await asyncio.to_thread(_check_file_sync, path)
