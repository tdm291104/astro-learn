"""End-to-end tests for /api/v1/notebooks/* — CRUD, upload, NotebookLM, share."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import FakeAgentFactory

# --- CRUD -------------------------------------------------------------------


async def _create(client: AsyncClient, title: str = "NB", description: str | None = None) -> dict:
    r = await client.post(
        "/api/v1/notebooks/",
        json={"title": title, "description": description},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_notebooks_require_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/notebooks/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_then_list_returns_notebook(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client, title="My NB")
    assert nb["title"] == "My NB"

    r = await authed_client.get("/api/v1/notebooks/")
    assert r.status_code == 200
    titles = [n["title"] for n in r.json()]
    assert "My NB" in titles


@pytest.mark.asyncio
async def test_get_notebook_owner_only(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r = await authed_client.get(f"/api/v1/notebooks/{nb['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == nb["id"]


@pytest.mark.asyncio
async def test_other_user_cannot_access_notebook(client: AsyncClient) -> None:
    # User A creates a notebook
    await client.post(
        "/api/v1/users/register",
        json={"email": "a@nb.dev", "password": "Password1234"},
    )
    r = await client.post(
        "/api/v1/users/login",
        data={"username": "a@nb.dev", "password": "Password1234"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    a_token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {a_token}"
    nb = await _create(client, title="A's secret")

    # User B logs in
    await client.post(
        "/api/v1/users/register",
        json={"email": "b@nb.dev", "password": "Password1234"},
    )
    r = await client.post(
        "/api/v1/users/login",
        data={"username": "b@nb.dev", "password": "Password1234"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    b_token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {b_token}"

    r = await client.get(f"/api/v1/notebooks/{nb['id']}")
    assert r.status_code in {403, 404}


@pytest.mark.asyncio
async def test_update_and_delete_notebook(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r = await authed_client.patch(
        f"/api/v1/notebooks/{nb['id']}",
        json={"title": "Renamed"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"

    r = await authed_client.delete(f"/api/v1/notebooks/{nb['id']}")
    assert r.status_code == 204

    r = await authed_client.get(f"/api/v1/notebooks/{nb['id']}")
    assert r.status_code == 404


# --- Upload (Celery is stubbed) ---------------------------------------------


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(
    authed_client: AsyncClient,
    celery_eager: dict,
) -> None:
    nb = await _create(authed_client)
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/upload",
        files={"file": ("notes.exe", b"\x00\x00", "application/octet-stream")},
    )
    assert r.status_code in {400, 422}


@pytest.mark.asyncio
async def test_upload_pdf_enqueues_indexing(
    authed_client: AsyncClient,
    celery_eager: dict,
) -> None:
    nb = await _create(authed_client)
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/upload",
        files={"file": ("notes.pdf", b"%PDF-1.4\n%fake", "application/pdf")},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert celery_eager["index_document"].delay.called


# --- NotebookLM (Q&A, summarize, quiz, flashcards) --------------------------


@pytest.mark.asyncio
async def test_run_qa_returns_stubbed_answer(
    authed_client: AsyncClient, fake_factory: FakeAgentFactory
) -> None:
    nb = await _create(authed_client)
    fake_factory.set_output(
        "qa", {"answer": "Mercury is hot.", "citations": []}
    )
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/qa",
        json={"question": "What is Mercury?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Mercury is hot."
    assert "session_id" in body


@pytest.mark.asyncio
async def test_run_summarize(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/summarize",
        json={"style": "bullets"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_run_quiz(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/quiz",
        json={"n_questions": 1, "difficulty": "easy"},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["questions"]) >= 1


@pytest.mark.asyncio
async def test_run_flashcards(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/flashcards",
        json={"n_cards": 1},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["cards"]) >= 1


@pytest.mark.asyncio
async def test_artifact_returns_null_before_generation(
    authed_client: AsyncClient,
) -> None:
    nb = await _create(authed_client)
    r = await authed_client.get(f"/api/v1/notebooks/{nb['id']}/artifacts/quiz")
    assert r.status_code == 200
    assert r.json() is None


# --- Document content viewer ------------------------------------------------


@pytest.mark.asyncio
async def test_get_document_content_returns_txt_inline(
    authed_client: AsyncClient,
    celery_eager: dict,
) -> None:
    nb = await _create(authed_client)
    # Astronomy text so the upload-time relevance gate accepts the file.
    payload = b"Andromeda galaxy is the nearest spiral galaxy to the Milky Way."
    r = await authed_client.post(
        f"/api/v1/notebooks/{nb['id']}/upload",
        files={"file": ("notes.txt", payload, "text/plain")},
    )
    assert r.status_code == 202, r.text
    doc_id = r.json()["document_id"]

    r = await authed_client.get(
        f"/api/v1/notebooks/{nb['id']}/documents/{doc_id}/content",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "notes.txt"
    assert body["content"] == payload.decode()
    assert body["truncated"] is False
    assert body["pages"] is None


@pytest.mark.asyncio
async def test_get_document_content_missing_returns_404(
    authed_client: AsyncClient,
) -> None:
    nb = await _create(authed_client)
    bogus = "00000000-0000-0000-0000-000000000000"
    r = await authed_client.get(
        f"/api/v1/notebooks/{nb['id']}/documents/{bogus}/content",
    )
    assert r.status_code == 404


# --- Share link -------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_link_is_idempotent(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    r1 = await authed_client.post(f"/api/v1/notebooks/{nb['id']}/share")
    assert r1.status_code == 200, r1.text
    r2 = await authed_client.post(f"/api/v1/notebooks/{nb['id']}/share")
    assert r2.status_code == 200
    assert r1.json()["share_token"] == r2.json()["share_token"]


@pytest.mark.asyncio
async def test_revoke_share_link(authed_client: AsyncClient) -> None:
    nb = await _create(authed_client)
    await authed_client.post(f"/api/v1/notebooks/{nb['id']}/share")
    r = await authed_client.delete(f"/api/v1/notebooks/{nb['id']}/share")
    assert r.status_code == 204
