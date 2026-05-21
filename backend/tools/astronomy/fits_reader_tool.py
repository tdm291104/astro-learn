"""FITS file parsing via Astropy."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from core.exceptions import NotFoundError, ToolError
from tools.base_tool import BaseTool

# Cap to keep LLM tool-result sane on large images (4Kx4K = 16M).
_MAX_ARRAY_ELEMENTS: int = 1000


class FitsReaderInput(BaseModel):
    file_id: uuid.UUID
    hdu_index: int = Field(0, ge=0)
    include_headers: bool = True
    include_data_summary: bool = True
    include_data_array: bool = False


class FitsReaderTool(BaseTool):
    """Read a stored FITS file; return structure + headers."""

    name: ClassVar[str] = "fits_reader"
    description: ClassVar[str] = (
        "Open a FITS file previously uploaded to the system and return its "
        "HDU structure, header keywords, and (optionally) data summaries."
    )
    input_schema: ClassVar[type[BaseModel]] = FitsReaderInput

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        target = self._resolve_path(kwargs["file_id"])
        if not target.exists():
            raise NotFoundError(
                message=f"FITS file not found at {target}",
                code="fits_not_found",
            )
        return await asyncio.to_thread(
            self._parse_sync,
            target,
            file_id=kwargs["file_id"],
            hdu_index=kwargs.get("hdu_index", 0),
            include_headers=kwargs.get("include_headers", True),
            include_data_summary=kwargs.get("include_data_summary", True),
            include_data_array=kwargs.get("include_data_array", False),
        )

    def _resolve_path(self, file_id: uuid.UUID) -> Path:
        return self.storage_root / "fits" / f"{file_id}.fits"

    @staticmethod
    def _parse_sync(
        target: Path,
        *,
        file_id: uuid.UUID,
        hdu_index: int,
        include_headers: bool,
        include_data_summary: bool,
        include_data_array: bool,
    ) -> dict[str, Any]:
        # Lazy import: numpy+astropy cost hundreds of ms cold.
        import numpy as np
        from astropy.io import fits
        from astropy.io.fits.verify import VerifyError

        def _open(memmap: bool):
            return fits.open(str(target), memmap=memmap)

        try:
            hdul = _open(memmap=True)
        except (OSError, VerifyError, ValueError) as exc:
            raise ToolError(
                message=f"Not a valid FITS file: {target}",
                code="fits_invalid",
            ) from exc

        def _build_result(hdul_local) -> dict[str, Any]:
            hdu_count = len(hdul_local)
            if hdu_index >= hdu_count:
                raise ToolError(
                    message=f"hdu_index {hdu_index} out of range (file has {hdu_count} HDUs)",
                    code="fits_hdu_out_of_range",
                )
            hdu = hdul_local[hdu_index]
            data = hdu.data  # None for empty PrimaryHDU
            shape = list(data.shape) if data is not None and hasattr(data, "shape") else None
            result: dict[str, Any] = {
                "file_id": str(file_id),
                "hdu_count": hdu_count,
                "hdu_index": hdu_index,
                "hdu_type": type(hdu).__name__,
                "name": hdu.name or None,
                "shape": shape,
                "n_keywords": len(hdu.header),
            }
            if include_headers:
                result["headers"] = _serialise_header(hdu.header)
            if include_data_summary and data is not None and shape is not None:
                result["data_summary"] = _summarise_array(np, data)
            if include_data_array and data is not None and shape is not None:
                result["data_array"] = _truncate_array(np, data, shape)
            return result

        try:
            try:
                return _build_result(hdul)
            except (OSError, ValueError) as exc:
                # HST raw rescaling (BZERO/BSCALE/BLANK) rejects memmap.
                if any(k in str(exc) for k in ("BZERO", "BSCALE", "BLANK")):
                    hdul.close()
                    hdul = _open(memmap=False)
                    return _build_result(hdul)
                raise
        finally:
            hdul.close()


def _serialise_header(header: Any) -> list[dict[str, Any]]:
    """Astropy Header → ordered list of card dicts."""
    out: list[dict[str, Any]] = []
    for card in header.cards:
        value = card.value
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            value = str(value)
        out.append({
            "keyword": card.keyword,
            "value": value,
            "comment": card.comment,
        })
    return out


def _summarise_array(np_module: Any, data: Any) -> dict[str, Any]:
    """min/max/mean/stddev + NaN count for numeric array."""
    try:
        arr = np_module.asarray(data)
        if not np_module.issubdtype(arr.dtype, np_module.number):
            return {"dtype": str(arr.dtype), "size": int(arr.size), "summary_skipped": True}
        finite = arr[np_module.isfinite(arr)] if arr.size else arr
        if finite.size == 0:
            return {"size": int(arr.size), "all_non_finite": True}
        return {
            "dtype": str(arr.dtype),
            "size": int(arr.size),
            "min": float(np_module.min(finite)),
            "max": float(np_module.max(finite)),
            "mean": float(np_module.mean(finite)),
            "stddev": float(np_module.std(finite)),
            "nan_count": int(np_module.sum(~np_module.isfinite(arr))),
        }
    except Exception as exc:  # non-array HDUs (tables) land here
        return {"summary_error": str(exc)}


def _truncate_array(np_module: Any, data: Any, shape: list[int]) -> dict[str, Any]:
    """Flatten + cap to _MAX_ARRAY_ELEMENTS for sane JSON."""
    arr = np_module.asarray(data)
    flat = arr.flatten()
    truncated = flat.size > _MAX_ARRAY_ELEMENTS
    if truncated:
        flat = flat[:_MAX_ARRAY_ELEMENTS]
    return {
        "values": flat.tolist(),
        "original_shape": shape,
        "returned_count": int(flat.size),
        "truncated": truncated,
    }
