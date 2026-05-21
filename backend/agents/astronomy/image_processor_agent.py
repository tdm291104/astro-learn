"""Image processing on FITS images: stretching, smoothing, source detection."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.exceptions import AgentError
from core.llm.llm_client import LLMClient
from tools.base_tool import BaseTool

_VALID_OPERATIONS: frozenset[str] = frozenset(
    {"stretch", "smooth", "detect_sources", "annotate"}
)

_VALID_STRETCH_TYPES: frozenset[str] = frozenset(
    {"linear", "log", "sqrt", "asinh"}
)

_DEFAULT_STRETCH: str = "asinh"
_DEFAULT_SIGMA: float = 2.0
_DEFAULT_FWHM: float = 3.0
_DEFAULT_THRESHOLD_SIGMA: float = 5.0

# Cap protects payload size on dense source fields.
_MAX_SOURCES: int = 500


@AgentRegistry.register
class ImageProcessorAgent(BaseAgent):
    """Process a FITS image and emit a viewable artefact."""

    name: ClassVar[str] = "image_processor"
    description: ClassVar[str] = (
        "Process FITS images: contrast stretching, smoothing, source "
        "detection, annotation. Returns a viewable image artefact."
    )
    capabilities: ClassVar[list[str]] = ["image_stretch", "source_detection", "rendering"]

    def __init__(
        self,
        llm: LLMClient,
        tools: list[BaseTool] | None = None,
        *,
        storage_root: Path,
    ) -> None:
        super().__init__(llm=llm, tools=tools)
        self.storage_root = storage_root

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
        file_id, hdu_index, operation, params = self._validate_task(task)

        user_msg = AgentMessage(
            role="user",
            content=(
                f"Image op {operation} on file_id={file_id} hdu={hdu_index}"
            ),
        )
        state.append(user_msg)
        yield user_msg

        # Sanity check: file exists and has shape.
        meta = await self._fits_metadata(file_id, hdu_index)
        meta_msg = AgentMessage(
            role="tool",
            name="fits_reader",
            content=json.dumps(meta, default=str),
        )
        state.append(meta_msg)
        yield meta_msg

        if not meta.get("shape"):
            raise AgentError(
                message=(
                    f"HDU {hdu_index} of {file_id} has no image data "
                    f"(shape is empty / null)"
                ),
                code="no_image_data",
                details={"file_id": str(file_id), "hdu_index": hdu_index},
            )

        # Offload pixel work to thread.
        fits_path = self.storage_root / "fits" / f"{file_id}.fits"
        out_dir = self.storage_root / "fits_artifacts" / str(file_id)
        relative_path, stats = await asyncio.to_thread(
            _process_image_sync,
            fits_path=fits_path,
            file_id=file_id,
            hdu_index=hdu_index,
            operation=operation,
            params=params,
            out_dir=out_dir,
            run_id=state.run_id,
        )

        assistant_msg = AgentMessage(
            role="assistant",
            content=f"Wrote artefact: {relative_path}",
        )
        state.append(assistant_msg)
        yield assistant_msg

        state.final_output = {
            "artifact_url": relative_path,
            "stats": stats,
        }

    async def _fits_metadata(
        self,
        file_id: uuid.UUID,
        hdu_index: int,
    ) -> dict[str, Any]:
        tool = self.get_tool("fits_reader")
        if tool is None:
            raise AgentError(
                message="ImageProcessorAgent requires the 'fits_reader' tool",
                code="missing_tool",
                details={"required": "fits_reader"},
            )
        return await tool(
            file_id=file_id,
            hdu_index=hdu_index,
            include_headers=False,
            include_data_summary=False,
            include_data_array=False,
        )

    @staticmethod
    def _validate_task(
        task: dict[str, Any],
    ) -> tuple[uuid.UUID, int, str, dict[str, Any]]:
        raw_file_id = task.get("file_id")
        if raw_file_id is None:
            raise AgentError(
                message="ImageProcessorAgent requires task['file_id']",
                code="invalid_task",
            )
        if isinstance(raw_file_id, uuid.UUID):
            file_id = raw_file_id
        else:
            try:
                file_id = uuid.UUID(str(raw_file_id))
            except (TypeError, ValueError) as exc:
                raise AgentError(
                    message=f"Invalid file_id: {raw_file_id!r}",
                    code="invalid_task",
                ) from exc

        operation = task.get("operation")
        if operation not in _VALID_OPERATIONS:
            raise AgentError(
                message=f"Unknown operation: {operation!r}",
                code="invalid_task",
                details={
                    "operation": operation,
                    "valid": sorted(_VALID_OPERATIONS),
                },
            )

        try:
            hdu_index = int(task.get("hdu_index", 0))
        except (TypeError, ValueError) as exc:
            raise AgentError(
                message=f"Invalid hdu_index: {task.get('hdu_index')!r}",
                code="invalid_task",
            ) from exc
        if hdu_index < 0:
            raise AgentError(
                message=f"hdu_index must be >= 0, got {hdu_index}",
                code="invalid_task",
            )

        params = task.get("params") or {}
        if not isinstance(params, dict):
            raise AgentError(
                message=f"params must be a dict, got {type(params).__name__}",
                code="invalid_task",
            )
        return file_id, hdu_index, operation, params


def _process_image_sync(
    *,
    fits_path: Path,
    file_id: uuid.UUID,
    hdu_index: int,
    operation: str,
    params: dict[str, Any],
    out_dir: Path,
    run_id: uuid.UUID,
) -> tuple[str, dict[str, Any]]:
    """Open FITS, run op, save PNG; return (rel_path, stats)."""
    # Lazy imports so optional-dep failures become AgentError, not import error.
    import numpy as np
    from astropy.io import fits

    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise AgentError(
            message="ImageProcessorAgent requires matplotlib",
            code="optional_dep_missing",
            details={"missing": "matplotlib"},
        ) from exc

    def _load_plane(memmap: bool) -> Any:
        with fits.open(str(fits_path), memmap=memmap) as hdul:
            if hdu_index >= len(hdul):
                raise AgentError(
                    message=(
                        f"hdu_index {hdu_index} out of range "
                        f"(file has {len(hdul)} HDUs)"
                    ),
                    code="no_image_data",
                )
            data = hdul[hdu_index].data
            if data is None:
                raise AgentError(
                    message=f"HDU {hdu_index} has no image data",
                    code="no_image_data",
                )
            arr = np.asarray(data)
            while arr.ndim > 2:
                arr = arr[0]
            if arr.ndim < 2:
                raise AgentError(
                    message=(
                        f"HDU {hdu_index} is not a 2-D image (ndim={arr.ndim})"
                    ),
                    code="no_image_data",
                )
            return arr.astype(np.float64, copy=True)

    try:
        plane = _load_plane(memmap=True)
    except (OSError, ValueError) as exc:
        # HST raw rescaling (BZERO/BSCALE/BLANK) rejects memmap.
        if any(k in str(exc) for k in ("BZERO", "BSCALE", "BLANK")):
            plane = _load_plane(memmap=False)
        else:
            raise

    # Ops return (display_plane, extra_stats, markers).
    if operation == "stretch":
        display, extra, markers = _op_stretch(plane, params, np)
    elif operation == "smooth":
        display, extra, markers = _op_smooth(plane, params, np)
    elif operation == "detect_sources":
        display, extra, markers = _op_detect_sources(plane, params, np)
    elif operation == "annotate":
        display, extra, markers = _op_annotate(plane, params, np)
    else:                                        # pragma: no cover — guarded above
        raise AgentError(
            message=f"Unknown operation: {operation!r}",
            code="invalid_task",
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{operation}_{run_id.hex}.png"
    out_path = out_dir / out_name
    _save_png(display, out_path, markers=markers, plt_module=plt, np_module=np)

    # Stats reflect rendered PNG (post-op).
    stats = _basic_stats(display, np_module=np)
    stats.update(extra)

    relative = f"fits_artifacts/{file_id}/{out_name}"
    return relative, stats


def _op_stretch(
    plane: Any,
    params: dict[str, Any],
    np: Any,
) -> tuple[Any, dict[str, Any], list[dict[str, Any]] | None]:
    """Apply contrast transform; return plane + meta."""
    stretch_type = str(params.get("stretch_type", _DEFAULT_STRETCH)).lower()
    if stretch_type not in _VALID_STRETCH_TYPES:
        raise AgentError(
            message=f"Unknown stretch_type: {stretch_type!r}",
            code="invalid_task",
            details={"valid": sorted(_VALID_STRETCH_TYPES)},
        )

    finite_min = float(np.nanmin(plane)) if np.isfinite(plane).any() else 0.0

    if stretch_type == "linear":
        out = plane
    elif stretch_type == "log":
        # Shift so min becomes small positive (log undefined elsewhere).
        shift = (-finite_min if finite_min < 0 else 0.0) + 1e-6
        out = np.log10(plane + shift)
    elif stretch_type == "sqrt":
        shift = -finite_min if finite_min < 0 else 0.0
        out = np.sqrt(plane + shift)
    else:                                        # asinh
        out = np.arcsinh(plane)

    return out, {"stretch_type": stretch_type}, None


def _op_smooth(
    plane: Any,
    params: dict[str, Any],
    np: Any,
) -> tuple[Any, dict[str, Any], list[dict[str, Any]] | None]:
    """Gaussian (or box-filter fallback) smoothing."""
    try:
        sigma = float(params.get("sigma", _DEFAULT_SIGMA))
    except (TypeError, ValueError) as exc:
        raise AgentError(
            message=f"Invalid sigma: {params.get('sigma')!r}",
            code="invalid_task",
        ) from exc
    if sigma <= 0:
        raise AgentError(
            message=f"sigma must be > 0, got {sigma}",
            code="invalid_task",
        )

    try:
        from scipy.ndimage import gaussian_filter
        out = gaussian_filter(plane, sigma=sigma)
        method = "scipy.gaussian_filter"
    except ImportError:
        # Box-filter fallback; window odd, scales with sigma.
        kernel = max(3, (int(round(2 * sigma)) | 1))
        out = _box_filter_numpy(plane, kernel, np_module=np)
        method = "numpy_box_filter"

    return out, {"sigma": sigma, "method": method}, None


def _op_detect_sources(
    plane: Any,
    params: dict[str, Any],
    np: Any,
) -> tuple[Any, dict[str, Any], list[dict[str, Any]] | None]:
    """Detect sources via photutils; return image + centroid markers."""
    try:
        fwhm = float(params.get("fwhm", _DEFAULT_FWHM))
        threshold_sigma = float(params.get("threshold_sigma", _DEFAULT_THRESHOLD_SIGMA))
    except (TypeError, ValueError) as exc:
        raise AgentError(
            message="detect_sources requires numeric `fwhm` and `threshold_sigma`",
            code="invalid_task",
        ) from exc

    finite_mask = np.isfinite(plane)
    if not finite_mask.any():
        return plane, {
            "method": "skipped",
            "source_count": 0,
            "note": "image has no finite pixels",
        }, []

    median = float(np.median(plane[finite_mask]))
    stddev = float(np.std(plane[finite_mask]))

    sources: list[dict[str, Any]] = []
    method: str
    try:
        from photutils.detection import DAOStarFinder

        threshold = threshold_sigma * stddev if stddev > 0 else 1e-6
        finder = DAOStarFinder(fwhm=fwhm, threshold=threshold)
        table = finder(plane - median)
        method = "photutils.DAOStarFinder"
        if table is not None and len(table) > 0:
            # photutils <3: xcentroid; >=3: x_centroid.
            x_col = _first_present(table.colnames, ("x_centroid", "xcentroid"))
            y_col = _first_present(table.colnames, ("y_centroid", "ycentroid"))
            for row in table[:_MAX_SOURCES]:
                sources.append(
                    {
                        "x": float(row[x_col]) if x_col else None,
                        "y": float(row[y_col]) if y_col else None,
                        "flux": float(row["flux"]) if "flux" in table.colnames else None,
                    }
                )
    except ImportError:
        method = "numpy_sigma_clip"
        # No centroids; stats-only fallback when photutils missing.

    extra: dict[str, Any] = {
        "method": method,
        "source_count": len(sources),
        "fwhm": fwhm,
        "threshold_sigma": threshold_sigma,
        "background_median": median,
        "background_stddev": stddev,
    }
    return plane, extra, sources


def _op_annotate(
    plane: Any,
    params: dict[str, Any],
    np: Any,
) -> tuple[Any, dict[str, Any], list[dict[str, Any]] | None]:
    """Overlay user markers on the image."""
    raw_markers = params.get("markers")
    if not isinstance(raw_markers, list) or not raw_markers:
        raise AgentError(
            message="annotate requires non-empty `params.markers` list",
            code="invalid_task",
        )

    markers: list[dict[str, Any]] = []
    for entry in raw_markers:
        if not isinstance(entry, dict):
            raise AgentError(
                message=f"Each marker must be an object, got {type(entry).__name__}",
                code="invalid_task",
            )
        try:
            x = float(entry["x"])
            y = float(entry["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AgentError(
                message="Each marker must carry numeric `x` and `y`",
                code="invalid_task",
            ) from exc
        marker: dict[str, Any] = {"x": x, "y": y}
        if "label" in entry and entry["label"] is not None:
            marker["label"] = str(entry["label"])
        markers.append(marker)

    return plane, {"marker_count": len(markers)}, markers


def _basic_stats(display: Any, *, np_module: Any) -> dict[str, Any]:
    """min/max/mean/stddev/n_finite of rendered plane."""
    finite_mask = np_module.isfinite(display)
    n_finite = int(finite_mask.sum())
    if n_finite == 0:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "stddev": 0.0,
            "n_finite": 0,
        }
    finite = display[finite_mask]
    return {
        "min": float(np_module.min(finite)),
        "max": float(np_module.max(finite)),
        "mean": float(np_module.mean(finite)),
        "stddev": float(np_module.std(finite)),
        "n_finite": n_finite,
    }


def _save_png(
    display: Any,
    out_path: Path,
    *,
    markers: list[dict[str, Any]] | None,
    plt_module: Any,
    np_module: Any,
) -> None:
    """Save plane as PNG with optional markers; ZScale → percentile fallback."""
    finite_mask = np_module.isfinite(display)
    if finite_mask.any():
        try:
            from astropy.visualization import ZScaleInterval
            vmin, vmax = ZScaleInterval().get_limits(display[finite_mask])
            vmin = float(vmin)
            vmax = float(vmax)
        except Exception:                        # pragma: no cover — fallback
            vmin = float(np_module.percentile(display[finite_mask], 1))
            vmax = float(np_module.percentile(display[finite_mask], 99))
        # ZScale degenerates on constant images; force flat-but-renderable.
        if not (vmin < vmax):
            vmin = float(np_module.min(display[finite_mask]))
            vmax = vmin + 1.0
    else:
        vmin, vmax = 0.0, 1.0

    fig, ax = plt_module.subplots(figsize=(4, 4), dpi=100)
    ax.imshow(display, cmap="gray", origin="lower", vmin=vmin, vmax=vmax)
    ax.set_axis_off()

    if markers:
        xs = [m["x"] for m in markers]
        ys = [m["y"] for m in markers]
        ax.scatter(xs, ys, s=40, edgecolors="red", facecolors="none", linewidths=1.0)
        for m in markers:
            label = m.get("label")
            if label:
                ax.annotate(label, xy=(m["x"], m["y"]), color="red", fontsize=8)

    fig.tight_layout(pad=0)
    fig.savefig(out_path, bbox_inches="tight", pad_inches=0)
    plt_module.close(fig)


def _first_present(names: Any, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in names:
            return c
    return None


def _box_filter_numpy(arr: Any, kernel: int, *, np_module: Any) -> Any:
    """Naive box filter fallback when scipy unavailable."""
    if kernel <= 1:
        return arr
    pad = kernel // 2
    padded = np_module.pad(arr, pad, mode="edge")
    out = np_module.empty_like(arr, dtype=float)
    h, w = arr.shape
    for i in range(h):
        for j in range(w):
            window = padded[i : i + kernel, j : j + kernel]
            out[i, j] = float(np_module.mean(window))
    return out
