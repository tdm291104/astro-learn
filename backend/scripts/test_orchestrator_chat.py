"""Smoke test for the orchestrator's chat and off-topic intent paths."""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


CASES: list[dict[str, Any]] = [
    {
        "name": "1. Greeting (chat)",
        "task": {"query": "Hello"},
        "expect_mode": "chat",
    },
    {
        "name": "2. Capability question (chat)",
        "task": {"query": "What can you do?"},
        "expect_mode": "chat",
    },
    {
        "name": "3. Astronomy fact (chat)",
        "task": {"query": "What is a black hole?"},
        # "black hole" matches the keyword regex → clear_signal → catalog.
        # Acceptable either way: catalog miss falls back to assistant message.
        "expect_mode": "any",
    },
    {
        "name": "4. Off-topic (poem)",
        "task": {"query": "Write me a poem about love"},
        "expect_mode": "off_topic",
    },
    {
        "name": "5. Off-topic (unrelated homework)",
        "task": {"query": "Help me with my Python homework on web scraping"},
        "expect_mode": "off_topic",
    },
    {
        "name": "6. Task w/ clear signal",
        "task": {"query": "Tell me about M31"},
        # 'M\d+' keyword → clear_signal → routes to catalog rule.
        "expect_mode": "task",
    },
]


async def register_and_login(client: httpx.AsyncClient) -> str:
    email = f"orchchat+{int(time.time())}@example.com"
    password = "test-password-123"
    r = await client.post(
        f"{API}/users/register",
        json={"email": email, "password": password, "full_name": "Orch Chat"},
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"register failed: {r.status_code} {r.text}")
    r = await client.post(
        f"{API}/users/login",
        data={"username": email, "password": password},
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


async def run_case(
    client: httpx.AsyncClient, task: dict[str, Any]
) -> dict[str, Any]:
    r = await client.post(
        f"{API}/agents/run",
        json={"agent_name": "orchestrator", "task_input": task, "stream": False},
    )
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text}
    body["_http_status"] = r.status_code
    return body


def summarize(body: dict[str, Any]) -> dict[str, Any]:
    output = body.get("output") or {}
    mode = output.get("mode") if isinstance(output, dict) else None
    response = output.get("response") if isinstance(output, dict) else None
    step_outputs = output.get("step_outputs") if isinstance(output, dict) else None
    sub_agents: list[str] = []
    if isinstance(step_outputs, dict):
        for key in step_outputs.keys():
            parts = key.split("_", 2)
            sub_agents.append(parts[2] if len(parts) == 3 else key)
    return {
        "http": body.get("_http_status"),
        "status": body.get("status"),
        "mode": mode,
        "sub_agents": sub_agents,
        "response_preview": (str(response)[:160] if response else None),
        "error": body.get("error"),
    }


async def main() -> int:
    print("=" * 78)
    print("Orchestrator chat / off-topic smoke test")
    print("=" * 78)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(f"{BASE_URL}/health")
            r.raise_for_status()
        except Exception as exc:
            print(f"backend not reachable: {exc}")
            return 2

        print("\nauth bootstrap...")
        token = await register_and_login(client)
        client.headers["Authorization"] = f"Bearer {token}"

        for case in CASES:
            t0 = time.monotonic()
            try:
                body = await run_case(client, case["task"])
            except Exception as exc:
                body = {
                    "_http_status": "exc",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "output": None,
                }
            dt_ms = int((time.monotonic() - t0) * 1000)
            r = summarize(body)
            print(f"\n--- {case['name']} ---")
            print(f"  task:       {case['task']}")
            print(f"  expected:   mode={case['expect_mode']}")
            print(f"  http:       {r['http']}")
            print(f"  status:     {r['status']}")
            print(f"  mode:       {r['mode']!r}")
            print(f"  sub-agents: {r['sub_agents'] or '(none)'}")
            if r["response_preview"]:
                print(f"  response:   {r['response_preview']}")
            if r["error"]:
                print(f"  error:      {str(r['error'])[:200]}")
            print(f"  wall:       {dt_ms} ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
