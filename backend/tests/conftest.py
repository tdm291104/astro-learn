"""Shared fixtures: DB engine + ASGI client + factory/vector stubs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from agents.base.agent_message import AgentMessage
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.config import get_settings

_TABLES_TO_WIPE = (
    "messages",
    "agent_runs",
    "sessions",
    "documents",
    "fits_files",
    "analyses",
    "reports",
    "notebook_artifacts",
    "notebooks",
    "token_usage_events",
    "users",
    # catalog_cache has no FK to users; user-CASCADE doesn't cover it.
    "catalog_cache",
)


async def _truncate(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE " + ", ".join(_TABLES_TO_WIPE) + " RESTART IDENTITY CASCADE")
        )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test NullPool engine with all app tables truncated."""
    settings = get_settings()
    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, future=True)
    await _truncate(eng)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Fake agent infrastructure for route-level tests
# ---------------------------------------------------------------------------


class _FakeAgent(BaseAgent):
    """Returns the canned output configured for `name`, or raises on demand."""

    name = "_fake"
    description = "test fake"

    def __init__(
        self,
        agent_name: str,
        output: dict[str, Any],
        raises: BaseException | None = None,
    ) -> None:
        self.name = agent_name  # type: ignore[misc]
        self._output = output
        self._raises = raises
        self.tools = {}
        self.llm = None  # type: ignore[assignment]

    async def run(
        self, task: dict[str, Any], *, state: AgentState | None = None
    ) -> AgentState:
        if self._raises is not None:
            raise self._raises
        state = state or AgentState(agent_name=self.name)
        state.final_output = self._output
        return state

    async def stream(
        self, task: dict[str, Any], *, state: AgentState | None = None
    ) -> AsyncIterator[AgentMessage]:
        if self._raises is not None:
            raise self._raises
        state = state or AgentState(agent_name=self.name)
        yield AgentMessage(role="assistant", content="fake")
        state.final_output = self._output


class FakeAgentFactory:
    """Drop-in for DefaultAgentFactory; returns canned outputs by agent name."""

    def __init__(self) -> None:
        # Defaults cover every agent the route layer exercises.
        self.outputs: dict[str, dict[str, Any]] = {
            "qa": {"answer": "stubbed answer.", "citations": []},
            "summarizer": {
                "summary": "stubbed summary.",
                "style": "bullets",
                "citations": [],
            },
            "quiz": {
                "questions": [
                    {
                        "question": "Q?",
                        "options": ["a", "b", "c", "d"],
                        "correct_index": 0,
                        "explanation": "because",
                    }
                ],
            },
            "flashcard": {"cards": [{"front": "F", "back": "B"}]},
            "catalog": {"results": [], "source": "simbad", "query": "test"},
            "catalog_chat": {"reply": "stubbed reply.", "results": []},
            "image_processor": {"summary": {}, "artifacts": []},
            "data_analyst": {"summary": {}, "artifacts": []},
            "fits_analyst": {"summary": {}, "interpretation": None, "artifacts": []},
            "orchestrator": {"reply": "stubbed reply.", "step_outputs": {}},
        }
        self._raises: dict[str, BaseException] = {}

    def set_output(self, agent_name: str, output: dict[str, Any]) -> None:
        self.outputs[agent_name] = output

    def set_raises(self, agent_name: str, exc: BaseException) -> None:
        self._raises[agent_name] = exc

    def __call__(self, agent_name: str) -> _FakeAgent:
        # Mirror DefaultAgentFactory: a real lookup raises AgentNotFoundError.
        from agents.base.agent_registry import AgentRegistry

        AgentRegistry.get(agent_name)
        return _FakeAgent(
            agent_name,
            self.outputs.get(agent_name, {}),
            raises=self._raises.get(agent_name),
        )


class _FakeVectorStore:
    """No-op stand-in for memory.long_term.vector_store.VectorStore."""

    async def index_document(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def delete_notebook(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def delete_document(self, *args: Any, **kwargs: Any) -> int:
        return 0


@pytest.fixture
def fake_factory() -> FakeAgentFactory:
    """Per-test FakeAgentFactory; tests can set_output() to vary."""
    return FakeAgentFactory()


@pytest.fixture
def fake_vector_store() -> _FakeVectorStore:
    return _FakeVectorStore()


# ---------------------------------------------------------------------------
# ASGI client + auth
# ---------------------------------------------------------------------------


def _install_overrides(
    factory: FakeAgentFactory | None,
    vector: _FakeVectorStore | None,
) -> dict[Any, Any]:
    from core.dependencies import get_agent_factory, get_vector_store
    from main import app

    saved = dict(app.dependency_overrides)
    if factory is not None:
        app.dependency_overrides[get_agent_factory] = lambda: factory
    if vector is not None:
        app.dependency_overrides[get_vector_store] = lambda: vector
    return saved


@pytest_asyncio.fixture
async def client(
    fake_factory: FakeAgentFactory,
    fake_vector_store: _FakeVectorStore,
) -> AsyncIterator[AsyncClient]:
    """ASGI client with fakes wired in; uses the real app engine."""
    from core.db import engine as app_engine
    from main import app

    await _truncate(app_engine)
    saved = _install_overrides(fake_factory, fake_vector_store)

    # raise_app_exceptions=False so registered handlers run.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient) -> AsyncClient:
    """ASGI client pre-loaded with a bearer token for a fresh user."""
    email = "routes@test.dev"
    password = "RoutesTest1234"
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
    token = r.json()["access_token"]

    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def celery_eager(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Patch Celery `.delay()` so service tests never enqueue real work."""
    # Patches the import sites used by NotebookService and AstronomyService.
    from services import notebook_service

    stubs: dict[str, MagicMock] = {}
    for name in ("index_document", "generate_learning_pack", "generate_study_pack"):
        task = MagicMock()
        task.delay = MagicMock(return_value=None)
        monkeypatch.setattr(notebook_service, name, task)
        stubs[name] = task

    # Astronomy service queues ingest_fits + run_analysis.
    from services import astronomy_service

    for name in ("ingest_fits", "run_analysis"):
        task = MagicMock()
        task.delay = MagicMock(return_value=None)
        monkeypatch.setattr(astronomy_service, name, task)
        stubs[name] = task

    return stubs
