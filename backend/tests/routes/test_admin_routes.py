"""End-to-end tests for /api/v1/admin/* routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from core.db import AsyncSessionLocal


async def _login(client: AsyncClient, email: str, password: str) -> str:
    """Register + log in; returns a bearer token."""
    r = await client.post(
        "/api/v1/users/register",
        json={"email": email, "password": password},
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        "/api/v1/users/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _promote_to_admin(email: str) -> None:
    """Flip is_admin = true directly in the DB (mirrors the CLI script)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE users SET is_admin = true WHERE email = :email"),
            {"email": email},
        )
        await session.commit()


@pytest.fixture
async def admin_token(client: AsyncClient) -> str:
    """Register an admin user and yield the bearer token."""
    email = "admin@routes.dev"
    token = await _login(client, email, "AdminPass1234")
    await _promote_to_admin(email)
    # Token still encodes the same user-id; on the next request the loader
    # re-reads `is_admin` from the DB, so promotion takes effect immediately.
    return token


@pytest.fixture
async def regular_token(client: AsyncClient) -> str:
    """Register a normal user and yield the bearer token."""
    return await _login(client, "regular@routes.dev", "RegularPass1234")


# ---------- Authorization ---------------------------------------------------


@pytest.mark.asyncio
async def test_admin_routes_reject_unauthenticated(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_routes_reject_non_admin(
    client: AsyncClient, regular_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {regular_token}"
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 403
    # Envelope from core.exceptions.AuthorizationError.
    assert r.json()["error"]["code"] == "admin_required"


@pytest.mark.asyncio
async def test_admin_routes_admin_can_list_users(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # The admin itself is in the list.
    assert any(u["email"] == "admin@routes.dev" for u in body["items"])


# ---------- Search / filter -------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_users_supports_search(
    client: AsyncClient, admin_token: str
) -> None:
    # Add a couple of extra users so the search has something to discriminate.
    await _login(client, "alice@search.dev", "alicepass1234")
    await _login(client, "bob@search.dev", "bobpass1234")

    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/users", params={"q": "alice"})
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()["items"]}
    assert emails == {"alice@search.dev"}


@pytest.mark.asyncio
async def test_admin_list_users_filters_admin_only(
    client: AsyncClient, admin_token: str
) -> None:
    await _login(client, "user1@filter.dev", "passpass1234")
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get(
        "/api/v1/admin/users", params={"is_admin": "true"}
    )
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()["items"]}
    assert emails == {"admin@routes.dev"}


# ---------- Update / delete -------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_update_other_user(
    client: AsyncClient, admin_token: str
) -> None:
    # Create a target user, then PATCH it as admin.
    await _login(client, "target@routes.dev", "TargetPass1234")
    # Look up the target's id via the admin list.
    client.headers["Authorization"] = f"Bearer {admin_token}"
    listing = await client.get(
        "/api/v1/admin/users", params={"q": "target@routes.dev"}
    )
    target_id = listing.json()["items"][0]["id"]

    r = await client.patch(
        f"/api/v1/admin/users/{target_id}",
        json={
            "full_name": "Promoted",
            "is_admin": True,
            "is_active": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Promoted"
    assert body["is_admin"] is True


@pytest.mark.asyncio
async def test_admin_cannot_demote_self(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    # Discover the admin's own id from /users/me.
    me = await client.get("/api/v1/users/me")
    admin_id = me.json()["id"]

    r = await client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"is_admin": False}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "self_demote_forbidden"


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    me = await client.get("/api/v1/users/me")
    admin_id = me.json()["id"]

    r = await client.delete(f"/api/v1/admin/users/{admin_id}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "self_delete_forbidden"


@pytest.mark.asyncio
async def test_admin_can_delete_other_user(
    client: AsyncClient, admin_token: str
) -> None:
    await _login(client, "doomed@routes.dev", "DoomedPass1234")
    client.headers["Authorization"] = f"Bearer {admin_token}"
    listing = await client.get(
        "/api/v1/admin/users", params={"q": "doomed@routes.dev"}
    )
    target_id = listing.json()["items"][0]["id"]

    r = await client.delete(f"/api/v1/admin/users/{target_id}")
    assert r.status_code == 204

    # Subsequent GET on the user's id returns 404 from the detail route.
    r2 = await client.get(f"/api/v1/admin/users/{target_id}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_unknown_user_returns_404(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.delete(f"/api/v1/admin/users/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "user_not_found"


# ---------- Stats overview --------------------------------------------------


@pytest.mark.asyncio
async def test_admin_stats_overview_returns_zeroes_with_no_usage(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/stats/overview", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 7
    assert len(body["daily"]) == 7
    assert body["total_users"] >= 1
    assert body["admin_users"] >= 1
    assert body["month_total"]["total_tokens"] == 0


@pytest.mark.asyncio
async def test_admin_user_detail_endpoint(
    client: AsyncClient, admin_token: str
) -> None:
    await _login(client, "detail@routes.dev", "DetailPass1234")
    client.headers["Authorization"] = f"Bearer {admin_token}"
    listing = await client.get(
        "/api/v1/admin/users", params={"q": "detail@routes.dev"}
    )
    target_id = listing.json()["items"][0]["id"]

    r = await client.get(f"/api/v1/admin/users/{target_id}", params={"days": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "detail@routes.dev"
    assert body["window_days"] == 14
    assert len(body["daily"]) == 14
    assert body["notebooks_count"] == 0


# ---------- Plumbing regression --------------------------------------------


@pytest.mark.asyncio
async def test_register_returns_is_admin_false(client: AsyncClient) -> None:
    """Regression: the 500 the user reported when the migration was missing."""
    r = await client.post(
        "/api/v1/users/register",
        json={"email": "newbie@routes.dev", "password": "NewbiePass1234"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_admin"] is False
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_users_me_exposes_is_admin(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 200
    assert r.json()["is_admin"] is True


# ---------- New feature endpoints ------------------------------------------


@pytest.mark.asyncio
async def test_agent_runs_route_returns_empty_list_when_none(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/agent-runs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["status_counts"] == {}


@pytest.mark.asyncio
async def test_agent_runs_route_returns_404_for_unknown_run(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get(f"/api/v1/admin/agent-runs/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "agent_run_not_found"


@pytest.mark.asyncio
async def test_agent_runs_route_rejects_non_admin(
    client: AsyncClient, regular_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {regular_token}"
    r = await client.get("/api/v1/admin/agent-runs")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cost_breakdown_route_returns_zero_with_no_usage(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/stats/cost-breakdown", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 7
    assert body["total_cost_usd"] == 0.0
    assert body["total_tokens"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_cost_breakdown_route_rejects_non_admin(
    client: AsyncClient, regular_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {regular_token}"
    r = await client.get("/api/v1/admin/stats/cost-breakdown")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_notebooks_list_empty(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/notebooks")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_admin_notebooks_delete_unknown_returns_404(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.delete(f"/api/v1/admin/notebooks/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_admin_fits_list_returns_storage_total(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.get("/api/v1/admin/fits")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["total_storage_bytes"] == 0


@pytest.mark.asyncio
async def test_admin_fits_delete_unknown_returns_404(
    client: AsyncClient, admin_token: str
) -> None:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    r = await client.delete(f"/api/v1/admin/fits/{uuid.uuid4()}")
    assert r.status_code == 404
