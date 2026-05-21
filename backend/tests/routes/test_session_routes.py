"""End-to-end tests for /api/v1/sessions/* — CRUD, messages, FITS attach."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _create_session(client: AsyncClient, mode: str = "general") -> dict:
    r = await client.post("/api/v1/sessions/", json={"mode": mode})
    assert r.status_code == 201, r.text
    return r.json()


# --- Auth -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sessions_require_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/sessions/")
    assert r.status_code == 401


# --- CRUD -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_row(authed_client: AsyncClient) -> None:
    s = await _create_session(authed_client)
    assert s["mode"] == "general"
    assert "id" in s


@pytest.mark.asyncio
async def test_list_then_get(authed_client: AsyncClient) -> None:
    s = await _create_session(authed_client)
    r = await authed_client.get("/api/v1/sessions/")
    assert r.status_code == 200
    assert any(row["id"] == s["id"] for row in r.json())

    r = await authed_client.get(f"/api/v1/sessions/{s['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == s["id"]


@pytest.mark.asyncio
async def test_update_session_mode(authed_client: AsyncClient) -> None:
    s = await _create_session(authed_client)
    r = await authed_client.patch(
        f"/api/v1/sessions/{s['id']}",
        json={"mode": "fits"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "fits"


@pytest.mark.asyncio
async def test_delete_session(authed_client: AsyncClient) -> None:
    s = await _create_session(authed_client)
    r = await authed_client.delete(f"/api/v1/sessions/{s['id']}")
    assert r.status_code == 204
    r = await authed_client.get(f"/api/v1/sessions/{s['id']}")
    assert r.status_code in {403, 404}


# --- Messages ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_messages_empty_for_new_session(
    authed_client: AsyncClient,
) -> None:
    s = await _create_session(authed_client)
    r = await authed_client.get(f"/api/v1/sessions/{s['id']}/messages")
    assert r.status_code == 200
    assert r.json() == []


# --- Filtering by notebook --------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_filtered_by_notebook(
    authed_client: AsyncClient,
) -> None:
    # Create a notebook first so we have a valid notebook_id.
    r = await authed_client.post(
        "/api/v1/notebooks/",
        json={"title": "T", "description": None},
    )
    nb_id = r.json()["id"]

    # Two sessions: one in general mode, one bound to the notebook.
    await _create_session(authed_client, mode="general")
    r = await authed_client.post(
        "/api/v1/sessions/",
        json={"mode": "notebook", "notebook_id": nb_id},
    )
    assert r.status_code == 201

    r = await authed_client.get(
        "/api/v1/sessions/", params={"notebook_id": nb_id}
    )
    assert r.status_code == 200
    rows = r.json()
    assert all(row["notebook_id"] == nb_id for row in rows)
    assert len(rows) == 1
