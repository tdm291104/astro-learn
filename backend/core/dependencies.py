"""FastAPI dependency providers — the DI container."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_factory import DefaultAgentFactory
from core.config import Settings, get_settings
from core.db import AsyncSessionLocal, get_db_session
from core.exceptions import AuthenticationError, AuthorizationError
from core.llm.llm_client import LLMClient
from core.redis_client import get_redis
from core.security import decode_access_token
from core.usage_context import set_current_user_id
from memory.long_term.catalog_cache import CatalogCache
from memory.long_term.qdrant_backend import QdrantBackend
from memory.long_term.vector_store import VectorBackend, VectorStore
from memory.short_term.conversation_memory import ConversationMemory

# Imported at runtime so FastAPI can resolve CurrentUserDep annotation.
from models.user_model import UserModel
from repositories.agent_repository import AgentRepository
from repositories.analysis_repository import AnalysisRepository
from repositories.catalog_cache_repository import CatalogCacheRepository
from repositories.document_repository import DocumentRepository
from repositories.fits_file_repository import FitsFileRepository
from repositories.message_repository import MessageRepository
from repositories.notebook_artifact_repository import NotebookArtifactRepository
from repositories.notebook_repository import NotebookRepository
from repositories.report_repository import ReportRepository
from repositories.session_repository import SessionRepository
from repositories.token_usage_repository import TokenUsageRepository
from repositories.user_repository import UserRepository
from services._agent_run_recorder import AgentRunRecorder
from services.admin_service import AdminService
from services.agent_service import AgentService
from services.astronomy_service import AstronomyService
from services.catalog_commentary import CatalogCommentaryService
from services.notebook_service import NotebookService
from services.session_service import SessionService
from services.token_usage_service import TokenUsageService
from services.user_service import UserService
from services.user_stats_service import UserStatsService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session bound to the request lifecycle."""
    async for session in get_db_session():
        yield session


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Process-wide LLMClient; persists token_usage_events via usage_context."""
    return LLMClient(session_factory=AsyncSessionLocal)


@lru_cache(maxsize=1)
def get_http_client() -> httpx.AsyncClient:
    """Process-wide AsyncClient shared by tools that hit external APIs."""
    return httpx.AsyncClient(timeout=30.0)


def get_storage_root(settings: SettingsDep) -> Path:
    """Resolve `STORAGE_ROOT` from settings into an absolute Path."""
    return settings.STORAGE_ROOT.expanduser().resolve()


@lru_cache(maxsize=1)
def get_vector_backend() -> VectorBackend:
    """Construct the Qdrant-backed VectorBackend (one per process)."""
    settings = get_settings()
    return QdrantBackend(client=AsyncQdrantClient(url=settings.QDRANT_URL))


def get_vector_store(
    backend: Annotated[VectorBackend, Depends(get_vector_backend)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> VectorStore:
    """Compose VectorBackend + LLMClient into the high-level store."""
    return VectorStore(backend=backend, llm=llm)


def get_catalog_cache(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogCache:
    """Per-request CatalogCache bound to request-scoped DB session."""
    return CatalogCache(
        repo=CatalogCacheRepository(db),
        default_ttl_days=settings.CATALOG_CACHE_TTL_DAYS,
    )


def get_conversation_memory(
    redis: Annotated[Redis, Depends(get_redis)],
) -> ConversationMemory:
    """Build the Redis-backed server-side chat history for the orchestrator."""
    return ConversationMemory(redis=redis)


def get_agent_factory(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    redis: Annotated[Redis, Depends(get_redis)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    storage_root: Annotated[Path, Depends(get_storage_root)],
    catalog_cache: Annotated[CatalogCache, Depends(get_catalog_cache)],
    conversation_memory: Annotated[ConversationMemory, Depends(get_conversation_memory)],
    recorder: Annotated[AgentRunRecorder, Depends(get_agent_run_recorder)],
) -> DefaultAgentFactory:
    """Build the per-request AgentFactory."""
    return DefaultAgentFactory(
        llm=llm,
        settings=settings,
        vector_store=vector_store,
        redis=redis,
        http_client=http_client,
        storage_root=storage_root,
        catalog_cache=catalog_cache,
        conversation_memory=conversation_memory,
        session_factory=AsyncSessionLocal,
        recorder=recorder,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserModel:
    """Decode the bearer token and load the corresponding user row."""
    payload = decode_access_token(token)

    sub = payload.get("sub")
    if sub is None:
        raise AuthenticationError(
            message="Token missing subject claim",
            code="invalid_token",
        )

    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError(
            message="Token subject is not a valid user id",
            code="invalid_token",
        ) from exc

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AuthenticationError(
            message="User no longer exists",
            code="invalid_token",
        )
    if not user.is_active:
        # Distinct code so FE shows the right message.
        raise AuthenticationError(
            message="User account is disabled",
            code="user_inactive",
        )

    # ContextVar so LLM calls attribute token usage without threading user_id.
    set_current_user_id(user.id)

    return user


async def get_current_admin(
    user: Annotated[UserModel, Depends(get_current_user)],
) -> UserModel:
    """Same as `get_current_user` but rejects non-admins with 403."""
    if not user.is_admin:
        raise AuthorizationError(
            message="Admin privileges required",
            code="admin_required",
        )
    return user


def get_admin_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    storage_root: Annotated[Path, Depends(get_storage_root)],
) -> AdminService:
    return AdminService(
        users=UserRepository(db),
        token_usage=TokenUsageRepository(db),
        notebooks=NotebookRepository(db),
        documents=DocumentRepository(db),
        fits_files=FitsFileRepository(db),
        analyses=AnalysisRepository(db),
        agent_runs=AgentRepository(db),
        storage_root=storage_root,
    )


def get_user_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserService:
    return UserService(users=UserRepository(db))


def get_token_usage_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenUsageService:
    """Per-request token-usage aggregator for the dashboard endpoint."""
    return TokenUsageService(repo=TokenUsageRepository(db))


def get_user_stats_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserStatsService:
    """Dashboard counts aggregator (notebooks/documents/fits/analyses)."""
    return UserStatsService(
        notebooks=NotebookRepository(db),
        documents=DocumentRepository(db),
        fits_files=FitsFileRepository(db),
        analyses=AnalysisRepository(db),
    )


def get_session_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionService:
    return SessionService(
        sessions=SessionRepository(db),
        messages=MessageRepository(db),
    )


def get_notebook_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    factory: Annotated[DefaultAgentFactory, Depends(get_agent_factory)],
    recorder: Annotated[AgentRunRecorder, Depends(get_agent_run_recorder)],
    storage_root: Annotated[Path, Depends(get_storage_root)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> NotebookService:
    return NotebookService(
        notebooks=NotebookRepository(db),
        documents=DocumentRepository(db),
        sessions=SessionRepository(db),
        messages=MessageRepository(db),
        artifacts=NotebookArtifactRepository(db),
        factory=factory,
        recorder=recorder,
        storage_root=storage_root,
        session_factory=AsyncSessionLocal,
        vector_store=vector_store,
        llm=llm,
    )


def get_catalog_commentary_service(
    redis: Annotated[Redis, Depends(get_redis)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> CatalogCommentaryService:
    """Build the per-request catalog commentary service."""
    return CatalogCommentaryService(redis=redis, llm=llm)


def get_astronomy_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    factory: Annotated[DefaultAgentFactory, Depends(get_agent_factory)],
    recorder: Annotated[AgentRunRecorder, Depends(get_agent_run_recorder)],
    storage_root: Annotated[Path, Depends(get_storage_root)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AstronomyService:
    return AstronomyService(
        fits_files=FitsFileRepository(db),
        analyses=AnalysisRepository(db),
        reports=ReportRepository(db),
        factory=factory,
        recorder=recorder,
        storage_root=storage_root,
        llm=llm,
    )


@lru_cache(maxsize=1)
def get_agent_run_recorder() -> AgentRunRecorder:
    """Process-wide recorder; uses own sessions so status polls see mid-stream writes."""
    return AgentRunRecorder(session_factory=AsyncSessionLocal)


def get_agent_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    factory: Annotated[DefaultAgentFactory, Depends(get_agent_factory)],
    recorder: Annotated[AgentRunRecorder, Depends(get_agent_run_recorder)],
) -> AgentService:
    return AgentService(
        agent_runs=AgentRepository(db),
        sessions=SessionRepository(db),
        factory=factory,
        recorder=recorder,
        session_factory=AsyncSessionLocal,
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
CurrentUserDep = Annotated[UserModel, Depends(get_current_user)]
CurrentAdminDep = Annotated[UserModel, Depends(get_current_admin)]

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
TokenUsageServiceDep = Annotated[
    TokenUsageService, Depends(get_token_usage_service)
]
UserStatsServiceDep = Annotated[
    UserStatsService, Depends(get_user_stats_service)
]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
NotebookServiceDep = Annotated[NotebookService, Depends(get_notebook_service)]
AstronomyServiceDep = Annotated[AstronomyService, Depends(get_astronomy_service)]
CatalogCommentaryServiceDep = Annotated[
    CatalogCommentaryService, Depends(get_catalog_commentary_service)
]
AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]
AgentFactoryDep = Annotated[DefaultAgentFactory, Depends(get_agent_factory)]
