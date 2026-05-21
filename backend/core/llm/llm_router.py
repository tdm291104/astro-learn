"""Centralised LLM model resolution per purpose so agents stay declarative."""

from __future__ import annotations

from enum import StrEnum

from core.config import Settings, get_settings


class ModelPurpose(StrEnum):
    """Logical task types mapped to concrete models in `resolve_model`."""

    DEFAULT = "default"
    ROUTING = "routing"
    REASONING = "reasoning"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"


def resolve_model(
    purpose: ModelPurpose = ModelPurpose.DEFAULT,
    *,
    settings: Settings | None = None,
) -> str:
    """Return a LiteLLM-format model id for the given purpose."""
    ...


def fallback_chain(settings: Settings | None = None) -> list[str]:
    """Return the configured fallback model list for retries."""
    settings = settings or get_settings()
    return list(settings.LLM_FALLBACK_MODELS)
