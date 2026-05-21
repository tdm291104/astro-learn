"""Post-generation validators for LLM output; failures feed retry prompt."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from schemas.fits_interpretation_schema import FitsInterpretation

# Internal ids must not leak into LLM output.
_UUID_RE: re.Pattern[str] = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Substring that leaks server storage layout.
_FORBIDDEN_PATH_FRAGMENT: str = "fits_artifacts/"

# Engineer-only labels; LLM must rename to human-readable.
_FORBIDDEN_METRIC_LABELS: frozenset[str] = frozenset(
    {"dtype", "nan_count", "method", "bitpix", "naxis", "crval", "ctype"}
)


def validate_fits_interpretation(payload: Any) -> tuple[FitsInterpretation | None, list[str]]:
    """Validate FitsInterpretation; on failure errors feed the retry prompt."""
    errors: list[str] = []

    try:
        model = FitsInterpretation.model_validate(payload)
    except ValidationError as exc:
        return None, [f"schema: {exc.errors(include_url=False)}"]

    _walk_strings(model.model_dump(), path="$", errors=errors)

    for ri, result in enumerate(model.results):
        for mi, metric in enumerate(result.metrics):
            normalised = metric.label.strip().lower()
            if normalised in _FORBIDDEN_METRIC_LABELS:
                errors.append(
                    f"results[{ri}].metrics[{mi}].label is a forbidden internal "
                    f"name {metric.label!r}; rename to a human-readable term."
                )

    if errors:
        return None, errors
    return model, []


def _walk_strings(value: Any, *, path: str, errors: list[str]) -> None:
    """Recursively scan every string for UUIDs and server paths."""
    if isinstance(value, str):
        if _UUID_RE.search(value):
            errors.append(f"{path} contains a UUID; surface the original filename instead.")
        if _FORBIDDEN_PATH_FRAGMENT in value:
            errors.append(f"{path} contains the server path fragment {_FORBIDDEN_PATH_FRAGMENT!r}.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _walk_strings(item, path=f"{path}.{key}", errors=errors)
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _walk_strings(item, path=f"{path}[{idx}]", errors=errors)
