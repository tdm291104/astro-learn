"""Background notebook tasks: indexing and study-pack generation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from core.db import task_session_factory
from core.exceptions import NotFoundError, ValidationError
from memory.long_term.vector_store import VectorChunk
from repositories.agent_repository import AgentRepository
from repositories.document_repository import DocumentRepository
from tools.knowledge.text_splitter import RecursiveCharacterSplitter
from workers._deps import (
    get_worker_agent_factory,
    get_worker_pdf_parser,
    get_worker_storage_root,
    get_worker_vector_store,
)
from workers.celery_app import celery_app
from workflows.learning_workflow import LearningWorkflow
from workflows.notebook_workflow import NotebookWorkflow

_logger = structlog.get_logger(__name__)


# Recursive splitter with hyperparams chosen by the chunker hyperparam sweep
# against arxiv_curated_v1 (30 hand-curated questions over 6 astronomy papers).
# Smaller chunks (500) won across hit@1, hit@10, MRR vs 750/1000/1500 sizes —
# numeric/factual queries benefit from tighter chunks with less surrounding
# noise. See benchmarks/rag_retrieval_eval_results/comparison.md for the full ablation.
_CHUNK_SIZE: int = 500
_CHUNK_OVERLAP: int = 250
_SPLITTER = RecursiveCharacterSplitter(size=_CHUNK_SIZE, overlap=_CHUNK_OVERLAP)

_PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})
_TEXT_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md"})


@celery_app.task(name="workers.notebook.index_document", bind=True, max_retries=3)
def index_document(
    self: Any,                           # noqa: ANN401 — Celery's `bind=True` self
    document_id: str,
    notebook_id: str,
    filename: str,
) -> dict[str, Any]:
    """Index one uploaded document and return a summary."""
    return asyncio.run(
        _async_index_document(
            document_id=uuid.UUID(document_id),
            notebook_id=uuid.UUID(notebook_id),
            filename=filename,
        )
    )


@celery_app.task(name="workers.notebook.generate_learning_pack", bind=True, max_retries=2)
def generate_learning_pack(
    self: Any,                           # noqa: ANN401 — Celery's `bind=True` self
    run_id: str,
    document_id: str,
    notebook_id: str,
    n_questions: int,
    n_cards: int,
) -> dict[str, Any]:
    """Run per-document LearningWorkflow asynchronously."""
    # max_retries=2: single-doc workflow is cheap enough to retry transient hiccups.
    return asyncio.run(
        _async_generate_learning_pack(
            run_id=uuid.UUID(run_id),
            document_id=uuid.UUID(document_id),
            notebook_id=uuid.UUID(notebook_id),
            n_questions=n_questions,
            n_cards=n_cards,
        )
    )


@celery_app.task(name="workers.notebook.generate_study_pack", bind=True, max_retries=0)
def generate_study_pack(
    self: Any,                           # noqa: ANN401 — Celery's `bind=True` self
    run_id: str,
    notebook_id: str,
    max_bullets: int,
    n_questions: int,
    n_cards: int,
) -> dict[str, Any]:
    """Run full notebook workflow asynchronously."""
    # max_retries=0: surface failures to UI instead of silent costly retries.
    return asyncio.run(
        _async_generate_study_pack(
            run_id=uuid.UUID(run_id),
            notebook_id=uuid.UUID(notebook_id),
            max_bullets=max_bullets,
            n_questions=n_questions,
            n_cards=n_cards,
        )
    )


async def _async_index_document(
    *,
    document_id: uuid.UUID,
    notebook_id: uuid.UUID,
    filename: str,
) -> dict[str, Any]:
    """Parse, chunk, embed, upsert one document."""
    # Short-lived sessions so polling readers see status updates immediately.
    storage_root = get_worker_storage_root()
    vector_store = get_worker_vector_store()
    pdf_parser = get_worker_pdf_parser()

    async with task_session_factory() as sf:
        storage_path = await _begin_indexing(sf, document_id)

        try:
            full_text, page_offsets, parser_metadata = await _parse_document(
                storage_root=storage_root,
                storage_path=storage_path,
                document_id=document_id,
                pdf_parser=pdf_parser,
            )

            chunks = _build_chunks(
                full_text=full_text,
                page_offsets=page_offsets,
                document_id=document_id,
            )

            indexed_count = await vector_store.index(chunks, notebook_id=notebook_id)

            await _finish_indexed(
                sf,
                document_id,
                indexed_chunks=indexed_count,
                parser_metadata=parser_metadata,
            )

            _logger.info(
                "document.indexed",
                document_id=str(document_id),
                notebook_id=str(notebook_id),
                chunk_count=indexed_count,
            )
            return {
                "document_id": str(document_id),
                "indexed_chunks": indexed_count,
                "status": "indexed",
            }

        except Exception as exc:
            # Re-raise so Celery retry kicks in.
            await _mark_failed(sf, document_id, error=str(exc))
            _logger.exception(
                "document.index_failed",
                document_id=str(document_id),
                error=str(exc),
            )
            raise


async def _begin_indexing(
    session_factory: Any,
    document_id: uuid.UUID,
) -> str:
    """Flip queued → indexing; return storage_path."""
    async with session_factory() as session:
        repo = DocumentRepository(session)
        document = await repo.get(document_id)
        if document is None:
            raise NotFoundError(
                message=f"Document {document_id} not found",
                code="document_not_found",
            )
        await repo.set_status(document_id, "indexing")
        await session.commit()
        return document.storage_path


async def _finish_indexed(
    session_factory: Any,
    document_id: uuid.UUID,
    *,
    indexed_chunks: int,
    parser_metadata: dict[str, Any] | None,
) -> None:
    """Flip indexing → indexed; record chunk count + parser metadata."""
    async with session_factory() as session:
        repo = DocumentRepository(session)
        await repo.set_status(document_id, "indexed", indexed_chunks=indexed_chunks)
        if parser_metadata:
            await repo.update(document_id, {"extra": parser_metadata})
        await session.commit()


async def _mark_failed(
    session_factory: Any,
    document_id: uuid.UUID,
    *,
    error: str,
) -> None:
    """Best-effort terminal failure write; never raises."""
    try:
        async with session_factory() as session:
            repo = DocumentRepository(session)
            await repo.set_status(document_id, "failed", error=error)
            await session.commit()
    except Exception:
        _logger.exception(
            "document.failed_mark_failed",
            document_id=str(document_id),
        )


async def _parse_document(
    *,
    storage_root: Path,
    storage_path: str,
    document_id: uuid.UUID,
    pdf_parser: Any,
) -> tuple[str, list[tuple[int, int]], dict[str, Any] | None]:
    """Parse file at storage_root/storage_path."""
    target = storage_root / storage_path
    if not target.exists():
        raise NotFoundError(
            message=f"Document file missing on disk: {target}",
            code="document_file_missing",
        )

    ext = Path(storage_path).suffix.lower()

    if ext in _PDF_EXTENSIONS:
        result = await pdf_parser.execute(file_id=document_id)
        page_offsets = [(page.page_number, page.char_offset) for page in result.pages]
        metadata: dict[str, Any] = dict(result.metadata)
        metadata["page_count"] = result.page_count
        return result.full_text, page_offsets, metadata

    if ext in _TEXT_EXTENSIONS:
        # errors="replace" tolerates non-UTF-8 bytes.
        text = target.read_text(encoding="utf-8", errors="replace")
        return text, [], None

    raise ValidationError(
        message=f"Unsupported document type: {ext or '<no extension>'}",
        code="unsupported_document_type",
    )


def _build_chunks(
    *,
    full_text: str,
    page_offsets: list[tuple[int, int]],
    document_id: uuid.UUID,
) -> list[VectorChunk]:
    """Recursive split full_text into ~size chunks tagged with their page.

    Picked over char-window after a head-to-head on 16 astronomy
    questions: same recall@k but cleaner text (never cuts mid-word).
    """
    pieces = _SPLITTER.split_with_positions(full_text)
    chunks: list[VectorChunk] = []
    for index, (text, offset) in enumerate(pieces):
        metadata: dict[str, Any] = {"char_offset": offset}
        page = _page_for_offset(offset, page_offsets)
        if page is not None:
            metadata["page"] = page
        chunks.append(
            VectorChunk(
                chunk_id=f"{document_id}:{index}",
                document_id=document_id,
                text=text,
                metadata=metadata,
            )
        )
    return chunks


# Checked before transitions to preserve out-of-band cancellations.
_STUDY_PACK_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled"}
)


_LEARNING_STEP_LABELS: dict[str, str] = {
    "summarize": "Summarized document",
    "quiz": "Generated quiz",
    "flashcards": "Generated flashcards",
}


async def _async_generate_learning_pack(
    *,
    run_id: uuid.UUID,
    document_id: uuid.UUID,
    notebook_id: uuid.UUID,
    n_questions: int,
    n_cards: int,
) -> dict[str, Any]:
    """Drive LearningWorkflow; mirror progress onto agent_runs."""
    async with task_session_factory() as sf:
        if not await _mark_run_running(sf, run_id):
            _logger.info("learning_pack.skipped", run_id=str(run_id))
            return {"status": "skipped", "run_id": str(run_id)}

        async def _on_step(step_name: str, index: int, total: int) -> None:
            fraction = (index + 1) / total if total > 0 else None
            await _write_study_pack_progress(
                sf,
                run_id,
                step_count=index + 1,
                current_step=_LEARNING_STEP_LABELS.get(step_name, step_name),
                progress=fraction,
            )

        workflow = LearningWorkflow(
            agent_factory=get_worker_agent_factory(),
            on_step_complete=_on_step,
        )

        try:
            workflow_state = await workflow.run(
                {
                    "notebook_id": notebook_id,
                    "document_id": document_id,
                    "n_questions": n_questions,
                    "n_cards": n_cards,
                }
            )
            output = workflow_state.final_output or {}
            await _mark_run_terminal(sf, run_id, "succeeded", output=output)
            _logger.info(
                "learning_pack.succeeded",
                run_id=str(run_id),
                notebook_id=str(notebook_id),
                document_id=str(document_id),
            )
            return {"status": "succeeded", "run_id": str(run_id)}

        except Exception as exc:
            await _mark_run_terminal(sf, run_id, "failed", error=str(exc))
            _logger.exception(
                "learning_pack.failed",
                run_id=str(run_id),
                document_id=str(document_id),
                error=str(exc),
            )
            # Retry-safe: _mark_run_running short-circuits on terminal status.
            raise


async def _async_generate_study_pack(
    *,
    run_id: uuid.UUID,
    notebook_id: uuid.UUID,
    max_bullets: int,
    n_questions: int,
    n_cards: int,
) -> dict[str, Any]:
    """Drive NotebookWorkflow; mirror progress onto agent_runs."""
    async with task_session_factory() as sf:
        if not await _mark_run_running(sf, run_id):
            _logger.info("study_pack.skipped", run_id=str(run_id))
            return {"status": "skipped", "run_id": str(run_id)}

        async def _on_step(step_name: str, index: int, total: int) -> None:
            fraction = (index + 1) / total if total > 0 else None
            await _write_study_pack_progress(
                sf,
                run_id,
                step_count=index + 1,
                current_step=_humanise_stage(step_name),
                progress=fraction,
            )

        workflow = NotebookWorkflow(
            agent_factory=get_worker_agent_factory(),
            on_step_complete=_on_step,
        )

        try:
            workflow_state = await workflow.run(
                {
                    "notebook_id": notebook_id,
                    "max_bullets": max_bullets,
                    "n_questions": n_questions,
                    "n_cards": n_cards,
                }
            )
            output = workflow_state.final_output or {}
            await _mark_run_terminal(sf, run_id, "succeeded", output=output)
            _logger.info(
                "study_pack.succeeded",
                run_id=str(run_id),
                notebook_id=str(notebook_id),
            )
            return {"status": "succeeded", "run_id": str(run_id)}

        except Exception as exc:
            await _mark_run_terminal(sf, run_id, "failed", error=str(exc))
            _logger.exception(
                "study_pack.failed",
                run_id=str(run_id),
                error=str(exc),
            )
            # Authoritative status is agent_runs.status; not re-raising avoids log noise.
            return {"status": "failed", "run_id": str(run_id)}


async def _write_study_pack_progress(
    session_factory: Any,
    run_id: uuid.UUID,
    *,
    step_count: int,
    current_step: str,
    progress: float | None,
) -> None:
    """Mirror stage progress onto agent_runs."""
    try:
        async with session_factory() as session:
            await AgentRepository(session).update_progress(
                run_id,
                step_count=step_count,
                current_step=current_step,
                progress=progress,
            )
            await session.commit()
    except Exception:
        _logger.exception(
            "study_pack.progress_write_failed",
            run_id=str(run_id),
            step_count=step_count,
        )


_NOTEBOOK_STEP_LABELS: dict[str, str] = {
    "summarize": "Summarized documents",
    "quiz_and_flashcards": "Generated quiz + flashcards",
    "validate_quiz": "Validated quiz",
}


def _humanise_stage(step_name: str) -> str:
    return _NOTEBOOK_STEP_LABELS.get(step_name, step_name)


async def _mark_run_running(
    session_factory: Any,
    run_id: uuid.UUID,
) -> bool:
    """Flip pending → running; False if missing or already terminal."""
    async with session_factory() as session:
        repo = AgentRepository(session)
        row = await repo.get(run_id)
        if row is None:
            return False
        if row.status in _STUDY_PACK_TERMINAL_STATUSES:
            return False
        await repo.set_status(
            run_id, "running", finished_at=None,
        )
        # set_status doesn't update started_at; do it explicitly.
        row = await repo.get(run_id)
        if row is not None:
            row.started_at = datetime.now(UTC)
        await session.commit()
        return True


async def _mark_run_terminal(
    session_factory: Any,
    run_id: uuid.UUID,
    status: str,
    *,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Write terminal status; preserves out-of-band cancellation."""
    async with session_factory() as session:
        repo = AgentRepository(session)
        current = await repo.get(run_id)
        if current is None or current.status in _STUDY_PACK_TERMINAL_STATUSES:
            return
        await repo.set_status(
            run_id,
            status,
            output=output,
            error=error,
            finished_at=datetime.now(UTC),
        )
        await session.commit()


def _page_for_offset(
    char_offset: int,
    page_offsets: list[tuple[int, int]],
) -> int | None:
    """Page whose offset is the largest <= char_offset (linear scan; offsets are sorted)."""
    if not page_offsets:
        return None
    selected: int | None = None
    for page_number, offset in page_offsets:
        if offset <= char_offset:
            selected = page_number
        else:
            break
    return selected
