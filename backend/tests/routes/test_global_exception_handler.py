"""Tests for the catch-all unhandled-exception handler."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import FakeAgentFactory


@pytest.mark.asyncio
async def test_unhandled_exception_returns_internal_error_envelope(
    authed_client: AsyncClient,
    fake_factory: FakeAgentFactory,
) -> None:
    """Non-AstroLearn exceptions surface as a clean envelope without leaking detail."""
    fake_factory.set_raises(
        "qa", RuntimeError("internal-detail-that-must-not-leak")
    )
    r = await authed_client.post(
        "/api/v1/agents/run",
        json={"agent_name": "qa", "task_input": {}, "stream": False},
    )
    assert r.status_code == 500
    body = r.json()
    assert body == {
        "error": {
            "code": "internal_error",
            "message": "An internal error occurred",
            "details": {},
        }
    }
    assert "internal-detail" not in r.text
