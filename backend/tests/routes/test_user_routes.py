"""End-to-end tests for /api/v1/users/* — register, login, profile, stats."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str, password: str) -> dict:
    r = await client.post(
        "/api/v1/users/register",
        json={"email": email, "password": password},
    )
    return r.json() | {"_status": r.status_code, "_text": r.text}


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    r = await client.post(
        "/api/v1/users/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return r.json() | {"_status": r.status_code, "_text": r.text}


# --- Register ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_creates_active_user(client: AsyncClient) -> None:
    body = await _register(client, "new@user.dev", "Password1234")
    assert body["_status"] == 201, body["_text"]
    assert body["email"] == "new@user.dev"
    assert body["is_active"] is True
    assert body["is_admin"] is False
    assert "id" in body and "created_at" in body


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await _register(client, "dup@user.dev", "Password1234")
    second = await _register(client, "dup@user.dev", "Password1234")
    assert second["_status"] == 409


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    body = await _register(client, "weak@user.dev", "short")
    assert body["_status"] in {400, 422}


# --- Login ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_returns_bearer_token(client: AsyncClient) -> None:
    await _register(client, "log@user.dev", "Password1234")
    body = await _login(client, "log@user.dev", "Password1234")
    assert body["_status"] == 200, body["_text"]
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    await _register(client, "log2@user.dev", "Password1234")
    body = await _login(client, "log2@user.dev", "WrongPassword999")
    assert body["_status"] == 401


# --- /me --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/users/me")
    assert r.status_code == 200
    assert r.json()["email"] == "routes@test.dev"


@pytest.mark.asyncio
async def test_update_me_full_name(authed_client: AsyncClient) -> None:
    r = await authed_client.patch(
        "/api/v1/users/me",
        json={"full_name": "Ada Lovelace"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_change_password_then_login(
    client: AsyncClient, authed_client: AsyncClient
) -> None:
    r = await authed_client.post(
        "/api/v1/users/me/password",
        json={"current_password": "RoutesTest1234", "new_password": "NewPassword9876"},
    )
    assert r.status_code == 204

    # Re-login with the new password succeeds.
    body = await _login(client, "routes@test.dev", "NewPassword9876")
    assert body["_status"] == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current_rejected(
    authed_client: AsyncClient,
) -> None:
    r = await authed_client.post(
        "/api/v1/users/me/password",
        json={"current_password": "wrong-current", "new_password": "NewPassword9876"},
    )
    assert r.status_code in {400, 401, 403}


# --- /me/stats and /me/token-usage ------------------------------------------


@pytest.mark.asyncio
async def test_me_stats_zero_for_fresh_user(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/users/me/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["notebooks_count"] == 0
    assert body["documents_count"] == 0
    assert body["fits_files_count"] == 0
    assert body["analyses_count"] == 0


@pytest.mark.asyncio
async def test_me_token_usage_zero_for_fresh_user(
    authed_client: AsyncClient,
) -> None:
    r = await authed_client.get("/api/v1/users/me/token-usage")
    assert r.status_code == 200
    body = r.json()
    assert body["month_total"]["total_tokens"] == 0
    assert body["window_days"] == 30
    assert len(body["daily"]) == 30
