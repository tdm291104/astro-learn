"""Schemas for /users/me/stats."""

from __future__ import annotations

from pydantic import BaseModel


class UserStatsResponse(BaseModel):
    """Counts driving the dashboard's stat cards (single round-trip)."""

    notebooks_count: int
    documents_count: int
    fits_files_count: int
    analyses_count: int
