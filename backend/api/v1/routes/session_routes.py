"""Session routes — CRUD on conversations, messages, FITS attachments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from core.dependencies import (
    AstronomyServiceDep,
    CurrentUserDep,
    SessionServiceDep,
)
from core.exceptions import NotFoundError
from schemas.session_schema import (
    MessageResponse,
    SessionCreate,
    SessionFileAttachRequest,
    SessionResponse,
    SessionUpdate,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    current_user: CurrentUserDep,
    service: SessionServiceDep,
    notebook_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionResponse]:
    return await service.list_for_user(
        current_user.id,
        notebook_id=notebook_id,
        limit=limit,
        offset=offset,
    )


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> SessionResponse:
    """Mint a new conversation for the current user."""
    return await service.create(current_user.id, payload)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> SessionResponse:
    return await service.get(session_id, current_user.id)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> SessionResponse:
    """Patch title / mode / notebook_id on a conversation."""
    return await service.update(session_id, current_user.id, payload)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> list[MessageResponse]:
    return await service.list_messages(session_id, current_user.id)


@router.post(
    "/{session_id}/files",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
)
async def attach_fits_file(
    session_id: uuid.UUID,
    payload: SessionFileAttachRequest,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> SessionResponse:
    """Attach a FITS file to this conversation. Idempotent on duplicates."""
    return await service.attach_fits_file(
        session_id, current_user.id, payload.fits_file_id
    )


@router.delete(
    "/{session_id}/files/{fits_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_fits_file(
    session_id: uuid.UUID,
    fits_file_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
) -> None:
    """Remove a FITS file from this conversation."""
    detached = await service.detach_fits_file(
        session_id, current_user.id, fits_file_id
    )
    if not detached:
        raise NotFoundError(
            message="Session or attachment not found",
            code="attachment_not_found",
        )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: SessionServiceDep,
    astronomy: AstronomyServiceDep,
) -> None:
    deleted, orphan_file_ids = await service.delete(session_id, current_user.id)
    if not deleted:
        raise NotFoundError(message="Session not found", code="session_not_found")

    # Best-effort cascade of orphaned FITS files; failure must not block 204.
    for file_id in orphan_file_ids:
        try:
            await astronomy.delete_fits_file(current_user.id, file_id)
        except NotFoundError:
            continue
        except Exception:  # noqa: BLE001 — best-effort cascade
            continue
