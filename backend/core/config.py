"""Application settings loaded from .env via Pydantic BaseSettings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the AstroLearn backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: Literal["development", "staging", "production"] = "development"
    SECRET_KEY: str = Field(..., min_length=16)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    DATABASE_URL: str

    REDIS_URL: str = "redis://localhost:6379/0"
    # Kill switch; orchestrator falls back to task["history"] when False.
    ENABLE_CHAT_HISTORY_MEMORY: bool = True

    QDRANT_URL: str = "http://localhost:6333"

    # Virtual alias defined in configs/litellm.yaml; switch providers there.
    # `openai/` prefix is routing metadata for the OpenAI-compatible client.
    LLM_MODEL: str = "openai/astrolearn-llm"
    # Faster/cheaper alias for non-critical paths (quiz/flashcards/summary).
    LLM_FAST_MODEL: str = "openai/astrolearn-llm-fast"
    LLM_FALLBACK_MODELS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT: int = 60
    LLM_BASE_URL: str | None = "http://localhost:4000"
    LLM_API_KEY: str | None = None  # LiteLLM master key (Bearer token)

    # Provider keys live on the LiteLLM proxy; kept here for legacy scripts.
    GROQ_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    EMBEDDING_MODEL: str = "openai/astrolearn-embedding"
    # Cross-encoder reranker (LiteLLM proxy alias). Hit by LLMClient.rerank()
    # via the proxy's /v1/rerank endpoint (Cohere-compatible API), not via
    # the openai-compat path — hence no "openai/" prefix here.
    RERANKER_MODEL: str = "astrolearn-reranker"
    # Two-stage retrieval: pull top_k * this many candidates, rerank to top_k.
    # 4x is the sweet spot from the retrieval eval (recall@40 ~ recall@10 unranked).
    RERANK_CANDIDATE_MULTIPLIER: int = 4

    STORAGE_ROOT: Path = Path("./var/storage")

    NASA_API_KEY: str | None = None
    # Catalog positions are stable; TTL balances dev/test drift.
    CATALOG_CACHE_TTL_DAYS: int = 7

    TAVILY_API_KEY: str | None = None
    SERPAPI_API_KEY: str | None = None

    @field_validator("LLM_FALLBACK_MODELS", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated string from .env and split into a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()  # type: ignore[call-arg]


# Singleton for non-DI consumers; routes/services use Depends(get_settings).
settings: Settings = get_settings()
