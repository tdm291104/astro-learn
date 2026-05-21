"""Astronomy routes — FITS upload, analysis, catalog search, reports."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse

from core.dependencies import (
    AstronomyServiceDep,
    CatalogCommentaryServiceDep,
    CurrentUserDep,
    get_storage_root,
)
from core.exceptions import ValidationError
from core.sample_fits import SAMPLE_FITS, is_sample_seeded
from schemas.astronomy_schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    CatalogSearchRequest,
    CatalogSearchResponse,
    FitsUploadResponse,
    ReportRequest,
    ReportResponse,
    SampleFitsItem,
    SampleFitsListResponse,
)

router = APIRouter(prefix="/astronomy", tags=["astronomy"])


# Bigger cap than documents (raw images / data cubes hit hundreds of MB).
_MAX_FITS_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MiB

# Drives the 200 vs 202 split for inline vs queued analyses.
_INLINE_ANALYSIS_TYPES: frozenset[str] = frozenset({"image_stats"})

_REPORT_MEDIA_TYPES: dict[str, str] = {
    "markdown": "text/markdown",
    "html": "text/html",
    "pdf": "application/pdf",
}
_REPORT_DOWNLOAD_EXTENSIONS: dict[str, str] = {
    "markdown": "md",
    "html": "html",
    "pdf": "pdf",
}


@router.post(
    "/upload-fits",
    response_model=FitsUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fits(
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
    file: UploadFile = File(...),
) -> FitsUploadResponse:
    """Upload a FITS file (inline header parse, async artefact build)."""
    if file.size is not None and file.size > _MAX_FITS_SIZE_BYTES:
        raise ValidationError(
            message=(
                f"FITS file exceeds {_MAX_FITS_SIZE_BYTES // (1024 * 1024)} MiB cap "
                f"({file.size} bytes received)"
            ),
            code="file_too_large",
        )

    content = await file.read()
    if len(content) > _MAX_FITS_SIZE_BYTES:
        raise ValidationError(
            message=(
                f"FITS file exceeds {_MAX_FITS_SIZE_BYTES // (1024 * 1024)} MiB cap "
                f"({len(content)} bytes received)"
            ),
            code="file_too_large",
        )

    return await service.upload_fits(
        current_user.id,
        filename=file.filename or "unnamed.fits",
        content=content,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
    response: Response,
) -> AnalyzeResponse:
    """Run analysis (inline types return 200, queued types return 202)."""
    result = await service.analyze(current_user.id, request)
    if request.analysis_type not in _INLINE_ANALYSIS_TYPES:
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
async def get_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> AnalyzeResponse:
    """Polling endpoint for queued analyses (owner-scoped)."""
    return await service.get_analysis(analysis_id, current_user.id)


@router.get("/analyses", response_model=list[AnalyzeResponse])
async def list_analyses(
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> list[AnalyzeResponse]:
    """List the current user's analyses (newest first)."""
    return await service.list_analyses(current_user.id)


@router.get("/catalog/search", response_model=CatalogSearchResponse)
async def search_catalog(
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
    commentary_service: CatalogCommentaryServiceDep,
    query: str,
    source: str = "simbad",
    radius_arcsec: float | None = None,
    limit: int = 20,
) -> CatalogSearchResponse:
    """Query Simbad / NED / VizieR via the catalog agent."""
    request = CatalogSearchRequest(
        query=query,
        source=source,                                # type: ignore[arg-type]
        radius_arcsec=radius_arcsec,
        limit=limit,
    )
    response = await service.search_catalog(current_user.id, request)
    # Commentary best-effort; None on empty hits or LLM failure.
    response.commentary = await commentary_service.get_or_create(
        query=response.query,
        source=response.source,
        results=list(response.results),
    )
    return response


@router.get("/files", response_model=list[FitsUploadResponse])
async def list_fits_files(
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> list[FitsUploadResponse]:
    """Return the current user's uploaded FITS files (newest first)."""
    return await service.list_fits_files(current_user.id)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fits_file(
    file_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> Response:
    """Delete an owned FITS file plus its derived artefacts (owner-scoped)."""
    await service.delete_fits_file(current_user.id, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/files/{file_id}/artifacts/{filename}")
async def download_fits_artifact(
    file_id: uuid.UUID,
    filename: str,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> FileResponse:
    """Serve a derived FITS artifact by filename (owner-scoped)."""
    path = await service.get_fits_artifact(file_id, filename, current_user.id)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=filename)


@router.post("/report", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> ReportResponse:
    """Render a report from a succeeded analysis. Returns the download URL."""
    return await service.generate_report(current_user.id, request)


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AstronomyServiceDep,
) -> FileResponse:
    """Stream the rendered report file (owner-scoped)."""
    path, report = await service.get_report_for_download(report_id, current_user.id)
    media_type = _REPORT_MEDIA_TYPES.get(report.format, "application/octet-stream")
    extension = _REPORT_DOWNLOAD_EXTENSIONS.get(report.format, "bin")
    # Strip CR/LF/quotes to avoid Content-Disposition header injection.
    safe_title = (
        report.title.replace("\r", " ").replace("\n", " ").replace('"', "'")
    )
    filename = f"{safe_title}.{extension}"
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/sample-fits", response_model=SampleFitsListResponse)
async def list_sample_fits(
    current_user: CurrentUserDep,
    storage_root: Annotated[Path, Depends(get_storage_root)],
) -> SampleFitsListResponse:
    """Return curated FITS samples for the anomaly-audit demo."""
    items = [
        SampleFitsItem(
            file_id=s.file_id,
            display_name=s.display_name,
            description=s.description,
            instrument=s.instrument,
            size_mb=s.size_mb,
            expected_anomalies=s.expected_anomalies,
            seeded=is_sample_seeded(s, storage_root),
        )
        for s in SAMPLE_FITS
    ]
    return SampleFitsListResponse(items=items)
