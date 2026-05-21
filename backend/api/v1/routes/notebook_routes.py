"""Notebook routes — CRUD, document upload, Q&A, summarize, quiz, flashcards."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from core.dependencies import CurrentUserDep, NotebookServiceDep
from core.exceptions import NotFoundError, ValidationError
from schemas.agent_schema import AgentResponse
from schemas.notebook_schema import (
    DocumentContentResponse,
    DocumentUploadResponse,
    FlashcardRequest,
    FlashcardResponse,
    LearningPackRequest,
    NotebookArtifactKind,
    NotebookArtifactPayload,
    NotebookCreateRequest,
    NotebookResponse,
    NotebookShareResponse,
    NotebookUpdateRequest,
    QARequest,
    QAResponse,
    QuizRequest,
    QuizResponse,
    ShareSettingsResponse,
    ShareSettingsUpdateRequest,
    StudyPackRequest,
    SummarizeRequest,
    SummarizeResponse,
)

# Per-document upload cap; large PDFs balloon embedding spend.
_MAX_DOCUMENT_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MiB

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.post(
    "/",
    response_model=NotebookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notebook(
    request: NotebookCreateRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> NotebookResponse:
    return await service.create(current_user.id, request)


@router.get("/", response_model=list[NotebookResponse])
async def list_notebooks(
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
    limit: int = 100,
    offset: int = 0,
) -> list[NotebookResponse]:
    return await service.list_for_owner(
        current_user.id, limit=limit, offset=offset
    )


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> NotebookResponse:
    return await service.get(notebook_id, current_user.id)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: uuid.UUID,
    request: NotebookUpdateRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> NotebookResponse:
    return await service.update(notebook_id, current_user.id, request)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> None:
    deleted = await service.delete(notebook_id, current_user.id)
    if not deleted:
        raise NotFoundError(
            message="Notebook not found", code="notebook_not_found"
        )


@router.post(
    "/{notebook_id}/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    """Upload a document (indexed asynchronously in Celery)."""
    if file.size is not None and file.size > _MAX_DOCUMENT_SIZE_BYTES:
        raise ValidationError(
            message=(
                f"Document exceeds {_MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MiB cap "
                f"({file.size} bytes received)"
            ),
            code="file_too_large",
        )

    content = await file.read()
    if len(content) > _MAX_DOCUMENT_SIZE_BYTES:
        raise ValidationError(
            message=(
                f"Document exceeds {_MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MiB cap "
                f"({len(content)} bytes received)"
            ),
            code="file_too_large",
        )

    return await service.upload_document(
        notebook_id,
        current_user.id,
        filename=file.filename or "unnamed",
        content=content,
    )


@router.delete(
    "/{notebook_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    notebook_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> None:
    """Delete a single document and its derived artefacts (owner-scoped)."""
    deleted = await service.delete_document(
        notebook_id, document_id, current_user.id
    )
    if not deleted:
        raise NotFoundError(
            message="Document not found",
            code="document_not_found",
        )


@router.get(
    "/{notebook_id}/documents",
    response_model=list[DocumentUploadResponse],
)
async def list_documents(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
    limit: int = 100,
    offset: int = 0,
) -> list[DocumentUploadResponse]:
    """List documents in `notebook_id` (newest first)."""
    return await service.list_documents(
        notebook_id, current_user.id, limit=limit, offset=offset
    )


@router.get(
    "/{notebook_id}/documents/{document_id}/content",
    response_model=DocumentContentResponse,
)
async def get_document_content(
    notebook_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> DocumentContentResponse:
    """Return extracted text for a document so the FE viewer can render it."""
    return await service.get_document_content(
        notebook_id, document_id, current_user.id
    )


@router.get("/{notebook_id}/documents/{document_id}/file")
async def get_document_file(
    notebook_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> FileResponse:
    """Stream the raw document bytes (PDF/TXT/MD) for inline viewing."""
    path, filename, content_type = await service.get_document_file(
        notebook_id, document_id, current_user.id
    )
    return FileResponse(
        path,
        media_type=content_type or "application/octet-stream",
        # `inline` lets the browser render PDFs in the viewer instead of downloading.
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{notebook_id}/qa", response_model=QAResponse)
async def run_qa(
    notebook_id: uuid.UUID,
    request: QARequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> QAResponse:
    """Q&A grounded in the notebook's indexed documents."""
    return await service.run_qa(notebook_id, current_user.id, request)


@router.post("/{notebook_id}/summarize", response_model=SummarizeResponse)
async def run_summarize(
    notebook_id: uuid.UUID,
    request: SummarizeRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> SummarizeResponse:
    """Summarise the notebook's documents (bullets or paragraph)."""
    return await service.run_summarize(notebook_id, current_user.id, request)


@router.post("/{notebook_id}/quiz", response_model=QuizResponse)
async def run_quiz(
    notebook_id: uuid.UUID,
    request: QuizRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> QuizResponse:
    """Generate a multiple-choice quiz from the notebook's documents."""
    return await service.run_quiz(notebook_id, current_user.id, request)


@router.post("/{notebook_id}/flashcards", response_model=FlashcardResponse)
async def run_flashcards(
    notebook_id: uuid.UUID,
    request: FlashcardRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> FlashcardResponse:
    """Generate front/back flashcards from the notebook's documents."""
    return await service.run_flashcards(notebook_id, current_user.id, request)


@router.get(
    "/{notebook_id}/artifacts/{kind}",
    response_model=NotebookArtifactPayload | None,
)
async def get_notebook_artifact(
    notebook_id: uuid.UUID,
    kind: NotebookArtifactKind,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> NotebookArtifactPayload | None:
    """Return cached summary/quiz/flashcards payload, or null if none."""
    # Null body intentional; FE uses presence to switch between saved/empty.
    return await service.get_artifact(notebook_id, current_user.id, kind)


@router.post(
    "/{notebook_id}/documents/{document_id}/learning-pack",
    response_model=AgentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_learning_pack(
    notebook_id: uuid.UUID,
    document_id: uuid.UUID,
    request: LearningPackRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> AgentResponse:
    """Kick off the per-document learning workflow (summary, quiz, flashcards)."""
    return await service.run_learning_pack(
        notebook_id, document_id, current_user.id, request
    )


@router.post(
    "/{notebook_id}/study-pack",
    response_model=AgentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_study_pack(
    notebook_id: uuid.UUID,
    request: StudyPackRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> AgentResponse:
    """Kick off the notebook study-pack workflow asynchronously."""
    return await service.run_study_pack(notebook_id, current_user.id, request)


# Owner mints token; public GET lives in shared_routes.py.
@router.post("/{notebook_id}/share", response_model=NotebookShareResponse)
async def create_share_link(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> NotebookShareResponse:
    """Mint (or return existing) read-only share token for a notebook."""
    return await service.create_share_token(notebook_id, current_user.id)


@router.delete(
    "/{notebook_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_share_link(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> None:
    """Revoke the notebook's read-only share token (idempotent)."""
    await service.revoke_share_token(notebook_id, current_user.id)


@router.get(
    "/{notebook_id}/share/settings",
    response_model=ShareSettingsResponse,
)
async def get_share_settings(
    notebook_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> ShareSettingsResponse:
    """Return current share-visibility toggles for a notebook."""
    return await service.get_share_settings(notebook_id, current_user.id)


@router.patch(
    "/{notebook_id}/share/settings",
    response_model=ShareSettingsResponse,
)
async def update_share_settings(
    notebook_id: uuid.UUID,
    request: ShareSettingsUpdateRequest,
    current_user: CurrentUserDep,
    service: NotebookServiceDep,
) -> ShareSettingsResponse:
    """Update per-notebook share visibility toggles."""
    return await service.update_share_settings(
        notebook_id, current_user.id, request
    )
