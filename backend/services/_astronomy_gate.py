"""Astronomy-relevance gate for uploaded documents and FITS files.

Document gate: LLM 1-shot classifier on a 3000-char sample. Fail-open on
LLM error/timeout — log warning, let upload through. Strict-mode upload
gate UX must not be hostage to LLM provider blips.

FITS gate: header rule cards primary (TELESCOP / INSTRUME / WCS / CTYPE
sky axes). LLM fallback only fires for the rare "mute" FITS with no
header signal.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Final

import structlog

from core.llm.llm_client import LLMClient

_logger = structlog.get_logger(__name__)

_DOC_TIMEOUT_S: Final[float] = 15.0
_FITS_LLM_TIMEOUT_S: Final[float] = 8.0
_DOC_SAMPLE_CHAR_LIMIT: Final[int] = 3000

_DOC_GATE_SYSTEM_PROMPT: Final[str] = (
    "You decide if an uploaded document is about astronomy. "
    "Astronomy includes: astrophysics, cosmology, stellar/galactic physics, "
    "planetary science, observational astronomy, telescope/instrument papers, "
    "FITS data analysis, astronomy education material, and amateur observing "
    "notes.\n\n"
    "Reject documents that are clearly unrelated (CVs, contracts, recipes, "
    "general programming, business reports, fiction, non-astronomy science "
    "such as pure biology / chemistry / nuclear physics that does not touch "
    "astrophysics, etc.).\n\n"
    "Reply with a single JSON object — no prose, no markdown fences — "
    "matching exactly: "
    '{"is_astronomy": <bool>, "reason": <short string>}'
)

_FITS_GATE_SYSTEM_PROMPT: Final[str] = (
    "You decide if a FITS file is from astronomy. Most FITS files in the "
    "wild are astronomy (telescope images, spectra, catalogs). FITS is "
    "occasionally used in medical imaging or lab physics — reject those.\n\n"
    "You will get the FITS header summary as JSON. Look for sky-coordinate "
    "WCS, telescope/instrument names, exposure, OBJECT field. Absence of "
    "all astronomical hints is suspicious.\n\n"
    "Reply with a single JSON object — no prose, no markdown fences — "
    "matching exactly: "
    '{"is_astronomy": <bool>, "reason": <short string>}'
)


def _ctype_is_sky(ctype: str | None) -> bool:
    if not ctype:
        return False
    upper = ctype.upper()
    return any(
        upper.startswith(prefix)
        for prefix in ("RA--", "DEC-", "GLON", "GLAT", "ELON", "ELAT")
    )


def check_fits_relevance(header_summary: dict[str, Any]) -> tuple[bool, str | None]:
    """Header rule check. Returns (ok, reason).

    `reason` is "header_signal" when accepted, "no_astronomy_header_signal"
    when no hint found (caller should run LLM fallback).
    """
    if not isinstance(header_summary, dict):
        return False, "missing_header_summary"

    telescope = (header_summary.get("telescope") or "").strip()
    instrument = (header_summary.get("instrument") or "").strip()
    has_wcs = bool(header_summary.get("has_wcs"))
    ctype1 = header_summary.get("ctype1")
    ctype2 = header_summary.get("ctype2")
    obj = (header_summary.get("object") or "").strip()

    if telescope or instrument or has_wcs or _ctype_is_sky(ctype1) or _ctype_is_sky(ctype2):
        return True, "header_signal"

    # OBJECT alone is a weak signal — keep but flag for the caller; LLM
    # fallback can either confirm or reject. For now treat as accept since
    # legitimate FITS often have only OBJECT populated.
    if obj:
        return True, "object_only_signal"

    return False, "no_astronomy_header_signal"


def _parse_json_gate(raw: str) -> tuple[bool, str]:
    """Parse `{is_astronomy, reason}` from LLM output. Fail-open on parse error."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("astronomy_gate.invalid_json", raw=raw[:200])
        return True, "gate_parse_failed_fail_open"
    if not isinstance(parsed, dict):
        return True, "gate_shape_failed_fail_open"
    is_astro = bool(parsed.get("is_astronomy", True))
    reason = parsed.get("reason")
    return is_astro, reason if isinstance(reason, str) else ""


async def check_document_relevance(
    llm: LLMClient,
    filename: str,
    sample_text: str,
) -> tuple[bool, str]:
    """LLM-gated astronomy classification for an uploaded doc.

    Fail-open: any LLM/timeout/parse error returns (True, reason) so
    user is not held hostage to LLM infra.
    """
    sample = (sample_text or "").strip()
    if not sample:
        # No text extracted (scanned PDF without OCR, empty file). Accept
        # but flag — extension check already filtered binaries.
        _logger.info("astronomy_gate.empty_sample", filename=filename)
        return True, "empty_sample_fail_open"

    sample = sample[:_DOC_SAMPLE_CHAR_LIMIT]
    user_prompt = (
        f"Filename: {filename}\n\n"
        f"First {len(sample)} chars of extracted text:\n---\n{sample}\n---"
    )

    try:
        raw = await asyncio.wait_for(
            llm.complete(
                [
                    {"role": "system", "content": _DOC_GATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=120,
            ),
            timeout=_DOC_TIMEOUT_S,
        )
    except TimeoutError:
        _logger.warning("astronomy_gate.doc_timeout", filename=filename)
        return True, "gate_timeout_fail_open"
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        _logger.warning(
            "astronomy_gate.doc_llm_failed",
            filename=filename,
            error=str(exc),
        )
        return True, "gate_llm_failed_fail_open"

    return _parse_json_gate(raw)


async def check_fits_relevance_with_llm(
    llm: LLMClient,
    filename: str,
    header_summary: dict[str, Any],
) -> tuple[bool, str]:
    """Header-first, LLM-fallback FITS relevance gate.

    Header rule cards accept the obvious 99% case. LLM only runs when
    header has no astronomy hint at all.
    """
    ok, reason = check_fits_relevance(header_summary)
    if ok:
        return True, reason or "header_signal"

    # Header has no astronomy signal — ask LLM on the header summary.
    user_prompt = (
        f"Filename: {filename}\n\n"
        f"Header summary:\n{json.dumps(header_summary, default=str)}"
    )
    try:
        raw = await asyncio.wait_for(
            llm.complete(
                [
                    {"role": "system", "content": _FITS_GATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=120,
            ),
            timeout=_FITS_LLM_TIMEOUT_S,
        )
    except TimeoutError:
        _logger.warning(
            "astronomy_gate.fits_llm_timeout", filename=filename
        )
        return True, "gate_timeout_fail_open"
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        _logger.warning(
            "astronomy_gate.fits_llm_failed",
            filename=filename,
            error=str(exc),
        )
        return True, "gate_llm_failed_fail_open"

    return _parse_json_gate(raw)
