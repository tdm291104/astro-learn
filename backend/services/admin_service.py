"""Admin-only business logic: user management & system-wide analytics."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog

from core.exceptions import NotFoundError, ValidationError
from repositories.agent_repository import AgentRepository
from repositories.analysis_repository import AnalysisRepository
from repositories.document_repository import DocumentRepository
from repositories.fits_file_repository import FitsFileRepository
from repositories.notebook_repository import NotebookRepository
from repositories.token_usage_repository import TokenUsageRepository
from repositories.user_repository import UserRepository
from schemas.admin_schema import (
    AdminAgentRunDetailResponse,
    AdminAgentRunItem,
    AdminAgentRunListResponse,
    AdminCostBreakdownResponse,
    AdminFitsFileItem,
    AdminFitsListResponse,
    AdminNotebookItem,
    AdminNotebookListResponse,
    AdminOverviewResponse,
    AdminTopUserItem,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)
from schemas.token_usage_schema import DailyUsageItem, UsageTotalsResponse
from schemas.user_schema import UserResponse

_logger = structlog.get_logger(__name__)


class AdminService:
    """Read + mutate users and roll up system-wide stats."""

    def __init__(
        self,
        *,
        users: UserRepository,
        token_usage: TokenUsageRepository,
        notebooks: NotebookRepository,
        documents: DocumentRepository,
        fits_files: FitsFileRepository,
        analyses: AnalysisRepository,
        agent_runs: AgentRepository,
        storage_root: Path,
    ) -> None:
        self.users = users
        self.token_usage = token_usage
        self.notebooks = notebooks
        self.documents = documents
        self.fits_files = fits_files
        self.analyses = analyses
        self.agent_runs = agent_runs
        self.storage_root = storage_root

    async def list_users(
        self,
        *,
        query: str | None,
        is_active: bool | None,
        is_admin: bool | None,
        limit: int,
        offset: int,
    ) -> AdminUserListResponse:
        """Paginated user list for the admin table."""
        # Clamp at service boundary so route layer only validates shape.
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        rows = await self.users.search(
            query=query,
            is_active=is_active,
            is_admin=is_admin,
            limit=limit,
            offset=offset,
        )
        total = await self.users.count_search(
            query=query, is_active=is_active, is_admin=is_admin
        )
        return AdminUserListResponse(
            items=[AdminUserListItem.model_validate(u) for u in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update_user(
        self,
        user_id: uuid.UUID,
        request: AdminUserUpdateRequest,
        *,
        acting_admin_id: uuid.UUID,
    ) -> UserResponse:
        """Patch a user; protects against admins locking themselves out."""
        data = request.model_dump(exclude_unset=True)

        # Normalize empty full_name to NULL.
        if "full_name" in data:
            raw = data["full_name"]
            data["full_name"] = (
                raw.strip() if isinstance(raw, str) and raw.strip() else None
            )

        # Prevent self-lockout; recovery requires CLI promote.
        if user_id == acting_admin_id:
            if data.get("is_admin") is False:
                raise ValidationError(
                    message="You cannot revoke your own admin role",
                    code="self_demote_forbidden",
                )
            if data.get("is_active") is False:
                raise ValidationError(
                    message="You cannot deactivate your own account",
                    code="self_deactivate_forbidden",
                )

        if not data:
            existing = await self.users.get(user_id)
            if existing is None:
                raise NotFoundError(
                    message="User not found", code="user_not_found"
                )
            return UserResponse.model_validate(existing)

        updated = await self.users.update(user_id, data)
        if updated is None:
            raise NotFoundError(
                message="User not found", code="user_not_found"
            )
        return UserResponse.model_validate(updated)

    async def delete_user(
        self,
        user_id: uuid.UUID,
        *,
        acting_admin_id: uuid.UUID,
    ) -> None:
        """Hard-delete a user. Owned notebooks/sessions cascade per ORM config."""
        if user_id == acting_admin_id:
            raise ValidationError(
                message="You cannot delete your own account",
                code="self_delete_forbidden",
            )
        deleted = await self.users.delete(user_id)
        if not deleted:
            raise NotFoundError(
                message="User not found", code="user_not_found"
            )

    async def overview(self, *, days: int = 30) -> AdminOverviewResponse:
        """System-wide stats for the admin landing page."""
        window_days = max(1, min(days, 90))
        now = datetime.now(UTC)
        today = now.date()
        month_start_dt = datetime(now.year, now.month, 1, tzinfo=UTC)
        window_start_date = today - timedelta(days=window_days - 1)
        window_start_dt = datetime(
            window_start_date.year,
            window_start_date.month,
            window_start_date.day,
            tzinfo=UTC,
        )

        total_users = await self.users.count_search()
        active_users = await self.users.count_search(is_active=True)
        admin_users = await self.users.count_search(is_admin=True)
        users_active_in_window = await self.token_usage.count_active_users_since(
            window_start_dt
        )
        new_users_in_window = await self.users.count_created_since(window_start_dt)

        month_totals = await self.token_usage.totals_all_since(month_start_dt)
        daily_rows = await self.token_usage.daily_breakdown_all(window_start_dt)
        daily = _zero_fill(daily_rows, window_start_date, window_days)

        top_rows = await self.token_usage.top_users(window_start_dt, limit=10)
        top_users: list[AdminTopUserItem] = []
        for r in top_rows:
            user = await self.users.get(r.user_id)
            if user is None:
                # Brief orphan window between user delete and cascade.
                continue
            top_users.append(
                AdminTopUserItem(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    total_tokens=r.total_tokens,
                )
            )

        return AdminOverviewResponse(
            total_users=total_users,
            active_users=active_users,
            admin_users=admin_users,
            users_active_in_window=users_active_in_window,
            new_users_in_window=new_users_in_window,
            window_days=window_days,
            month_total=UsageTotalsResponse(
                prompt_tokens=month_totals.prompt_tokens,
                completion_tokens=month_totals.completion_tokens,
                total_tokens=month_totals.total_tokens,
            ),
            month_start=month_start_dt.date(),
            daily=daily,
            top_users=top_users,
        )

    async def user_detail(
        self,
        user_id: uuid.UUID,
        *,
        days: int = 30,
    ) -> AdminUserDetailResponse:
        """Per-user analytics for /admin/users/[id]."""
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found", code="user_not_found"
            )

        window_days = max(1, min(days, 90))
        now = datetime.now(UTC)
        today = now.date()
        month_start_dt = datetime(now.year, now.month, 1, tzinfo=UTC)
        window_start_date = today - timedelta(days=window_days - 1)
        window_start_dt = datetime(
            window_start_date.year,
            window_start_date.month,
            window_start_date.day,
            tzinfo=UTC,
        )

        month_totals = await self.token_usage.totals_since(user_id, month_start_dt)
        daily_rows = await self.token_usage.daily_breakdown(user_id, window_start_dt)
        daily = _zero_fill(daily_rows, window_start_date, window_days)

        notebooks_count = await self.notebooks.count(owner_id=user_id)
        documents_count = await self.documents.count(owner_id=user_id)
        fits_files_count = await self.fits_files.count(owner_id=user_id)
        analyses_count = await self.analyses.count(owner_id=user_id)

        return AdminUserDetailResponse(
            user=UserResponse.model_validate(user),
            month_total=UsageTotalsResponse(
                prompt_tokens=month_totals.prompt_tokens,
                completion_tokens=month_totals.completion_tokens,
                total_tokens=month_totals.total_tokens,
            ),
            month_start=month_start_dt.date(),
            window_days=window_days,
            daily=daily,
            notebooks_count=notebooks_count,
            documents_count=documents_count,
            fits_files_count=fits_files_count,
            analyses_count=analyses_count,
        )

    async def list_agent_runs(
        self,
        *,
        status: str | None,
        agent_name: str | None,
        user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> AdminAgentRunListResponse:
        """Paginated list of agent runs across all users."""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        rows = await self.agent_runs.search(
            status=status,
            agent_name=agent_name,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        total = await self.agent_runs.count_search(
            status=status, agent_name=agent_name, user_id=user_id
        )
        items = [
            await self._agent_run_item(row) for row in rows
        ]
        status_counts = await self.agent_runs.status_counts()
        return AdminAgentRunListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            status_counts=status_counts,
        )

    async def get_agent_run(self, run_id: uuid.UUID) -> AdminAgentRunDetailResponse:
        """Single run with full task_input/output payloads."""
        row = await self.agent_runs.get(run_id)
        if row is None:
            raise NotFoundError(
                message="Agent run not found", code="agent_run_not_found"
            )
        return AdminAgentRunDetailResponse(
            run=await self._agent_run_item(row),
            task_input=row.task_input or {},
            output=row.output,
        )

    async def _agent_run_item(self, row) -> AdminAgentRunItem:
        # Resolve owner email server-side to avoid FE N+1 lookups.
        user = await self.users.get(row.user_id)
        duration_ms: int | None = None
        if row.started_at and row.finished_at:
            duration_ms = int(
                (row.finished_at - row.started_at).total_seconds() * 1000
            )
        return AdminAgentRunItem(
            id=row.id,
            user_id=row.user_id,
            user_email=(user.email if user is not None else None),
            agent_name=row.agent_name,
            status=row.status,
            error=row.error,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration_ms=duration_ms,
            progress=row.progress,
            current_step=row.current_step,
            step_count=row.step_count,
            created_at=row.created_at,
        )

    async def cost_breakdown(self, *, days: int = 30) -> AdminCostBreakdownResponse:
        """System-wide per-model token + estimated USD cost; delegates to TokenUsageService."""
        # Local import to avoid circular import at module load.
        from services.token_usage_service import TokenUsageService

        delegate = TokenUsageService(repo=self.token_usage)
        return await delegate.cost_breakdown(user_id=None, days=days)

    async def list_notebooks(
        self,
        *,
        query: str | None,
        owner_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> AdminNotebookListResponse:
        """Admin-wide notebook listing across all owners."""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        rows = await self.notebooks.search_all(
            query=query, owner_id=owner_id, limit=limit, offset=offset
        )
        total = await self.notebooks.count_search_all(
            query=query, owner_id=owner_id
        )
        return AdminNotebookListResponse(
            items=[await self._notebook_item(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def delete_notebook(self, notebook_id: uuid.UUID) -> None:
        """Hard-delete notebook + best-effort disk cleanup. Skips Qdrant (rare op)."""
        row = await self.notebooks.get(notebook_id)
        if row is None:
            raise NotFoundError(
                message="Notebook not found", code="notebook_not_found"
            )

        documents = await self.documents.list_for_notebook(
            notebook_id, limit=10_000, offset=0
        )
        deleted = await self.notebooks.delete(notebook_id)
        if not deleted:  # pragma: no cover — race with a concurrent delete
            return

        for doc in documents:
            target = self.storage_root / doc.storage_path
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                _logger.warning(
                    "admin.notebook_document_unlink_failed",
                    notebook_id=str(notebook_id),
                    document_id=str(doc.id),
                    storage_path=doc.storage_path,
                    error=str(exc),
                )

    async def list_fits_files(
        self,
        *,
        query: str | None,
        owner_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> AdminFitsListResponse:
        """Admin-wide FITS file listing across all owners."""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        rows = await self.fits_files.search_all(
            query=query, owner_id=owner_id, limit=limit, offset=offset
        )
        total = await self.fits_files.count_search_all(
            query=query, owner_id=owner_id
        )
        total_storage = await self.fits_files.storage_total_bytes()
        return AdminFitsListResponse(
            items=[await self._fits_item(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
            total_storage_bytes=total_storage,
        )

    async def delete_fits_file(self, file_id: uuid.UUID) -> None:
        """Hard-delete a FITS row + on-disk file + artefacts directory."""
        row = await self.fits_files.get(file_id)
        if row is None:
            raise NotFoundError(
                message="FITS file not found", code="fits_not_found"
            )
        storage_path = row.storage_path

        deleted = await self.fits_files.delete(file_id)
        if not deleted:  # pragma: no cover
            return

        fits_path = self.storage_root / storage_path
        try:
            fits_path.unlink(missing_ok=True)
        except OSError as exc:
            _logger.warning(
                "admin.fits_unlink_failed",
                file_id=str(file_id),
                path=str(fits_path),
                error=str(exc),
            )

        artifacts_path = self.storage_root / "fits_artifacts" / str(file_id)
        if artifacts_path.exists():
            try:
                shutil.rmtree(artifacts_path)
            except OSError as exc:
                _logger.warning(
                    "admin.fits_rmtree_failed",
                    file_id=str(file_id),
                    path=str(artifacts_path),
                    error=str(exc),
                )

    async def _notebook_item(self, row) -> AdminNotebookItem:
        owner = await self.users.get(row.owner_id)
        return AdminNotebookItem(
            id=row.id,
            owner_id=row.owner_id,
            owner_email=(owner.email if owner is not None else None),
            title=row.title,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
            is_shared=bool(row.share_token),
        )

    async def _fits_item(self, row) -> AdminFitsFileItem:
        owner = await self.users.get(row.owner_id)
        return AdminFitsFileItem(
            id=row.id,
            owner_id=row.owner_id,
            owner_email=(owner.email if owner is not None else None),
            filename=row.filename,
            size_bytes=row.size_bytes,
            status=row.status,
            hdu_count=row.hdu_count,
            created_at=row.created_at,
        )


def _zero_fill(
    rows, window_start: date, window_days: int
) -> list[DailyUsageItem]:
    """Densify a sparse daily-usage list to exactly `window_days` items."""
    by_day = {
        r.day: DailyUsageItem(
            date=r.day,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=r.total_tokens,
        )
        for r in rows
    }
    dense: list[DailyUsageItem] = []
    for i in range(window_days):
        d = window_start + timedelta(days=i)
        dense.append(
            by_day.get(
                d,
                DailyUsageItem(
                    date=d,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                ),
            )
        )
    return dense
