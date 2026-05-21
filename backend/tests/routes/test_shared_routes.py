"""End-to-end tests for /api/v1/shared/{token} — public notebook view."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_shared_unknown_token_returns_404(client: AsyncClient) -> None:
    r = await client.get("/api/v1/shared/not-a-real-token")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_share_then_public_get(
    client: AsyncClient, authed_client: AsyncClient
) -> None:
    r = await authed_client.post(
        "/api/v1/notebooks/",
        json={"title": "Public NB", "description": "shared"},
    )
    nb_id = r.json()["id"]
    r = await authed_client.post(f"/api/v1/notebooks/{nb_id}/share")
    token = r.json()["share_token"]

    # Unauthenticated client gets the scrubbed payload.
    r = await client.get(f"/api/v1/shared/{token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Public NB"
    assert body["description"] == "shared"
    assert "documents" in body
    assert "document_count" in body


@pytest.mark.asyncio
async def test_revoked_share_returns_404(
    client: AsyncClient, authed_client: AsyncClient
) -> None:
    r = await authed_client.post(
        "/api/v1/notebooks/",
        json={"title": "Throwaway", "description": None},
    )
    nb_id = r.json()["id"]
    r = await authed_client.post(f"/api/v1/notebooks/{nb_id}/share")
    token = r.json()["share_token"]

    r = await authed_client.delete(f"/api/v1/notebooks/{nb_id}/share")
    assert r.status_code == 204

    r = await client.get(f"/api/v1/shared/{token}")
    assert r.status_code == 404
