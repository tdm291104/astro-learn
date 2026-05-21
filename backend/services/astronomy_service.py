"""Astronomy data logic: FITS upload, analysis, catalog search, reports."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any

import structlog

from agents.astronomy.fits_decision import extract_header_summary
from agents.base.agent_state import AgentState
from core.agent_factory import DefaultAgentFactory
from core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from core.llm.llm_client import LLMClient
from core.storage import safe_extension, write_bytes
from models.analysis_model import AnalysisModel
from models.fits_file_model import FitsFileModel
from models.report_model import ReportModel
from repositories.analysis_repository import AnalysisRepository
from repositories.fits_file_repository import FitsFileRepository
from repositories.report_repository import ReportRepository
from schemas.astronomy_schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    CatalogObject,
    CatalogSearchRequest,
    CatalogSearchResponse,
    FitsHduSummary,
    FitsUploadResponse,
    ReportRequest,
    ReportResponse,
)
from services._agent_run_recorder import AgentRunRecorder
from services._astronomy_gate import check_fits_relevance_with_llm
from tools.astronomy.fits_reader_tool import FitsReaderTool
from workers.astronomy_worker import ingest_fits, run_analysis

# Canonicalised to ".fits" on disk so FitsReaderTool can resolve by id.
_ALLOWED_FITS_EXTENSIONS: set[str] = {".fits", ".fit", ".fts"}
_REJECT_SENTINEL_EXTENSION: str = ".bin"
_CANONICAL_FITS_EXTENSION: str = ".fits"

# Enqueued types; only image_stats runs inline.
_HEAVY_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {"photometry", "spectroscopy", "wcs_solve", "custom"}
)

_REPORT_EXTENSIONS: dict[str, str] = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
}

_logger = structlog.get_logger(__name__)


class AstronomyService:
    """Astronomy-related operations exposed to routes."""

    def __init__(
        self,
        fits_files: FitsFileRepository,
        analyses: AnalysisRepository,
        reports: ReportRepository,
        factory: DefaultAgentFactory,
        recorder: AgentRunRecorder,
        storage_root: Path,
        llm: LLMClient | None = None,
    ) -> None:
        self.fits_files = fits_files
        self.analyses = analyses
        self.reports = reports
        self.factory = factory
        self.recorder = recorder
        self.storage_root = storage_root
        # Indirect astropy access; tool is stateless.
        self._fits_reader = FitsReaderTool(storage_root=storage_root)
        # Optional: tests without LLM skip the FITS LLM fallback (header
        # rule still runs; LLM only fires on no-signal headers).
        self._llm = llm

    async def upload_fits(
        self,
        owner_id: uuid.UUID,
        *,
        filename: str,
        content: bytes,
    ) -> FitsUploadResponse:
        """Persist a FITS file and parse headers plus per-HDU summary inline."""
        ext = safe_extension(
            filename,
            allowed=_ALLOWED_FITS_EXTENSIONS,
            default=_REJECT_SENTINEL_EXTENSION,
        )
        if ext == _REJECT_SENTINEL_EXTENSION:
            raise ValidationError(
                message=(
                    f"Unsupported FITS extension for {filename!r}; allowed: "
                    f"{sorted(_ALLOWED_FITS_EXTENSIONS)}"
                ),
                code="unsupported_fits_type",
            )

        file_id = uuid.uuid4()
        storage_path = f"fits/{file_id}{_CANONICAL_FITS_EXTENSION}"
        disk_target = self.storage_root / storage_path
        write_bytes(disk_target, content)

        hdu_count, primary_headers, hdus = await self._summarise_fits(file_id)

        # Drives FitsAnalystAgent's analysis-type decision + prompt header block.
        header_summary = extract_header_summary(
            primary_headers,
            hdu_shapes=[h.shape for h in hdus],
        )

        # Astronomy-relevance gate: header rule cards primary, LLM fallback
        # only on mute headers. Reject before any DB row is created so the
        # file is the only artefact to clean up.
        if self._llm is not None:
            is_astro, reason = await check_fits_relevance_with_llm(
                self._llm, filename, header_summary
            )
            if not is_astro:
                try:
                    disk_target.unlink(missing_ok=True)
                except OSError:
                    _logger.warning(
                        "astronomy.fits_reject_cleanup_failed",
                        file_id=str(file_id),
                        storage_path=storage_path,
                    )
                raise ValidationError(
                    message=(
                        "This FITS file does not appear to be from "
                        "astronomy. AstroLearn only supports astronomy "
                        "FITS data."
                    ),
                    code="not_astronomy_content_fits",
                    details={"reason": reason},
                )

        row = await self.fits_files.create(
            {
                "id": file_id,
                "owner_id": owner_id,
                "filename": filename,
                "content_type": "application/fits",
                "size_bytes": len(content),
                "storage_path": storage_path,
                "hdu_count": hdu_count,
                "hdus": [h.model_dump() for h in hdus],
                "primary_headers": primary_headers,
                "header_summary": header_summary,
                "status": "parsed",
            }
        )

        ingest_fits.delay(str(file_id), filename)

        return FitsUploadResponse(
            file_id=row.id,
            filename=row.filename,
            size_bytes=row.size_bytes,
            hdu_count=hdu_count,
            hdus=hdus,
            primary_headers=primary_headers,
            header_summary=header_summary,
        )

    async def _summarise_fits(
        self,
        file_id: uuid.UUID,
    ) -> tuple[int, dict[str, Any], list[FitsHduSummary]]:
        """Walk HDUs; return count, primary headers, per-HDU summaries."""
        primary = await self._fits_reader.execute(
            file_id=file_id,
            hdu_index=0,
            include_headers=True,
            include_data_summary=False,
            include_data_array=False,
        )
        hdu_count = int(primary["hdu_count"])
        primary_headers = _flatten_headers(primary.get("headers", []))

        hdus: list[FitsHduSummary] = [
            FitsHduSummary(
                index=0,
                name=primary.get("name"),
                type=str(primary.get("hdu_type", "")),
                shape=primary.get("shape"),
                n_keywords=int(primary.get("n_keywords", 0)),
            )
        ]
        for idx in range(1, hdu_count):
            info = await self._fits_reader.execute(
                file_id=file_id,
                hdu_index=idx,
                include_headers=False,
                include_data_summary=False,
                include_data_array=False,
            )
            hdus.append(
                FitsHduSummary(
                    index=idx,
                    name=info.get("name"),
                    type=str(info.get("hdu_type", "")),
                    shape=info.get("shape"),
                    n_keywords=int(info.get("n_keywords", 0)),
                )
            )
        return hdu_count, primary_headers, hdus

    async def analyze(
        self,
        owner_id: uuid.UUID,
        request: AnalyzeRequest,
    ) -> AnalyzeResponse:
        """Cheap types run inline; heavy types enqueue and return pending row."""
        response, _ = await self.analyze_with_result(owner_id, request)
        return response

    async def analyze_with_result(
        self,
        owner_id: uuid.UUID,
        request: AnalyzeRequest,
    ) -> tuple[AnalyzeResponse, Any]:
        """Variant of analyze that also returns Celery AsyncResult (None inline)."""
        await self._load_owned_fits(request.file_id, owner_id)

        analysis = await self.analyses.create(
            {
                "owner_id": owner_id,
                "file_id": request.file_id,
                "analysis_type": request.analysis_type,
                "hdu_index": request.hdu_index,
                "params": request.params,
                "status": "pending",
            }
        )

        if request.analysis_type == "image_stats":
            return await self._run_image_stats_inline(analysis, request), None

        if request.analysis_type in _HEAVY_ANALYSIS_TYPES:
            async_result = run_analysis.delay(
                str(analysis.id),
                str(request.file_id),
                request.analysis_type,
                request.params,
            )
            return _analysis_to_response(analysis), async_result

        raise ValidationError(
            message=f"Unknown analysis_type: {request.analysis_type!r}",
            code="unknown_analysis_type",
        )

    async def _run_image_stats_inline(
        self,
        analysis: AnalysisModel,
        request: AnalyzeRequest,
    ) -> AnalyzeResponse:
        """Compute summary stats via FitsReaderTool inline."""
        try:
            tool_result = await self._fits_reader.execute(
                file_id=request.file_id,
                hdu_index=request.hdu_index,
                include_headers=False,
                include_data_summary=True,
                include_data_array=False,
            )
            results = dict(tool_result.get("data_summary", {}))
            updated = await self.analyses.set_terminal(
                analysis.id,
                "succeeded",
                results=results,
                artifacts=[],
                finished_at=datetime.now(UTC),
            )
            assert updated is not None
            return _analysis_to_response(updated)
        except Exception as exc:
            await self.analyses.set_terminal(
                analysis.id,
                "failed",
                error=str(exc),
                finished_at=datetime.now(UTC),
            )
            raise

    async def get_analysis(
        self,
        analysis_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> AnalyzeResponse:
        """Polling endpoint for queued analyses, owner-scoped."""
        row = await self._load_owned_analysis(analysis_id, owner_id)
        return _analysis_to_response(row)

    async def list_analyses(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[AnalyzeResponse]:
        """Return the owner's analyses, newest first."""
        rows = await self.analyses.list_for_owner(owner_id, limit=limit)
        return [_analysis_to_response(row) for row in rows]

    async def list_fits_files(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[FitsUploadResponse]:
        """Return the owner's FITS files (newest first); FE uses to reconcile MRU."""
        rows = await self.fits_files.list_for_owner(owner_id, limit=limit)
        return [
            FitsUploadResponse(
                file_id=row.id,
                filename=row.filename,
                size_bytes=row.size_bytes,
                hdu_count=row.hdu_count,
                hdus=[FitsHduSummary(**h) for h in (row.hdus or [])],
                primary_headers=dict(row.primary_headers or {}),
                header_summary=dict(row.header_summary) if row.header_summary else None,
            )
            for row in rows
        ]

    async def delete_fits_file(
        self,
        owner_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> None:
        """Delete owned FITS row + disk content + artefacts (analyses/reports cascade)."""
        row = await self._load_owned_fits(file_id, owner_id)
        storage_path = row.storage_path

        # Drop DB row first so a failed unlink can't leave a phantom row.
        deleted = await self.fits_files.delete(row.id)
        if not deleted:                                # pragma: no cover — race
            return

        # Disk cleanup is best-effort; DB is source of truth.
        fits_path = self.storage_root / storage_path
        try:
            fits_path.unlink(missing_ok=True)
        except OSError as exc:
            _logger.warning(
                "delete_fits_file.unlink_failed",
                file_id=str(file_id), path=str(fits_path), error=str(exc),
            )

        artifacts_path = self.storage_root / "fits_artifacts" / str(file_id)
        if artifacts_path.exists():
            try:
                shutil.rmtree(artifacts_path)
            except OSError as exc:
                _logger.warning(
                    "delete_fits_file.rmtree_failed",
                    file_id=str(file_id), path=str(artifacts_path), error=str(exc),
                )

    async def search_catalog(
        self,
        owner_id: uuid.UUID,
        request: CatalogSearchRequest,
    ) -> CatalogSearchResponse:
        """Delegate to the catalog agent and normalise its output."""
        agent = self.factory("catalog")
        task = request.model_dump()

        async with self.recorder.run(
            user_id=owner_id,
            session_id=None,
            agent_name="catalog",
            task=task,
        ) as handle:
            state = AgentState(
                run_id=handle.run_id,
                agent_name="catalog",
                user_id=owner_id,
            )
            terminal_state = await agent.run(task, state=state)
            output = terminal_state.final_output or {}
            handle.set_output(output)

        results_raw = output.get("results", []) or []
        return CatalogSearchResponse(
            query=request.query,
            source=request.source,
            results=[CatalogObject(**item) for item in results_raw],
        )

    async def generate_report(
        self,
        owner_id: uuid.UUID,
        request: ReportRequest,
    ) -> ReportResponse:
        """Render markdown / html / pdf report from a succeeded analysis."""
        analysis = await self._load_owned_analysis(request.analysis_id, owner_id)
        if analysis.status != "succeeded":
            raise ValidationError(
                message=(
                    f"Cannot generate a report from analysis in status "
                    f"{analysis.status!r}; wait for it to succeed."
                ),
                code="analysis_not_succeeded",
            )

        title = request.title or f"Analysis {analysis.id} ({analysis.analysis_type})"
        markdown_body = _render_markdown_report(
            title=title,
            analysis=analysis,
            include_plots=request.include_plots,
        )

        if request.format == "markdown":
            content_bytes = markdown_body.encode("utf-8")
        elif request.format == "html":
            content_bytes = _markdown_to_html(markdown_body, title=title).encode("utf-8")
        elif request.format == "pdf":
            content_bytes = _markdown_to_pdf(markdown_body, title=title)
        else:
            raise ValidationError(
                message=f"Unsupported report format: {request.format!r}",
                code="unsupported_report_format",
            )

        report_id = uuid.uuid4()
        ext = _REPORT_EXTENSIONS[request.format]
        storage_path = f"reports/{report_id}{ext}"
        write_bytes(self.storage_root / storage_path, content_bytes)

        generated_at = datetime.now(UTC)
        report = await self.reports.create(
            {
                "id": report_id,
                "owner_id": owner_id,
                "analysis_id": analysis.id,
                "title": title,
                "format": request.format,
                "storage_path": storage_path,
                "include_plots": request.include_plots,
                "generated_at": generated_at,
            }
        )

        return ReportResponse(
            report_id=report.id,
            title=report.title,
            format=report.format,  # type: ignore[arg-type]
            url=f"/api/v1/astronomy/reports/{report.id}/download",
            generated_at=report.generated_at,
        )

    async def get_fits_artifact(
        self,
        file_id: uuid.UUID,
        filename: str,
        owner_id: uuid.UUID,
    ) -> Path:
        """Owner-scoped resolver for derived FITS artifacts."""
        # Reject non-basename input to block path traversal.
        if not filename or filename != Path(filename).name or filename.startswith("."):
            raise ValidationError(
                message="Invalid artifact filename",
                code="invalid_artifact_filename",
            )

        await self._load_owned_fits(file_id, owner_id)

        absolute = self.storage_root / "fits_artifacts" / str(file_id) / filename
        if not absolute.exists() or not absolute.is_file():
            raise NotFoundError(
                message="Artifact not found",
                code="artifact_not_found",
            )
        return absolute

    async def get_report_for_download(
        self,
        report_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> tuple[Path, ReportModel]:
        """Owner-scoped fetch returning the absolute file path and report row."""
        report = await self.reports.get(report_id)
        if report is None:
            raise NotFoundError(
                message="Report not found",
                code="report_not_found",
            )
        if report.owner_id != owner_id:
            raise AuthorizationError(
                message="Report belongs to another user",
                code="forbidden",
            )
        absolute = self.storage_root / report.storage_path
        if not absolute.exists():
            raise NotFoundError(
                message=f"Report file missing on disk: {absolute}",
                code="report_file_missing",
            )
        return absolute, report

    async def _load_owned_fits(
        self,
        file_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> FitsFileModel:
        row = await self.fits_files.get(file_id)
        if row is None:
            raise NotFoundError(
                message="FITS file not found",
                code="fits_not_found",
            )
        if row.owner_id != owner_id:
            raise AuthorizationError(
                message="FITS file belongs to another user",
                code="forbidden",
            )
        return row

    async def _load_owned_analysis(
        self,
        analysis_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> AnalysisModel:
        row = await self.analyses.get(analysis_id)
        if row is None:
            raise NotFoundError(
                message="Analysis not found",
                code="analysis_not_found",
            )
        if row.owner_id != owner_id:
            raise AuthorizationError(
                message="Analysis belongs to another user",
                code="forbidden",
            )
        return row


def _flatten_headers(header_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten header cards to {keyword: value}; repeating cards collapse last-write-wins."""
    out: dict[str, Any] = {}
    for card in header_cards:
        keyword = card.get("keyword")
        if keyword:
            out[str(keyword)] = card.get("value")
    return out


def _analysis_to_response(row: AnalysisModel) -> AnalyzeResponse:
    # Surface status in results payload so client polls a single field.
    if row.status in {"pending", "running"} and not row.results:
        results: dict[str, Any] = {"status": row.status}
    elif row.status == "failed":
        results = {"status": "failed", "error": row.error or "unknown error"}
    else:
        results = dict(row.results or {})

    return AnalyzeResponse(
        analysis_id=row.id,
        file_id=row.file_id,
        analysis_type=row.analysis_type,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        results=results,
        artifacts=list(row.artifacts or []),
        interpretation=row.interpretation,
        generated_at=row.finished_at or row.updated_at,
    )


def _render_markdown_report(
    *,
    title: str,
    analysis: AnalysisModel,
    include_plots: bool,
) -> str:
    """Plain-string markdown renderer; prefers FitsAnalystAgent interpretation."""
    sections: list[str] = []

    sections.append(f"# {title}")
    sections.append("")
    sections.append(_render_run_metadata_md(analysis))

    interpretation = analysis.interpretation
    if _looks_like_fits_interpretation(interpretation):
        sections.append(_render_interpretation_md(interpretation))
    else:
        sections.append(_render_raw_results_md(analysis))

    if include_plots and analysis.artifacts:
        sections.append("## Artifacts")
        sections.append("")
        for artifact in analysis.artifacts:
            sections.append(f"- `{artifact}`")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def _looks_like_fits_interpretation(payload: Any) -> bool:
    """Cheap structural check; strict validation happens at write time."""
    if not isinstance(payload, dict):
        return False
    return (
        isinstance(payload.get("context"), dict)
        and isinstance(payload.get("decision"), dict)
        and isinstance(payload.get("results"), list)
    )


def _render_run_metadata_md(analysis: AnalysisModel) -> str:
    """Top metadata table common to every report."""
    generated_at = analysis.finished_at or analysis.created_at
    rows = [
        ("Analysis ID", str(analysis.id)),
        ("File ID", str(analysis.file_id)),
        ("Analysis Type", str(analysis.analysis_type)),
        ("Status", str(analysis.status)),
        ("HDU Index", str(analysis.hdu_index)),
        ("Generated", str(generated_at)),
    ]
    lines = ["| Field | Value |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| **{label}** | {_md_inline_escape(value)} |")
    lines.append("")
    return "\n".join(lines)


def _render_interpretation_md(interpretation: dict[str, Any]) -> str:
    """Render validated FitsInterpretation as markdown sections."""
    context = interpretation.get("context") or {}
    decision = interpretation.get("decision") or {}
    results = interpretation.get("results") or []
    next_steps = interpretation.get("next_steps") or []

    parts: list[str] = []

    parts.append("## File Context")
    parts.append("")
    ctx_rows = [
        ("Filename", context.get("filename") or "—"),
        ("Image Type", context.get("image_type") or "—"),
        ("Dimensions", context.get("dimensions") or "—"),
        ("Instrument", context.get("instrument") or "—"),
        ("Filter", context.get("filter") or "—"),
    ]
    parts.append("| Field | Value |")
    parts.append("| --- | --- |")
    for label, value in ctx_rows:
        parts.append(f"| **{label}** | {_md_inline_escape(str(value))} |")
    parts.append("")

    parts.append("## Analysis Plan")
    parts.append("")
    types = decision.get("analysis_types") or []
    if isinstance(types, list) and types:
        parts.append("**Analyses run:** " + ", ".join(f"`{t}`" for t in types))
        parts.append("")
    reasoning = decision.get("reasoning")
    if reasoning:
        parts.append(str(reasoning))
        parts.append("")

    if isinstance(results, list) and results:
        parts.append("## Findings")
        parts.append("")
        for idx, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                continue
            rtype = result.get("type") or f"result {idx}"
            headline = result.get("headline") or ""
            interp = result.get("interpretation") or ""
            metrics = result.get("metrics") or []
            anomalies = result.get("anomalies") or []

            parts.append(f"### {idx}. {rtype.replace('_', ' ').title()}")
            parts.append("")
            if headline:
                parts.append(f"> {headline}")
                parts.append("")

            if isinstance(metrics, list) and metrics:
                parts.append("| Metric | Value | What it means |")
                parts.append("| --- | --- | --- |")
                for metric in metrics:
                    if not isinstance(metric, dict):
                        continue
                    label = _md_inline_escape(str(metric.get("label") or "—"))
                    value = _md_inline_escape(str(metric.get("value") or "—"))
                    meaning = _md_inline_escape(
                        str(metric.get("interpretation") or "—")
                    )
                    parts.append(f"| {label} | {value} | {meaning} |")
                parts.append("")

            if interp:
                parts.append(str(interp))
                parts.append("")

            if isinstance(anomalies, list) and anomalies:
                parts.append("**Anomalies flagged:**")
                parts.append("")
                for a in anomalies:
                    parts.append(f"- {a}")
                parts.append("")

    if isinstance(next_steps, list) and next_steps:
        parts.append("## Suggested Next Steps")
        parts.append("")
        for step in next_steps:
            parts.append(f"- {step}")
        parts.append("")

    return "\n".join(parts)


def _render_raw_results_md(analysis: AnalysisModel) -> str:
    """Fallback for legacy analyses with no interpretation column."""
    parts = ["## Raw Results", ""]
    if analysis.status == "failed":
        parts.append(
            f"> Analysis failed: {analysis.error or 'no error message recorded'}."
        )
        parts.append("")
        return "\n".join(parts)
    if not analysis.results:
        parts.append("> No results recorded for this analysis.")
        parts.append("")
        return "\n".join(parts)
    parts.append("```json")
    parts.append(json.dumps(analysis.results, indent=2, default=str))
    parts.append("```")
    parts.append("")
    return "\n".join(parts)


# Escape `|` for table cells; escape `\\` first to avoid double-escape.
def _md_inline_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _markdown_to_html(markdown_body: str, *, title: str) -> str:
    """Render markdown as a self-contained HTML document with inline styles."""
    # Typed error so HTTP layer returns 422 instead of 500.
    try:
        import markdown as md
    except ImportError as exc:
        raise ValidationError(
            message="HTML report format requires the 'markdown' package",
            code="unsupported_report_format",
        ) from exc

    body_html = md.markdown(markdown_body, extensions=["fenced_code", "tables"])
    safe_title = html_escape(title)
    return (
        "<!doctype html><html lang='en'><head>"
        "<meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        f"<style>{_REPORT_CSS}</style>"
        "</head><body>"
        f"<main class='report'>{body_html}</main>"
        "</body></html>"
    )


# Inline stylesheet; weasyprint reuses via _markdown_to_html for PDF.
_REPORT_CSS: str = """
  body { margin: 0; background: #fafafa; color: #1f2329;
         font-family: 'Georgia', 'Times New Roman', serif;
         font-size: 11pt; line-height: 1.55; }
  main.report { max-width: 800px; margin: 0 auto; padding: 32px 40px;
                background: #ffffff; }
  h1, h2, h3 { font-family: 'Helvetica Neue', Arial, sans-serif;
               color: #0a2540; line-height: 1.25; }
  h1 { font-size: 22pt; margin: 0 0 8px; padding-bottom: 6px;
       border-bottom: 2px solid #0a2540; }
  h2 { font-size: 15pt; margin: 28px 0 10px; }
  h3 { font-size: 12pt; margin: 20px 0 6px; color: #1f3a5f; }
  p { margin: 0 0 12px; }
  blockquote { margin: 8px 0 16px; padding: 8px 14px;
               border-left: 4px solid #c2a661; background: #fbf6e8;
               color: #3a3a3a; }
  table { border-collapse: collapse; width: 100%; margin: 6px 0 18px;
          font-size: 10.5pt; }
  th, td { border: 1px solid #d6d8dd; padding: 6px 10px;
           text-align: left; vertical-align: top; }
  th { background: #f0f3f7; font-weight: 600;
       font-family: 'Helvetica Neue', Arial, sans-serif; }
  code { font-family: 'Consolas', 'Monaco', monospace;
         background: #f3f4f6; padding: 1px 5px; border-radius: 3px;
         font-size: 10pt; }
  pre code { display: block; padding: 10px 14px; background: #1f2329;
             color: #f0f0f0; border-radius: 4px; overflow-x: auto; }
  ul, ol { margin: 0 0 14px; padding-left: 22px; }
  li { margin-bottom: 4px; }
  strong { color: #0a2540; }
"""


def _markdown_to_pdf(markdown_body: str, *, title: str) -> bytes:
    """Render markdown as a PDF via weasyprint."""
    try:
        import weasyprint
    except ImportError as exc:
        raise ValidationError(
            message="PDF report format requires the 'weasyprint' package",
            code="unsupported_report_format",
        ) from exc

    html = _markdown_to_html(markdown_body, title=title)
    return weasyprint.HTML(string=html).write_pdf()
