"""Public read-only notebook access via share token (no auth)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.dependencies import NotebookServiceDep
from schemas.notebook_schema import (
    NotebookArtifactKind,
    NotebookArtifactPayload,
    SharedNotebookResponse,
)

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/{token}", response_model=SharedNotebookResponse)
async def get_shared_notebook(
    token: str,
    service: NotebookServiceDep,
) -> SharedNotebookResponse:
    """Public read-only notebook view (scrubbed payload, 404 on miss/revoked)."""
    return await service.get_shared(token)


@router.get("/{token}/documents/{document_id}/file")
async def get_shared_document_file(
    token: str,
    document_id: uuid.UUID,
    service: NotebookServiceDep,
) -> FileResponse:
    """Stream raw document bytes for inline viewing in the shared page."""
    path, filename, content_type = await service.get_shared_document_file(
        token, document_id
    )
    return FileResponse(
        path,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/{token}/artifacts/{kind}",
    response_model=NotebookArtifactPayload | None,
)
async def get_shared_artifact(
    token: str,
    kind: NotebookArtifactKind,
    service: NotebookServiceDep,
) -> NotebookArtifactPayload | None:
    """Return owner-generated summary/quiz/flashcards if cached, else null."""
    return await service.get_shared_artifact(token, kind)
