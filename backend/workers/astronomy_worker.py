"""Background FITS tasks: ingest and analysis."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from core.db import task_session_factory
from core.exceptions import NotFoundError
from core.storage import fits_artifacts_dir
from repositories.analysis_repository import AnalysisRepository
from repositories.fits_file_repository import FitsFileRepository
from services._agent_run_recorder import AgentRunRecorder
from workers._deps import (
    get_worker_agent_factory,
    get_worker_fits_reader,
    get_worker_storage_root,
)
from workers.celery_app import celery_app
from workflows.astronomy_workflow import AstronomyWorkflow

_logger = structlog.get_logger(__name__)


# image_stats runs inline; rest go through data_analyst.
_HEAVY_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {"photometry", "spectroscopy", "wcs_solve", "custom"}
)

_SOURCE_DETECT_FWHM: float = 3.0
_SOURCE_DETECT_THRESHOLD_SIGMA: float = 5.0
_SOURCE_DETECT_MAX_ROWS: int = 1000


@celery_app.task(name="workers.astronomy.ingest_fits", bind=True, max_retries=3)
def ingest_fits(
    self: Any,                           # noqa: ANN401
    file_id: str,
    filename: str,
) -> dict[str, Any]:
    """Ingest: render thumbnail + detect sources."""
    return asyncio.run(
        _async_ingest_fits(file_id=uuid.UUID(file_id), filename=filename)
    )


@celery_app.task(name="workers.astronomy.run_analysis", bind=True, max_retries=2)
def run_analysis(
    self: Any,                           # noqa: ANN401
    analysis_id: str,
    file_id: str,
    analysis_type: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Async analysis when the sync path is too slow."""
    return asyncio.run(
        _async_run_analysis(
            analysis_id=uuid.UUID(analysis_id),
            file_id=uuid.UUID(file_id),
            analysis_type=analysis_type,
            params=params,
        )
    )


async def _async_ingest_fits(
    *,
    file_id: uuid.UUID,
    filename: str,
) -> dict[str, Any]:
    """Render thumbnail + detect sources, best-effort per artefact."""
    storage_root = get_worker_storage_root()

    async with task_session_factory() as sf:
        storage_path = await _begin_ingesting(sf, file_id)

        artefacts: dict[str, Any] = {}
        try:
            target = storage_root / storage_path
            if not target.exists():
                raise NotFoundError(
                    message=f"FITS file missing on disk: {target}",
                    code="fits_file_missing",
                )

            out_dir = fits_artifacts_dir(storage_root, file_id)

            # Offload sync numpy/astropy work to thread.
            artefacts = await asyncio.to_thread(
                _render_artefacts_sync,
                fits_path=target,
                out_dir=out_dir,
            )

            await _set_fits_status(sf, file_id, "ready")

            _logger.info(
                "fits.ingested",
                file_id=str(file_id),
                artefacts=list(artefacts.keys()),
            )
            return {
                "file_id": str(file_id),
                "status": "ready",
                "artefacts": artefacts,
            }

        except Exception as exc:
            # Re-raise so Celery retry kicks in.
            await _set_fits_status(sf, file_id, "failed", error=str(exc))
            _logger.exception(
                "fits.ingest_failed",
                file_id=str(file_id),
                error=str(exc),
            )
            raise


async def _begin_ingesting(
    session_factory: Any,
    file_id: uuid.UUID,
) -> str:
    """Flip parsed → ingesting; return storage_path."""
    async with session_factory() as session:
        repo = FitsFileRepository(session)
        row = await repo.get(file_id)
        if row is None:
            raise NotFoundError(
                message=f"FITS file {file_id} not found",
                code="fits_not_found",
            )
        await repo.set_status(file_id, "ingesting")
        await session.commit()
        return row.storage_path


async def _set_fits_status(
    session_factory: Any,
    file_id: uuid.UUID,
    status: str,
    *,
    error: str | None = None,
) -> None:
    """Best-effort status update; never raises."""
    try:
        async with session_factory() as session:
            repo = FitsFileRepository(session)
            await repo.set_status(file_id, status, error=error)
            await session.commit()
    except Exception:
        _logger.exception(
            "fits.status_update_failed",
            file_id=str(file_id),
            target_status=status,
        )


def _render_artefacts_sync(
    *,
    fits_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Render thumbnail + source list; return manifest."""
    import numpy as np
    from astropy.io import fits

    manifest: dict[str, Any] = {}

    def _build(hdul: Any) -> None:
        image_hdu_index = _find_image_hdu(hdul)
        if image_hdu_index is None:
            manifest["note"] = "no image HDU; skipped thumbnail and source detection"
            return

        data = np.asarray(hdul[image_hdu_index].data)
        manifest["thumbnail"] = _render_thumbnail(
            data=data, out_dir=out_dir, np_module=np
        )
        manifest["sources"] = _detect_sources(
            data=data, out_dir=out_dir, np_module=np
        )

    hdul = fits.open(str(fits_path), memmap=True)
    try:
        try:
            _build(hdul)
        except (OSError, ValueError) as exc:
            # HST raw rescaling (BZERO/BSCALE/BLANK) rejects memmap.
            if any(k in str(exc) for k in ("BZERO", "BSCALE", "BLANK")):
                hdul.close()
                hdul = fits.open(str(fits_path), memmap=False)
                manifest.clear()
                _build(hdul)
            else:
                raise
    finally:
        hdul.close()

    return manifest


def _find_image_hdu(hdul: Any) -> int | None:
    """Index of first 2-D image HDU, else None."""
    for index, hdu in enumerate(hdul):
        data = hdu.data
        if data is None:
            continue
        shape = getattr(data, "shape", None)
        if shape is None:
            continue
        if len(shape) >= 2 and all(s > 0 for s in shape[-2:]):
            return index
    return None


def _render_thumbnail(
    *,
    data: Any,
    out_dir: Path,
    np_module: Any,
) -> dict[str, Any]:
    """Save PNG thumbnail at fits_artifacts/{file_id}/thumbnail.png."""
    try:
        import matplotlib
        matplotlib.use("Agg")           # headless backend
        import matplotlib.pyplot as plt
        from astropy.visualization import ZScaleInterval
    except ImportError as exc:
        return {"skipped": True, "reason": f"missing dep: {exc.name}"}

    try:
        # Reduce cubes/multi-frame to 2-D via leading slice.
        plane = data
        while plane.ndim > 2:
            plane = plane[0]

        # Drop NaN/Inf so ZScaleInterval works.
        finite_mask = np_module.isfinite(plane)
        if not finite_mask.any():
            return {"skipped": True, "reason": "image has no finite pixels"}

        vmin, vmax = ZScaleInterval().get_limits(plane[finite_mask])

        out_path = out_dir / "thumbnail.png"
        fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
        ax.imshow(plane, cmap="gray", origin="lower", vmin=vmin, vmax=vmax)
        ax.set_axis_off()
        fig.tight_layout(pad=0)
        fig.savefig(out_path, bbox_inches="tight", pad_inches=0)
        plt.close(fig)

        return {
            "path": f"fits_artifacts/{out_dir.name}/thumbnail.png",
            "shape": list(plane.shape),
        }
    except Exception as exc:                                  # pragma: no cover
        # Don't fail ingest on render glitch.
        return {"skipped": True, "reason": f"render error: {exc}"}


def _detect_sources(
    *,
    data: Any,
    out_dir: Path,
    np_module: Any,
) -> dict[str, Any]:
    """source_list.json via DAOStarFinder; sigma-clip fallback."""
    plane = data
    while plane.ndim > 2:
        plane = plane[0]

    finite_mask = np_module.isfinite(plane)
    if not finite_mask.any():
        return {"skipped": True, "reason": "image has no finite pixels"}

    finite_pixels = plane[finite_mask]
    median = float(np_module.median(finite_pixels))
    stddev = float(np_module.std(finite_pixels))

    payload: dict[str, Any]
    try:
        from photutils.detection import DAOStarFinder

        threshold = _SOURCE_DETECT_THRESHOLD_SIGMA * stddev
        finder = DAOStarFinder(fwhm=_SOURCE_DETECT_FWHM, threshold=threshold)
        table = finder(plane - median)
        if table is None or len(table) == 0:
            sources: list[dict[str, Any]] = []
        else:
            # Cap rows so JSON stays sane on dense fields.
            cols = ("xcentroid", "ycentroid", "flux", "peak")
            sources = [
                {col: float(row[col]) for col in cols if col in row.colnames}
                for row in table[:_SOURCE_DETECT_MAX_ROWS]
            ]
        payload = {
            "method": "photutils.DAOStarFinder",
            "fwhm": _SOURCE_DETECT_FWHM,
            "threshold_sigma": _SOURCE_DETECT_THRESHOLD_SIGMA,
            "median": median,
            "stddev": stddev,
            "source_count": len(sources),
            "truncated": (
                table is not None and len(table) > _SOURCE_DETECT_MAX_ROWS
            ),
            "sources": sources,
        }
    except ImportError:
        payload = {
            "method": "numpy_sigma_clip",
            "note": "photutils not installed; recording summary stats only",
            "median": median,
            "stddev": stddev,
            "min": float(np_module.min(finite_pixels)),
            "max": float(np_module.max(finite_pixels)),
            "source_count": 0,
            "sources": [],
        }
    except Exception as exc:                                  # pragma: no cover
        return {"skipped": True, "reason": f"detection error: {exc}"}

    out_path = out_dir / "source_list.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "path": f"fits_artifacts/{out_dir.name}/source_list.json",
        "method": payload["method"],
        "source_count": payload["source_count"],
    }


async def _async_run_analysis(
    *,
    analysis_id: uuid.UUID,
    file_id: uuid.UUID,
    analysis_type: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch on analysis_type; persist outcome to AnalysisModel."""
    async with task_session_factory() as sf:
        owner_id, hdu_index = await _begin_running(sf, analysis_id, file_id)

        try:
            if analysis_type == "image_stats":
                results, artifacts = await _run_image_stats(
                    file_id=file_id, hdu_index=hdu_index
                )
                agent_run_id = None
            elif analysis_type in _HEAVY_ANALYSIS_TYPES:
                results, artifacts, agent_run_id = await _run_via_workflow(
                    session_factory=sf,
                    analysis_id=analysis_id,
                    owner_id=owner_id,
                    file_id=file_id,
                    hdu_index=hdu_index,
                    analysis_type=analysis_type,
                    params=params,
                )
            else:
                raise ValueError(f"Unknown analysis_type: {analysis_type!r}")

            await _set_analysis_terminal(
                sf,
                analysis_id,
                "succeeded",
                results=results,
                artifacts=artifacts,
                agent_run_id=agent_run_id,
            )

            _logger.info(
                "analysis.succeeded",
                analysis_id=str(analysis_id),
                analysis_type=analysis_type,
            )
            return {
                "analysis_id": str(analysis_id),
                "status": "succeeded",
                "results": results,
                "artifacts": artifacts,
            }

        except Exception as exc:
            # Re-raise so Celery retry kicks in.
            await _set_analysis_terminal(
                sf,
                analysis_id,
                "failed",
                error=str(exc),
            )
            _logger.exception(
                "analysis.failed",
                analysis_id=str(analysis_id),
                analysis_type=analysis_type,
                error=str(exc),
            )
            raise


async def _begin_running(
    session_factory: Any,
    analysis_id: uuid.UUID,
    file_id: uuid.UUID,
) -> tuple[uuid.UUID, int]:
    """Flip pending → running; return (owner_id, hdu_index)."""
    async with session_factory() as session:
        repo = AnalysisRepository(session)
        row = await repo.get(analysis_id)
        if row is None:
            raise NotFoundError(
                message=f"Analysis {analysis_id} not found",
                code="analysis_not_found",
            )
        if row.file_id != file_id:
            raise ValueError(
                f"Analysis {analysis_id} file_id mismatch "
                f"(stored={row.file_id}, task={file_id})"
            )
        await repo.mark_running(analysis_id, datetime.now(UTC))
        await session.commit()
        return row.owner_id, row.hdu_index


async def _set_analysis_terminal(
    session_factory: Any,
    analysis_id: uuid.UUID,
    status: str,
    *,
    results: dict[str, Any] | None = None,
    artifacts: list[str] | None = None,
    error: str | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> None:
    """Best-effort terminal status; never raises."""
    try:
        async with session_factory() as session:
            repo = AnalysisRepository(session)
            await repo.set_terminal(
                analysis_id,
                status,
                results=results,
                artifacts=artifacts,
                error=error,
                finished_at=datetime.now(UTC),
            )
            # Write agent_run_id separately to keep set_terminal narrow.
            if agent_run_id is not None:
                await repo.update(analysis_id, {"agent_run_id": agent_run_id})
            await session.commit()
    except Exception:
        _logger.exception(
            "analysis.status_update_failed",
            analysis_id=str(analysis_id),
            target_status=status,
        )


async def _run_image_stats(
    *,
    file_id: uuid.UUID,
    hdu_index: int,
) -> tuple[dict[str, Any], list[str]]:
    """Cheap inline summary stats via FitsReaderTool."""
    fits_reader = get_worker_fits_reader()
    parsed = await fits_reader.execute(
        file_id=file_id,
        hdu_index=hdu_index,
        include_headers=False,
        include_data_summary=True,
        include_data_array=False,
    )
    return parsed.get("data_summary", {}), []


async def _run_via_workflow(
    *,
    session_factory: Any,
    analysis_id: uuid.UUID,
    owner_id: uuid.UUID,
    file_id: uuid.UUID,
    hdu_index: int,
    analysis_type: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[str], uuid.UUID]:
    """Heavy analysis via AstronomyWorkflow; one agent_runs row per workflow."""
    factory = get_worker_agent_factory()
    recorder = AgentRunRecorder(session_factory=session_factory)
    workflow = AstronomyWorkflow(agent_factory=factory)

    task: dict[str, Any] = {
        "file_id": str(file_id),
        "hdu_index": hdu_index,
        "analysis_type": analysis_type,
        "params": params,
        "analysis_id": str(analysis_id),
        "render_image": bool(params.get("render_image", False)),
    }

    async with recorder.run(
        user_id=owner_id,
        session_id=None,
        agent_name="astronomy_workflow",
        task=task,
    ) as handle:
        workflow_state = await workflow.run(
            {
                "file_id": file_id,
                "hdu_index": hdu_index,
                "analysis_type": analysis_type,
                "params": params,
                "render_image": task["render_image"],
            }
        )
        output = workflow_state.final_output or {}
        handle.set_output(output)

    results = dict(output.get("results", {}))
    artifacts_raw = output.get("artifacts") or []
    artifacts = [str(a) for a in artifacts_raw]
    return results, artifacts, handle.run_id
