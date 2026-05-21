"""LLM pricing reference (USD per 1M tokens) for admin cost breakdown."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ModelPrice:
    """Per-million-token rates in USD."""

    prompt_per_million: float
    completion_per_million: float


# Lowercase keys; unknown models report 0 to avoid overstating spend.
_PRICES: dict[str, ModelPrice] = {
    "groq/llama-3.3-70b-versatile": ModelPrice(0.0, 0.0),
    "llama-3.3-70b-versatile": ModelPrice(0.0, 0.0),
    "anthropic/claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "anthropic/claude-opus-4-7": ModelPrice(15.0, 75.0),
    "claude-opus-4-7": ModelPrice(15.0, 75.0),
    "anthropic/claude-haiku-4-5": ModelPrice(0.80, 4.0),
    "claude-haiku-4-5": ModelPrice(0.80, 4.0),
    "openai/gpt-4o": ModelPrice(2.50, 10.0),
    "gpt-4o": ModelPrice(2.50, 10.0),
    "openai/gpt-4o-mini": ModelPrice(0.15, 0.60),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
}


def estimate_cost_usd(
    model: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Return estimated USD spend; unknown models return 0.0 (visible in chart)."""
    price = _PRICES.get(model.lower().strip())
    if price is None:
        return 0.0
    return (
        prompt_tokens * price.prompt_per_million / 1_000_000.0
        + completion_tokens * price.completion_per_million / 1_000_000.0
    )


def known_models() -> tuple[str, ...]:
    """Sorted list of model keys with a known price (for diagnostics)."""
    return tuple(sorted(_PRICES.keys()))
