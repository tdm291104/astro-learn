"""Dependency providers for Celery workers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from core.agent_factory import DefaultAgentFactory
from core.config import Settings, get_settings
from core.llm.llm_client import LLMClient
from core.redis_client import redis_client as _shared_redis_client
from memory.long_term.qdrant_backend import QdrantBackend
from memory.long_term.vector_store import VectorStore
from tools.astronomy.fits_reader_tool import FitsReaderTool
from tools.knowledge.pdf_parser_tool import PdfParserTool


def get_worker_settings() -> Settings:
    return get_settings()


def get_worker_storage_root() -> Path:
    return get_settings().STORAGE_ROOT.expanduser().resolve()


# Session factory built per-task via core.db.task_session_factory (avoids loop reuse).


@lru_cache(maxsize=1)
def get_worker_llm_client() -> LLMClient:
    return LLMClient()


@lru_cache(maxsize=1)
def get_worker_qdrant_backend() -> QdrantBackend:
    return QdrantBackend(client=AsyncQdrantClient(url=get_settings().QDRANT_URL))


@lru_cache(maxsize=1)
def get_worker_vector_store() -> VectorStore:
    return VectorStore(
        backend=get_worker_qdrant_backend(),
        llm=get_worker_llm_client(),
    )


@lru_cache(maxsize=1)
def get_worker_pdf_parser() -> PdfParserTool:
    return PdfParserTool(storage_root=get_worker_storage_root())


@lru_cache(maxsize=1)
def get_worker_fits_reader() -> FitsReaderTool:
    return FitsReaderTool(storage_root=get_worker_storage_root())


def get_worker_redis() -> Redis:
    return _shared_redis_client


@lru_cache(maxsize=1)
def get_worker_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


@lru_cache(maxsize=1)
def get_worker_agent_factory() -> DefaultAgentFactory:
    """DefaultAgentFactory wired with worker-scoped deps."""
    return DefaultAgentFactory(
        llm=get_worker_llm_client(),
        settings=get_worker_settings(),
        vector_store=get_worker_vector_store(),
        redis=get_worker_redis(),
        http_client=get_worker_http_client(),
        storage_root=get_worker_storage_root(),
    )
