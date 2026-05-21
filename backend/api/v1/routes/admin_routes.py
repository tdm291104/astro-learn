"""Admin-only routes (user management & system analytics)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from core.dependencies import AdminServiceDep, CurrentAdminDep
from schemas.admin_schema import (
    AdminAgentRunDetailResponse,
    AdminAgentRunListResponse,
    AdminCostBreakdownResponse,
    AdminFitsListResponse,
    AdminNotebookListResponse,
    AdminOverviewResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)
from schemas.user_schema import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    q: str | None = Query(None, description="Substring match on email/full_name"),
    is_active: bool | None = Query(None),
    is_admin: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminUserListResponse:
    """Paginated user search for the admin table."""
    return await service.list_users(
        query=q,
        is_active=is_active,
        is_admin=is_admin,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user(
    user_id: uuid.UUID,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    days: int = Query(30, ge=1, le=90),
) -> AdminUserDetailResponse:
    """Detail view: profile + per-user usage chart + content counts."""
    return await service.user_detail(user_id, days=days)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    request: AdminUserUpdateRequest,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
) -> UserResponse:
    """Patch any of full_name / is_active / is_admin."""
    return await service.update_user(
        user_id, request, acting_admin_id=admin.id
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
) -> None:
    """Hard-delete a user. Owned rows cascade via ORM relationships."""
    await service.delete_user(user_id, acting_admin_id=admin.id)


@router.get("/stats/overview", response_model=AdminOverviewResponse)
async def stats_overview(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    days: int = Query(30, ge=1, le=90),
) -> AdminOverviewResponse:
    """System-wide stats: user counts + token usage chart + top users."""
    return await service.overview(days=days)


@router.get("/stats/cost-breakdown", response_model=AdminCostBreakdownResponse)
async def stats_cost_breakdown(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    days: int = Query(30, ge=1, le=90),
) -> AdminCostBreakdownResponse:
    """Per-model token usage + estimated cost over the rolling window."""
    return await service.cost_breakdown(days=days)


@router.get("/agent-runs", response_model=AdminAgentRunListResponse)
async def list_agent_runs(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    status: str | None = Query(None, description="Filter by run status."),
    agent_name: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminAgentRunListResponse:
    """Paginated list of agent runs across all users."""
    return await service.list_agent_runs(
        status=status,
        agent_name=agent_name,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/agent-runs/{run_id}", response_model=AdminAgentRunDetailResponse
)
async def get_agent_run(
    run_id: uuid.UUID,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
) -> AdminAgentRunDetailResponse:
    """Single agent run including task_input/output for debugging."""
    return await service.get_agent_run(run_id)


@router.get("/notebooks", response_model=AdminNotebookListResponse)
async def list_notebooks(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    q: str | None = Query(None),
    owner_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminNotebookListResponse:
    """Admin-wide notebook list across owners."""
    return await service.list_notebooks(
        query=q, owner_id=owner_id, limit=limit, offset=offset
    )


@router.delete(
    "/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_notebook(
    notebook_id: uuid.UUID,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
) -> None:
    """Hard-delete any notebook regardless of owner."""
    await service.delete_notebook(notebook_id)


@router.get("/fits", response_model=AdminFitsListResponse)
async def list_fits_files(
    admin: CurrentAdminDep,
    service: AdminServiceDep,
    q: str | None = Query(None),
    owner_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminFitsListResponse:
    """Admin-wide FITS file list across owners + total storage usage."""
    return await service.list_fits_files(
        query=q, owner_id=owner_id, limit=limit, offset=offset
    )


@router.delete("/fits/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fits_file(
    file_id: uuid.UUID,
    admin: CurrentAdminDep,
    service: AdminServiceDep,
) -> None:
    """Hard-delete a FITS file (DB row + on-disk file + artefacts)."""
    await service.delete_fits_file(file_id)
