"""Latency benchmark for the primary vs fast LLM aliases."""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from typing import Any

# Run from the `backend/` directory so the package imports resolve.
sys.path.insert(0, ".")

from core.config import get_settings
from core.llm.llm_client import LLMClient

# Three small prompts representative of the non-critical paths;
# kept short so wall clock is dominated by the model, not prompt size.
_PROMPTS: list[dict[str, Any]] = [
    {
        "label": "summary (5 bullets)",
        "messages": [
            {
                "role": "system",
                "content": "Summarise the user input as up to 5 bullets.",
            },
            {
                "role": "user",
                "content": (
                    "Andromeda (M31) is the nearest large spiral galaxy. "
                    "It's about 2.5 million light-years away, contains "
                    "roughly one trillion stars, and is on a collision "
                    "course with the Milky Way in ~4.5 billion years."
                ),
            },
        ],
    },
    {
        "label": "quiz (3 MCQs)",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Generate 3 multiple-choice questions about the user "
                    'input. Return JSON: {"questions": [...]} with 4 '
                    "options and correct_index per question."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Black holes are regions of spacetime where gravity "
                    "is so strong that not even light can escape past "
                    "the event horizon."
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    },
    {
        "label": "flashcard (3 cards)",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Produce 3 flashcards (front + back) covering the "
                    'user input. Return JSON: {"cards": [...]}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    "A pulsar is a highly magnetised rotating neutron "
                    "star that emits beams of electromagnetic radiation."
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    },
]

# 3 runs balances Groq free-tier rate limits with a sample size big
# enough to spot obvious latency differences (70B vs 8B gap is wide).
_SAMPLES_PER_PROMPT = 3


async def _time_call(
    llm: LLMClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
) -> tuple[float, int]:
    """Issue one completion and return (seconds, response_char_count)."""
    kwargs: dict[str, Any] = {"model": model, "temperature": 0.3, "max_tokens": 400}
    if response_format is not None:
        kwargs["response_format"] = response_format
    start = time.perf_counter()
    out = await llm.complete(messages, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed, len(out or "")


async def _bench(model: str) -> dict[str, list[float]]:
    """Run every prompt N times against model and return per-prompt timings."""
    llm = LLMClient(settings=get_settings())
    results: dict[str, list[float]] = {}
    for prompt in _PROMPTS:
        label = prompt["label"]
        samples: list[float] = []
        for i in range(_SAMPLES_PER_PROMPT):
            try:
                seconds, char_count = await _time_call(
                    llm,
                    model=model,
                    messages=prompt["messages"],
                    response_format=prompt.get("response_format"),
                )
            except Exception as exc:
                print(f"  [{label} run {i + 1}/{_SAMPLES_PER_PROMPT}] FAILED: {exc}")
                continue
            samples.append(seconds)
            print(f"  [{label} run {i + 1}/{_SAMPLES_PER_PROMPT}] {seconds:.2f}s ({char_count} chars)")
        results[label] = samples
    return results


def _summarise(label: str, timings: dict[str, list[float]]) -> None:
    print(f"\n--- {label} ---")
    for prompt_label, samples in timings.items():
        if not samples:
            print(f"  {prompt_label}: no successful runs")
            continue
        mean = statistics.mean(samples)
        best = min(samples)
        worst = max(samples)
        print(
            f"  {prompt_label}: mean={mean:.2f}s  min={best:.2f}s  max={worst:.2f}s  "
            f"(n={len(samples)})"
        )


def _diff(
    primary: dict[str, list[float]],
    fast: dict[str, list[float]],
) -> None:
    print("\n--- speedup (primary / fast) ---")
    for prompt_label in primary:
        p_samples = primary.get(prompt_label) or []
        f_samples = fast.get(prompt_label) or []
        if not p_samples or not f_samples:
            print(f"  {prompt_label}: skipped (missing samples)")
            continue
        p_mean = statistics.mean(p_samples)
        f_mean = statistics.mean(f_samples)
        if f_mean == 0:
            print(f"  {prompt_label}: skipped (fast mean is 0)")
            continue
        speedup = p_mean / f_mean
        savings_ms = (p_mean - f_mean) * 1000
        print(
            f"  {prompt_label}: {speedup:.2f}x faster, saves {savings_ms:.0f}ms per call"
        )


async def main() -> int:
    settings = get_settings()
    primary_alias = settings.LLM_MODEL
    fast_alias = settings.LLM_FAST_MODEL

    print(f"Primary alias: {primary_alias}")
    print(f"Fast alias:    {fast_alias}")
    print(f"Samples / prompt: {_SAMPLES_PER_PROMPT}")
    print(f"Base URL: {settings.LLM_BASE_URL}\n")

    print(f">>> Benchmarking PRIMARY ({primary_alias})")
    primary_timings = await _bench(primary_alias)

    print(f"\n>>> Benchmarking FAST ({fast_alias})")
    fast_timings = await _bench(fast_alias)

    _summarise(f"PRIMARY: {primary_alias}", primary_timings)
    _summarise(f"FAST:    {fast_alias}", fast_timings)
    _diff(primary_timings, fast_timings)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
