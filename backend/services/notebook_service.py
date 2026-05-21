"""Notebook CRUD + NotebookLM features (Q&A, summarize, quiz, flashcards)."""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base.agent_state import AgentState
from core.agent_factory import DefaultAgentFactory
from core.exceptions import AuthorizationError, NotFoundError, ValidationError
from core.llm.llm_client import LLMClient
from core.storage import safe_extension, write_bytes
from memory.long_term.vector_store import VectorStore
from models.agent_model import AgentModel  # noqa: F401 — used in forward type ref
from repositories.agent_repository import AgentRepository
from repositories.document_repository import DocumentRepository
from repositories.message_repository import MessageRepository
from repositories.notebook_artifact_repository import NotebookArtifactRepository
from repositories.notebook_repository import NotebookRepository
from repositories.session_repository import SessionRepository
from schemas.agent_schema import AgentResponse
from schemas.notebook_schema import (
    Citation,
    DocumentContentResponse,
    DocumentPage,
    DocumentUploadResponse,
    Flashcard,
    FlashcardRequest,
    FlashcardResponse,
    LearningPackRequest,
    NotebookArtifactPayload,
    NotebookCreateRequest,
    NotebookResponse,
    NotebookShareResponse,
    NotebookUpdateRequest,
    QARequest,
    QAResponse,
    QuizItem,
    QuizRequest,
    QuizResponse,
    SharedDocument,
    SharedNotebookResponse,
    ShareSettingsResponse,
    ShareSettingsUpdateRequest,
    StudyPackRequest,
    SummarizeRequest,
    SummarizeResponse,
)
from services._agent_run_recorder import AgentRunRecorder
from services._astronomy_gate import check_document_relevance
from workers.notebook_worker import (
    generate_learning_pack,
    generate_study_pack,
    index_document,
)
from workflows.notebook_workflow import NotebookWorkflow

_logger = structlog.get_logger(__name__)

_QA_SESSION_TITLE_CHAR_CAP: int = 80

# Cap content viewer payload so a huge PDF doesn't OOM the browser.
_MAX_DOCUMENT_CONTENT_CHARS: int = 500_000

# Sample size handed to the astronomy-relevance gate.
_GATE_SAMPLE_CHAR_LIMIT: int = 3000


# `.bin` is safe_extension's sentinel for rejected types.
_ALLOWED_DOCUMENT_EXTENSIONS: set[str] = {".pdf", ".txt", ".md"}
_REJECT_SENTINEL_EXTENSION: str = ".bin"


def _extract_gate_sample(ext: str, content: bytes) -> str:
    """Pull up to _GATE_SAMPLE_CHAR_LIMIT chars from raw bytes for relevance check.

    Returns "" when extraction fails — caller treats empty as "fail-open"
    via the gate's own empty_sample policy.
    """
    if ext in {".txt", ".md"}:
        try:
            return content.decode("utf-8", errors="replace")[:_GATE_SAMPLE_CHAR_LIMIT]
        except Exception:  # noqa: BLE001 — best-effort sampling
            return ""
    if ext == ".pdf":
        try:
            # Lazy import: pypdf cold-import is ~50ms; avoid on hot paths.
            from io import BytesIO

            from pypdf import PdfReader
        except Exception:  # noqa: BLE001
            return ""
        try:
            reader = PdfReader(BytesIO(content))
        except Exception:  # noqa: BLE001 — corrupt PDF; caller will surface
            return ""
        parts: list[str] = []
        total = 0
        # Sample up to the first 5 pages; abstract + intro is enough signal.
        for page in reader.pages[:5]:
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — keep walking pages
                continue
            parts.append(text)
            total += len(text)
            if total >= _GATE_SAMPLE_CHAR_LIMIT:
                break
        return "\n".join(parts)[:_GATE_SAMPLE_CHAR_LIMIT]
    return ""


# Filenames hidden by default so a leaked link doesn't reveal content.
_DEFAULT_SHARE_SETTINGS: dict = {"show_filenames": False}


def _build_share_response(token: str) -> NotebookShareResponse:
    # Emit relative path so dev/staging/prod don't bake in a host.
    return NotebookShareResponse(
        share_token=token,
        share_path=f"/shared/{token}",
    )


class NotebookService:
    """Notebook-related operations exposed to routes."""

    def __init__(
        self,
        notebooks: NotebookRepository,
        documents: DocumentRepository,
        sessions: SessionRepository,
        messages: MessageRepository,
        factory: DefaultAgentFactory,
        recorder: AgentRunRecorder,
        storage_root: Path,
        session_factory: async_sessionmaker[AsyncSession],
        vector_store: VectorStore | None = None,
        artifacts: NotebookArtifactRepository | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.notebooks = notebooks
        self.documents = documents
        self.sessions = sessions
        self.messages = messages
        # Optional for legacy test constructors not exercising these flows.
        self.artifacts = artifacts
        self.factory = factory
        self.recorder = recorder
        self.storage_root = storage_root
        # Optional: CRUD-only tests skip the Qdrant double; delete() becomes a no-op.
        self.vector_store = vector_store
        # Independent-transaction commits so recorder (separate connection) sees FK targets.
        self._session_factory = session_factory
        self._notebook_workflow = NotebookWorkflow(agent_factory=factory)
        # Optional: tests without LLM stub skip the astronomy-relevance gate.
        self._llm = llm

    async def create(
        self,
        owner_id: uuid.UUID,
        request: NotebookCreateRequest,
    ) -> NotebookResponse:
        created = await self.notebooks.create(
            {
                "owner_id": owner_id,
                "title": request.title,
                "description": request.description,
            }
        )
        return NotebookResponse.model_validate(created)

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NotebookResponse]:
        rows = await self.notebooks.list_for_owner(
            owner_id, limit=limit, offset=offset
        )
        return [NotebookResponse.model_validate(r) for r in rows]

    async def get(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> NotebookResponse:
        row = await self._load_owned(notebook_id, owner_id)
        return NotebookResponse.model_validate(row)

    async def update(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: NotebookUpdateRequest,
    ) -> NotebookResponse:
        await self._load_owned(notebook_id, owner_id)
        updated = await self.notebooks.update(notebook_id, request)
        assert updated is not None
        return NotebookResponse.model_validate(updated)

    async def delete(self, notebook_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """Delete a notebook and its derived artefacts."""
        # Disk + Qdrant cleanup is best-effort; orphan file/vector preferable
        # to a half-deleted notebook still appearing in the UI.
        row = await self.notebooks.get(notebook_id)
        if row is None:
            return False
        if row.owner_id != owner_id:
            raise AuthorizationError(
                message="Notebook belongs to another user",
                code="forbidden",
            )

        # Collect docs before cascade wipes them so we still have storage_paths.
        documents = await self.documents.list_for_notebook(
            notebook_id, limit=10_000, offset=0,
        )
        for doc in documents:
            target = self.storage_root / doc.storage_path
            try:
                target.unlink(missing_ok=True)
            except OSError:
                _logger.exception(
                    "notebook.document_unlink_failed",
                    notebook_id=str(notebook_id),
                    document_id=str(doc.id),
                    storage_path=doc.storage_path,
                )

        if self.vector_store is not None:
            try:
                await self.vector_store.delete_notebook(notebook_id)
            except Exception:
                _logger.exception(
                    "notebook.vector_cleanup_failed",
                    notebook_id=str(notebook_id),
                )

        return await self.notebooks.delete(notebook_id)

    async def create_share_token(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> NotebookShareResponse:
        """Mint or return existing read-only share token for a notebook."""
        # Idempotent so re-opening the dialog yields the same link.
        notebook = await self._load_owned(notebook_id, owner_id)
        if notebook.share_token:
            return _build_share_response(notebook.share_token)

        # 192 bits of entropy; collisions on UNIQUE are negligible (2^96).
        token = secrets.token_urlsafe(24)
        updated = await self.notebooks.set_share_token(notebook_id, token)
        assert updated is not None and updated.share_token is not None
        return _build_share_response(updated.share_token)

    async def revoke_share_token(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> bool:
        """Revoke an existing share token (idempotent)."""
        notebook = await self._load_owned(notebook_id, owner_id)
        if not notebook.share_token:
            return False
        updated = await self.notebooks.clear_share_token(notebook_id)
        return updated is not None

    async def get_share_settings(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> ShareSettingsResponse:
        """Return the notebook's current share-visibility toggles."""
        notebook = await self._load_owned(notebook_id, owner_id)
        current = notebook.share_settings or _DEFAULT_SHARE_SETTINGS
        return ShareSettingsResponse(
            show_filenames=bool(current.get("show_filenames", False)),
        )

    async def update_share_settings(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: ShareSettingsUpdateRequest,
    ) -> ShareSettingsResponse:
        """Apply a partial update to the notebook's share-visibility toggles."""
        notebook = await self._load_owned(notebook_id, owner_id)
        current = dict(notebook.share_settings or _DEFAULT_SHARE_SETTINGS)
        updates = request.model_dump(exclude_unset=True)
        current.update(updates)
        notebook.share_settings = current
        await self.notebooks.session.flush()
        await self.notebooks.session.refresh(notebook)
        return ShareSettingsResponse(
            show_filenames=bool(current.get("show_filenames", False)),
        )

    async def get_shared(self, token: str) -> SharedNotebookResponse:
        """Public read-only view for a share_token (no auth — token is credential)."""
        # Single error for "never existed" and "revoked" to avoid oracle.
        notebook = await self.notebooks.get_by_share_token(token)
        if notebook is None:
            raise NotFoundError(
                message="Shared notebook not found",
                code="shared_notebook_not_found",
            )

        settings = notebook.share_settings or _DEFAULT_SHARE_SETTINGS
        show_filenames = bool(settings.get("show_filenames", False))

        documents = await self.documents.list_for_notebook(
            notebook.id, limit=200, offset=0,
        )
        return SharedNotebookResponse(
            title=notebook.title,
            description=notebook.description,
            created_at=notebook.created_at,
            updated_at=notebook.updated_at,
            document_count=len(documents),
            documents=[
                SharedDocument(
                    document_id=d.id,
                    filename=(
                        d.filename if show_filenames else f"Document {i + 1}"
                    ),
                    size_bytes=d.size_bytes,
                    indexed_chunks=d.indexed_chunks,
                )
                for i, d in enumerate(documents)
            ],
        )

    async def get_shared_document_file(
        self,
        token: str,
        document_id: uuid.UUID,
    ) -> tuple[Path, str, str | None]:
        """Resolve disk path for a shared document; filename respects show_filenames."""
        notebook = await self.notebooks.get_by_share_token(token)
        if notebook is None:
            raise NotFoundError(
                message="Shared notebook not found",
                code="shared_notebook_not_found",
            )
        doc = await self.documents.get(document_id)
        if doc is None or doc.notebook_id != notebook.id:
            raise NotFoundError(
                message="Document not found",
                code="document_not_found",
            )
        target = self.storage_root / doc.storage_path
        if not target.exists():
            raise NotFoundError(
                message="Document file missing on disk",
                code="document_file_missing",
            )

        # Honour share_settings.show_filenames in Content-Disposition too.
        settings = notebook.share_settings or _DEFAULT_SHARE_SETTINGS
        show_filenames = bool(settings.get("show_filenames", False))
        public_name = doc.filename if show_filenames else "document"
        return target, public_name, doc.content_type

    async def get_shared_artifact(
        self,
        token: str,
        kind: str,
    ) -> NotebookArtifactPayload | None:
        """Return cached artifact payload via share token, or None if absent."""
        notebook = await self.notebooks.get_by_share_token(token)
        if notebook is None:
            raise NotFoundError(
                message="Shared notebook not found",
                code="shared_notebook_not_found",
            )
        if self.artifacts is None:
            return None
        row = await self.artifacts.get_by_kind(notebook.id, kind)
        if row is None:
            return None
        return NotebookArtifactPayload(
            notebook_id=row.notebook_id,
            kind=row.kind,
            params=row.params,
            payload=row.payload,
            updated_at=row.updated_at,
        )

    async def _load_owned(
        self, notebook_id: uuid.UUID, owner_id: uuid.UUID
    ) -> NotebookModel:  # noqa: F821 — forward type hint for clarity
        """Load a notebook and assert ownership; raise the right domain error."""
        row = await self.notebooks.get(notebook_id)
        if row is None:
            raise NotFoundError(
                message="Notebook not found",
                code="notebook_not_found",
            )
        if row.owner_id != owner_id:
            raise AuthorizationError(
                message="Notebook belongs to another user",
                code="forbidden",
            )
        return row

    async def list_documents(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentUploadResponse]:
        await self._load_owned(notebook_id, owner_id)
        rows = await self.documents.list_for_notebook(
            notebook_id, limit=limit, offset=offset
        )
        # Build explicitly: response renames row `id` to `document_id`.
        return [
            DocumentUploadResponse(
                document_id=r.id,
                notebook_id=r.notebook_id,
                filename=r.filename,
                size_bytes=r.size_bytes,
                status=r.status,  # type: ignore[arg-type]
                indexed_chunks=r.indexed_chunks,
            )
            for r in rows
        ]

    async def delete_document(
        self,
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> bool:
        """Delete a single document from a notebook."""
        # Best-effort disk + Qdrant cleanup; cross-notebook returns NotFound to avoid enumeration.
        await self._load_owned(notebook_id, owner_id)
        doc = await self.documents.get(document_id)
        if doc is None:
            return False
        if doc.notebook_id != notebook_id:
            raise NotFoundError(
                message="Document not found",
                code="document_not_found",
            )

        target = self.storage_root / doc.storage_path
        try:
            target.unlink(missing_ok=True)
        except OSError:
            _logger.exception(
                "notebook.document_unlink_failed",
                notebook_id=str(notebook_id),
                document_id=str(document_id),
                storage_path=doc.storage_path,
            )

        if self.vector_store is not None:
            try:
                await self.vector_store.delete_document(document_id)
            except Exception:
                _logger.exception(
                    "notebook.document_vector_cleanup_failed",
                    notebook_id=str(notebook_id),
                    document_id=str(document_id),
                )

        return await self.documents.delete(document_id)

    async def get_document_content(
        self,
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> DocumentContentResponse:
        """Return extracted text for the document; PDFs are parsed per-page."""
        await self._load_owned(notebook_id, owner_id)
        doc = await self.documents.get(document_id)
        if doc is None or doc.notebook_id != notebook_id:
            raise NotFoundError(
                message="Document not found",
                code="document_not_found",
            )

        target = self.storage_root / doc.storage_path
        if not target.exists():
            raise NotFoundError(
                message="Document file missing on disk",
                code="document_file_missing",
            )

        ext = Path(doc.filename).suffix.lower()
        if ext == ".pdf":
            from tools.knowledge.pdf_parser_tool import PdfParserTool

            parser = PdfParserTool(storage_root=self.storage_root)
            parsed = await parser.execute(path=str(target))
            content = parsed.full_text
            truncated = len(content) > _MAX_DOCUMENT_CONTENT_CHARS
            if truncated:
                content = content[:_MAX_DOCUMENT_CONTENT_CHARS]
            return DocumentContentResponse(
                document_id=doc.id,
                notebook_id=doc.notebook_id,
                filename=doc.filename,
                content_type=doc.content_type,
                size_bytes=doc.size_bytes,
                content=content,
                truncated=truncated,
                pages=[
                    DocumentPage(
                        page_number=p.page_number,
                        text=p.text,
                        char_offset=p.char_offset,
                    )
                    for p in parsed.pages
                ],
                page_count=parsed.page_count,
            )

        # .txt / .md: read directly (UTF-8 with replace so encoding quirks don't 500).
        raw = await asyncio.to_thread(target.read_bytes)
        text = raw.decode("utf-8", errors="replace")
        truncated = len(text) > _MAX_DOCUMENT_CONTENT_CHARS
        if truncated:
            text = text[:_MAX_DOCUMENT_CONTENT_CHARS]
        return DocumentContentResponse(
            document_id=doc.id,
            notebook_id=doc.notebook_id,
            filename=doc.filename,
            content_type=doc.content_type,
            size_bytes=doc.size_bytes,
            content=text,
            truncated=truncated,
        )

    async def get_document_file(
        self,
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> tuple[Path, str, str | None]:
        """Resolve disk path for inline viewing; returns (path, filename, content_type)."""
        await self._load_owned(notebook_id, owner_id)
        doc = await self.documents.get(document_id)
        if doc is None or doc.notebook_id != notebook_id:
            raise NotFoundError(
                message="Document not found",
                code="document_not_found",
            )
        target = self.storage_root / doc.storage_path
        if not target.exists():
            raise NotFoundError(
                message="Document file missing on disk",
                code="document_file_missing",
            )
        return target, doc.filename, doc.content_type

    async def upload_document(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        filename: str,
        content: bytes,
    ) -> DocumentUploadResponse:
        """Persist the file and enqueue indexing in the notebook worker."""
        await self._load_owned(notebook_id, owner_id)

        # Reject before creating any DB / disk artefacts.
        ext = safe_extension(
            filename,
            allowed=_ALLOWED_DOCUMENT_EXTENSIONS,
            default=_REJECT_SENTINEL_EXTENSION,
        )
        if ext == _REJECT_SENTINEL_EXTENSION:
            raise ValidationError(
                message=(
                    f"Unsupported document type for {filename!r}; allowed: "
                    f"{sorted(_ALLOWED_DOCUMENT_EXTENSIONS)}"
                ),
                code="unsupported_document_type",
            )

        # Astronomy-relevance gate: reject obvious off-topic uploads before
        # we spend disk/index resources. Fail-open on LLM/parse errors.
        if self._llm is not None:
            sample = await asyncio.to_thread(_extract_gate_sample, ext, content)
            is_astro, reason = await check_document_relevance(
                self._llm, filename, sample
            )
            if not is_astro:
                raise ValidationError(
                    message=(
                        "This document does not appear to be related to "
                        "astronomy. AstroLearn only supports astronomy "
                        "content."
                    ),
                    code="not_astronomy_content",
                    details={"reason": reason},
                )

        content_type, _ = mimetypes.guess_type(filename)

        # On-disk filename must match row id (PdfParserTool/worker resolve by id).
        document_id = uuid.uuid4()
        storage_path = f"documents/{document_id}{ext}"
        document = await self.documents.create(
            {
                "id": document_id,
                "notebook_id": notebook_id,
                "owner_id": owner_id,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(content),
                "storage_path": storage_path,
                "status": "queued",
            }
        )

        # Row already exists; on disk failure mark failed before re-raising.
        target = self.storage_root / storage_path
        try:
            write_bytes(target, content)
        except OSError as exc:
            await self.documents.set_status(
                document.id, "failed", error=f"disk write failed: {exc}"
            )
            raise

        index_document.delay(str(document.id), str(notebook_id), filename)

        # Build explicitly: response renames row `id` to `document_id`.
        return DocumentUploadResponse(
            document_id=document.id,
            notebook_id=document.notebook_id,
            filename=document.filename,
            size_bytes=document.size_bytes,
            status="queued",
            indexed_chunks=document.indexed_chunks,
        )

    async def run_qa(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: QARequest,
    ) -> QAResponse:
        """Run the QA agent against the notebook and persist the conversation."""
        await self._load_owned(notebook_id, owner_id)

        session = await self._get_or_create_qa_session(
            owner_id,
            notebook_id,
            request.session_id,
            question=request.question,
        )
        # Commit so recorder's separate connection sees the session FK target.
        await self.notebooks.session.commit()

        # Persist user turn first so transcript survives agent failures.
        await self.messages.create(
            {
                "session_id": session.id,
                "role": "user",
                "content": request.question,
            }
        )

        # Stringify UUIDs: asyncpg JSON encoder can't serialise raw UUID.
        task: dict[str, Any] = {
            "question": request.question,
            "notebook_id": str(notebook_id),
            "session_id": str(session.id),
            "top_k": request.top_k,
        }
        output = await self._run_agent("qa", owner_id, session.id, task)

        answer = str(output.get("answer", "")).strip()
        citations_raw = output.get("citations") or []

        assistant_msg = await self.messages.create(
            {
                "session_id": session.id,
                "role": "assistant",
                "content": answer,
                "extra": {"citations": citations_raw},
            }
        )

        return QAResponse(
            answer=answer,
            citations=[Citation(**c) for c in citations_raw],
            session_id=session.id,
            message_id=assistant_msg.id,
        )

    async def run_summarize(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: SummarizeRequest,
    ) -> SummarizeResponse:
        """Delegate to the summarizer agent."""
        # Agent has no DB access — inject source count from here.
        await self._load_owned(notebook_id, owner_id)
        source_document_count = await self.documents.count_for_notebook(notebook_id)

        # session_id=None: per-notebook artifact, not chat — avoid mint on regen.
        task: dict[str, Any] = {
            "notebook_id": str(notebook_id),
            "max_bullets": request.max_bullets,
            "style": request.style,
            "source_document_count": source_document_count,
        }
        output = await self._run_agent("summarizer", owner_id, None, task)

        response = SummarizeResponse(
            summary=output.get("summary", [] if request.style == "bullets" else ""),
            source_document_count=int(
                output.get("source_document_count", source_document_count)
            ),
        )
        await self._save_artifact(
            notebook_id,
            "summary",
            params={"max_bullets": request.max_bullets, "style": request.style},
            payload=response.model_dump(),
        )
        return response

    async def run_quiz(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: QuizRequest,
    ) -> QuizResponse:
        """Delegate to the quiz-generator agent."""
        await self._load_owned(notebook_id, owner_id)

        # session_id=None: see run_summarize.
        task: dict[str, Any] = {
            "notebook_id": str(notebook_id),
            "n_questions": request.n_questions,
            "difficulty": request.difficulty,
        }
        output = await self._run_agent("quiz", owner_id, None, task)

        response = QuizResponse(
            questions=[QuizItem(**q) for q in (output.get("questions") or [])]
        )
        await self._save_artifact(
            notebook_id,
            "quiz",
            params={
                "n_questions": request.n_questions,
                "difficulty": request.difficulty,
            },
            payload=response.model_dump(),
        )
        return response

    async def run_flashcards(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: FlashcardRequest,
    ) -> FlashcardResponse:
        """Delegate to the flashcard-generator agent."""
        await self._load_owned(notebook_id, owner_id)

        # session_id=None: see run_summarize.
        task: dict[str, Any] = {
            "notebook_id": str(notebook_id),
            "n_cards": request.n_cards,
        }
        output = await self._run_agent("flashcard", owner_id, None, task)

        response = FlashcardResponse(
            cards=[Flashcard(**c) for c in (output.get("cards") or [])]
        )
        await self._save_artifact(
            notebook_id,
            "flashcards",
            params={"n_cards": request.n_cards},
            payload=response.model_dump(),
        )
        return response

    async def run_study_pack(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: StudyPackRequest,
    ) -> AgentResponse:
        """Kick off the notebook study-pack workflow asynchronously."""
        # Workflow is ~30-60s; hand off to worker to avoid blocking request.
        await self._load_owned(notebook_id, owner_id)

        task_input: dict[str, Any] = {
            "notebook_id": str(notebook_id),
            "max_bullets": request.max_bullets,
            "n_questions": request.n_questions,
            "n_cards": request.n_cards,
        }
        # Row must commit BEFORE worker starts, else worker hits "row missing".
        run_id = await self._create_pending_study_pack_run(
            owner_id=owner_id,
            session_id=None,
            task_input=task_input,
        )

        # max_retries=0; failures land in agent_runs.error for UI display.
        generate_study_pack.delay(
            str(run_id),
            str(notebook_id),
            request.max_bullets,
            request.n_questions,
            request.n_cards,
        )

        # Independent session: request session can't see other-tx writes.
        agent_row = await self._fetch_run_via_independent_session(run_id)
        assert agent_row is not None
        return AgentResponse.model_validate(agent_row)

    async def run_learning_pack(
        self,
        notebook_id: uuid.UUID,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: LearningPackRequest,
    ) -> AgentResponse:
        """Kick off the per-document learning workflow asynchronously."""
        await self._load_owned(notebook_id, owner_id)
        document = await self.documents.get(document_id)
        if document is None or document.notebook_id != notebook_id:
            raise NotFoundError(
                message="Document not found",
                code="document_not_found",
            )
        if document.status != "indexed":
            raise ValidationError(
                message=(
                    f"Document is not indexed (status={document.status!r}). "
                    "Wait for indexing to finish before generating a "
                    "learning pack."
                ),
                code="document_not_indexed",
            )

        task_input: dict[str, Any] = {
            "notebook_id": str(notebook_id),
            "document_id": str(document_id),
            "n_questions": request.n_questions,
            "n_cards": request.n_cards,
        }
        run_id = await self._create_pending_learning_pack_run(
            owner_id=owner_id,
            session_id=None,
            task_input=task_input,
        )

        # max_retries=2; permanent failures filtered above.
        generate_learning_pack.delay(
            str(run_id),
            str(document_id),
            str(notebook_id),
            request.n_questions,
            request.n_cards,
        )

        agent_row = await self._fetch_run_via_independent_session(run_id)
        assert agent_row is not None
        return AgentResponse.model_validate(agent_row)

    async def _create_pending_learning_pack_run(
        self,
        *,
        owner_id: uuid.UUID,
        session_id: uuid.UUID | None,
        task_input: dict[str, Any],
    ) -> uuid.UUID:
        """Insert the agent_runs row in its own short transaction."""
        # Must commit before .delay() so worker's separate connection sees it.
        async with self._session_factory() as s:
            repo = AgentRepository(s)
            row = await repo.create(
                {
                    "user_id": owner_id,
                    "session_id": session_id,
                    "agent_name": "learning_workflow",
                    "status": "pending",
                    "task_input": task_input,
                }
            )
            await s.commit()
            return row.id

    async def _create_pending_study_pack_run(
        self,
        *,
        owner_id: uuid.UUID,
        session_id: uuid.UUID | None,
        task_input: dict[str, Any],
    ) -> uuid.UUID:
        """Insert the agent_runs row in its own short transaction."""
        # Must commit before .delay() so worker's separate connection sees it.
        async with self._session_factory() as s:
            repo = AgentRepository(s)
            row = await repo.create(
                {
                    "user_id": owner_id,
                    "session_id": session_id,
                    "agent_name": "notebook_workflow",
                    "status": "pending",
                    "task_input": task_input,
                }
            )
            await s.commit()
            return row.id

    async def _fetch_run_via_independent_session(
        self,
        run_id: uuid.UUID,
    ) -> AgentModel | None:
        """Read via independent session when request session can't see other-tx writes."""
        async with self._session_factory() as s:
            return await AgentRepository(s).get(run_id)

    async def get_artifact(
        self,
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID,
        kind: str,
    ) -> NotebookArtifactPayload | None:
        """Return cached payload + params for (notebook_id, kind), or None."""
        await self._load_owned(notebook_id, owner_id)
        if self.artifacts is None:
            return None
        row = await self.artifacts.get_by_kind(notebook_id, kind)
        if row is None:
            return None
        return NotebookArtifactPayload(
            notebook_id=row.notebook_id,
            kind=row.kind,
            params=row.params,
            payload=row.payload,
            updated_at=row.updated_at,
        )

    async def _save_artifact(
        self,
        notebook_id: uuid.UUID,
        kind: str,
        *,
        params: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        """Best-effort upsert; DB error must not fail the user-facing route."""
        if self.artifacts is None:
            return
        try:
            await self.artifacts.upsert(
                notebook_id, kind, params=params, payload=payload
            )
        except Exception:  # noqa: BLE001 — best-effort persistence
            _logger.warning(
                "notebook_artifact.save_failed",
                notebook_id=str(notebook_id),
                kind=kind,
            )

    async def _run_agent(
        self,
        agent_name: str,
        owner_id: uuid.UUID,
        session_id: uuid.UUID | None,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """Build agent, run inside recorder context, return final_output."""
        agent = self.factory(agent_name)
        async with self.recorder.run(
            user_id=owner_id,
            session_id=session_id,
            agent_name=agent_name,
            task=task,
        ) as handle:
            state = AgentState(
                run_id=handle.run_id,
                agent_name=agent_name,
                user_id=owner_id,
                session_id=session_id,
            )
            terminal_state = await agent.run(task, state=state)
            output = terminal_state.final_output or {}
            handle.set_output(output)
        return output

    async def _get_or_create_qa_session(
        self,
        owner_id: uuid.UUID,
        notebook_id: uuid.UUID,
        session_id: uuid.UUID | None,
        *,
        question: str,
    ) -> SessionModel:  # noqa: F821 — forward ref for clarity
        """Return an owned session for this Q&A turn, creating one if needed."""
        # Auto-title new sessions from first question for sidebar display.
        if session_id is not None:
            row = await self.sessions.get(session_id)
            if row is None:
                raise NotFoundError(
                    message="Session not found",
                    code="session_not_found",
                )
            if row.user_id != owner_id:
                raise AuthorizationError(
                    message="Session belongs to another user",
                    code="forbidden",
                )
            return row

        title = question.strip()[:_QA_SESSION_TITLE_CHAR_CAP] or None
        return await self.sessions.create(
            {
                "user_id": owner_id,
                "notebook_id": notebook_id,
                "title": title,
            }
        )
