"""End-to-end tests for GET /api/v1/users/me/cost-breakdown."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from core.db import AsyncSessionLocal


async def _register_and_login(
    client: AsyncClient, email: str, password: str
) -> str:
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


async def _record_usage(
    email: str,
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Insert a token_usage_events row for the user with `email`."""
    async with AsyncSessionLocal() as session:
        total = prompt_tokens + completion_tokens
        await session.execute(
            text(
                """
                INSERT INTO token_usage_events
                    (id, user_id, model, prompt_tokens, completion_tokens, total_tokens, created_at)
                SELECT
                    gen_random_uuid(), u.id, :model, :prompt, :completion, :total, NOW()
                FROM users u
                WHERE u.email = :email
                """
            ),
            {
                "model": model,
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total,
                "email": email,
            },
        )
        await session.commit()


@pytest.mark.asyncio
async def test_cost_breakdown_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users/me/cost-breakdown")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_cost_breakdown_empty_when_no_usage(client: AsyncClient) -> None:
    token = await _register_and_login(client, "empty@cb.dev", "Password1234")
    client.headers["Authorization"] = f"Bearer {token}"

    r = await client.get("/api/v1/users/me/cost-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tokens"] == 0
    assert body["total_cost_usd"] == 0.0
    assert body["items"] == []
    assert body["window_days"] == 30


@pytest.mark.asyncio
async def test_cost_breakdown_only_returns_callers_events(
    client: AsyncClient,
) -> None:
    """Tenancy check: another user's usage must not leak into the response."""
    alice_token = await _register_and_login(client, "alice@cb.dev", "Password1234")
    await _register_and_login(client, "bob@cb.dev", "Password1234")

    # Alice does an expensive GPT-4o call.
    await _record_usage(
        "alice@cb.dev",
        model="openai/gpt-4o",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    # Bob does a separate (free) Groq call — must not appear in Alice's view.
    await _record_usage(
        "bob@cb.dev",
        model="groq/llama-3.3-70b-versatile",
        prompt_tokens=500_000,
        completion_tokens=500_000,
    )

    client.headers["Authorization"] = f"Bearer {alice_token}"
    r = await client.get("/api/v1/users/me/cost-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tokens"] == 2_000_000
    assert body["total_cost_usd"] == pytest.approx(12.5, abs=0.01)
    assert {row["model"] for row in body["items"]} == {"openai/gpt-4o"}


@pytest.mark.asyncio
async def test_cost_breakdown_respects_days_param(client: AsyncClient) -> None:
    token = await _register_and_login(client, "days@cb.dev", "Password1234")
    client.headers["Authorization"] = f"Bearer {token}"

    r = await client.get(
        "/api/v1/users/me/cost-breakdown", params={"days": 7}
    )
    assert r.status_code == 200
    assert r.json()["window_days"] == 7


@pytest.mark.asyncio
async def test_cost_breakdown_unknown_model_zero_cost(
    client: AsyncClient,
) -> None:
    """Defensive: an unmapped model surfaces tokens but $0 cost (no extrapolation)."""
    token = await _register_and_login(client, "unk@cb.dev", "Password1234")
    await _record_usage(
        "unk@cb.dev",
        model="not-a-real-model-99b",
        prompt_tokens=10_000,
        completion_tokens=5_000,
    )

    client.headers["Authorization"] = f"Bearer {token}"
    r = await client.get("/api/v1/users/me/cost-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tokens"] == 15_000
    assert body["total_cost_usd"] == 0.0
    assert body["items"][0]["model"] == "not-a-real-model-99b"
    assert body["items"][0]["cost_usd"] == 0.0
