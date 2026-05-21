"""End-to-end smoke test for PDF upload, indexing, and notebook ops."""

from __future__ import annotations

import asyncio
import pathlib
import time

import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
TEST_FILE = pathlib.Path(r"C:\Users\ACER\Downloads\2605.04220v1.pdf")

pytestmark = pytest.mark.live


async def _run_workflow() -> None:
    async with httpx.AsyncClient(timeout=120) as c:

        email = f"workflow_test_{int(time.time())}@test.com"
        r = await c.post(
            f"{BASE}/users/register",
            json={"email": email, "password": "testpass123"},
        )
        assert r.status_code == 201, f"Register failed: {r.text}"
        print(f"[1] Register OK: {email}")

        r = await c.post(
            f"{BASE}/users/login",
            data={"username": email, "password": "testpass123"},
        )
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[2] Login OK, token: {token[:20]}...")

        r = await c.post(
            f"{BASE}/notebooks/",
            json={"title": "Workflow Test", "description": "e2e test"},
            headers=headers,
        )
        assert r.status_code == 201, f"Create notebook failed: {r.text}"
        nb_id = r.json()["id"]
        print(f"[3] Notebook created: {nb_id}")

        assert TEST_FILE.exists(), f"File not found: {TEST_FILE}"
        with open(TEST_FILE, "rb") as f:
            r = await c.post(
                f"{BASE}/notebooks/{nb_id}/upload",
                files={"file": (TEST_FILE.name, f, "application/pdf")},
                headers=headers,
            )
        assert r.status_code == 202, f"Upload failed: {r.text}"
        doc = r.json()
        doc_id = doc["document_id"]
        print(f"[4] Upload OK: {doc_id}, status: {doc['status']}")

        # Poll indexing status (max 3 minutes).
        print("[5] Polling indexing status...")
        chunks = None
        for i in range(60):
            await asyncio.sleep(3)
            r = await c.get(f"{BASE}/notebooks/{nb_id}/documents", headers=headers)
            assert r.status_code == 200
            docs = r.json()
            status = docs[0]["status"] if docs else "unknown"
            chunks = docs[0].get("indexed_chunks")
            print(f"    [{i*3}s] status={status}, chunks={chunks}")
            if status == "indexed":
                print(f"[5] INDEXED OK: {chunks} chunks")
                break
            if status == "failed":
                pytest.fail(f"Indexing failed: {docs[0].get('error')}")
        else:
            pytest.fail("Indexing timed out after 3 minutes")

        print("[6] Sending QA request...")
        r = await c.post(
            f"{BASE}/notebooks/{nb_id}/qa",
            json={"question": "What is the main topic of this paper?"},
            headers=headers,
            timeout=60,
        )
        assert r.status_code == 200, f"QA failed: {r.text}"
        qa = r.json()
        print("[6] QA OK:")
        print(f"    Answer: {qa.get('answer', '')[:200]}")
        print(f"    Citations: {len(qa.get('citations', []))}")

        print("[7] Generating summary...")
        r = await c.post(
            f"{BASE}/notebooks/{nb_id}/summarize",
            json={"style": "bullets", "max_bullets": 5},
            headers=headers,
            timeout=60,
        )
        assert r.status_code == 200, f"Summarize failed: {r.text}"
        summary = r.json()
        bullets = summary.get("summary", [])
        print(f"[7] Summary OK: {len(bullets)} bullets")
        for b in bullets[:3]:
            print(f"    - {b[:100]}")

        print("[8] Generating quiz...")
        r = await c.post(
            f"{BASE}/notebooks/{nb_id}/quiz",
            json={"n_questions": 3, "difficulty": "medium"},
            headers=headers,
            timeout=60,
        )
        assert r.status_code == 200, f"Quiz failed: {r.text}"
        quiz = r.json()
        questions = quiz.get("questions", [])
        print(f"[8] Quiz OK: {len(questions)} questions")
        if questions:
            print(f"    Q1: {questions[0]['question'][:100]}")

        print("\n=== WORKFLOW TEST PASSED ===")
        print(f"Notebook: {nb_id}")
        print(f"Document: {doc_id} ({chunks} chunks indexed)")
        print(f"QA: answered with {len(qa.get('citations', []))} citations")
        print(f"Summary: {len(bullets)} bullets")
        print(f"Quiz: {len(questions)} questions")


async def test_index_pdf_end_to_end() -> None:
    """Pytest entrypoint that runs the full workflow against a live stack."""
    await _run_workflow()


if __name__ == "__main__":
    asyncio.run(_run_workflow())
