"""End-to-end tests for /api/v1/agents/* — list, run, stream, status."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from agents.base.agent_registry import AgentRegistry
from tests.conftest import FakeAgentFactory

# --- /agents/ ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_includes_registered(
    authed_client: AsyncClient,
) -> None:
    r = await authed_client.get("/api/v1/agents/")
    assert r.status_code == 200
    names = {a["name"] for a in r.json()}
    # Core production agents are registered at import time.
    assert "orchestrator" in names
    assert "qa" in names


# --- /agents/run -------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_one_shot_returns_factory_output(
    authed_client: AsyncClient,
    fake_factory: FakeAgentFactory,
) -> None:
    fake_factory.set_output("qa", {"answer": "stub", "citations": []})
    r = await authed_client.post(
        "/api/v1/agents/run",
        json={"agent_name": "qa", "task_input": {"q": "hi"}, "stream": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["output"] == {"answer": "stub", "citations": []}


@pytest.mark.asyncio
async def test_run_agent_unknown_name_returns_404(
    authed_client: AsyncClient,
) -> None:
    # `AgentRegistry.get` raises before the factory is called, so we don't
    # need to register/unregister anything; just pick a non-existent name.
    r = await authed_client.post(
        "/api/v1/agents/run",
        json={"agent_name": "does_not_exist", "task_input": {}, "stream": False},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "agent_not_found"


# --- /agents/run (SSE) -------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_stream_emits_sse(
    authed_client: AsyncClient,
) -> None:
    """SSE returns synthetic system frame + agent messages + done event."""
    # The agent name must exist in the registry; pick any one.
    assert "qa" in AgentRegistry.names()

    async with authed_client.stream(
        "POST",
        "/api/v1/agents/run",
        json={"agent_name": "qa", "task_input": {"q": "stream me"}, "stream": True},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b""
        async for chunk in response.aiter_raw():
            body += chunk

    frames = [f for f in body.decode("utf-8").split("\n\n") if f.strip()]
    data_frames = [f for f in frames if f.startswith("data: ")]
    # Synthetic first frame carries run_id; FakeAgent yields one message.
    assert len(data_frames) >= 2
    first = json.loads(data_frames[0].removeprefix("data: "))
    assert first["role"] == "system"
    assert isinstance(first.get("extra", {}).get("run_id"), str)

    assert any("event: done" in f for f in frames)
