"""Schemas for /admin/* endpoints (user management & analytics)."""

from __future__ import annotations

import uuid
from datetime import date, datetime  # noqa: F401  (re-exported via models)

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from schemas.token_usage_schema import (
    CostBreakdownResponse,
    DailyUsageItem,
    ModelUsageItem,
    UsageTotalsResponse,
)
from schemas.user_schema import UserResponse

# Single-sourced types; route handlers keep distinct OpenAPI tags.
AdminModelUsageItem = ModelUsageItem
AdminCostBreakdownResponse = CostBreakdownResponse


class AdminUserListItem(BaseModel):
    """Row in the admin user table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    """Paginated list payload."""

    items: list[AdminUserListItem]
    total: int
    limit: int
    offset: int


class AdminUserUpdateRequest(BaseModel):
    """Body for PATCH /admin/users/{id}; email is not mutable here."""

    full_name: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    is_admin: bool | None = None


class AdminTopUserItem(BaseModel):
    """One row in the "top consumers" chart."""

    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AdminOverviewResponse(BaseModel):
    """System-wide stats for the admin dashboard landing page."""

    total_users: int
    active_users: int
    admin_users: int
    users_active_in_window: int
    new_users_in_window: int
    window_days: int
    month_total: UsageTotalsResponse
    month_start: date
    daily: list[DailyUsageItem]
    top_users: list[AdminTopUserItem]


class AdminUserDetailResponse(BaseModel):
    """Per-user detail view shown on /admin/users/[id]."""

    user: UserResponse
    month_total: UsageTotalsResponse
    month_start: date
    window_days: int
    daily: list[DailyUsageItem]
    notebooks_count: int
    documents_count: int
    fits_files_count: int
    analyses_count: int


class AdminAgentRunItem(BaseModel):
    """One row in the admin agent-runs table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: EmailStr | None
    agent_name: str
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    progress: float | None
    current_step: str | None
    step_count: int
    created_at: datetime


class AdminAgentRunListResponse(BaseModel):
    """Paginated agent-run list."""

    items: list[AdminAgentRunItem]
    total: int
    limit: int
    offset: int
    status_counts: dict[str, int]


class AdminAgentRunDetailResponse(BaseModel):
    """Single agent run including payloads (modal/detail view)."""

    run: AdminAgentRunItem
    task_input: dict
    output: dict | None


class AdminNotebookItem(BaseModel):
    """One row in the admin notebooks table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: EmailStr | None
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    is_shared: bool


class AdminNotebookListResponse(BaseModel):
    items: list[AdminNotebookItem]
    total: int
    limit: int
    offset: int


class AdminFitsFileItem(BaseModel):
    """One row in the admin FITS table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: EmailStr | None
    filename: str
    size_bytes: int
    status: str
    hdu_count: int
    created_at: datetime


class AdminFitsListResponse(BaseModel):
    items: list[AdminFitsFileItem]
    total: int
    limit: int
    offset: int
    total_storage_bytes: int
