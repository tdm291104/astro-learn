"""Unit tests for the upload-time astronomy-relevance gate."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from services._astronomy_gate import (
    check_document_relevance,
    check_fits_relevance,
    check_fits_relevance_with_llm,
)


# --- FITS header rule ------------------------------------------------------


def test_fits_header_rule_accepts_telescope() -> None:
    ok, reason = check_fits_relevance(
        {"telescope": "HST", "instrument": None, "has_wcs": False}
    )
    assert ok is True
    assert reason == "header_signal"


def test_fits_header_rule_accepts_instrument() -> None:
    ok, reason = check_fits_relevance(
        {"telescope": None, "instrument": "WFC3", "has_wcs": False}
    )
    assert ok is True
    assert reason == "header_signal"


def test_fits_header_rule_accepts_wcs() -> None:
    ok, reason = check_fits_relevance({"has_wcs": True})
    assert ok is True
    assert reason == "header_signal"


def test_fits_header_rule_accepts_sky_ctype() -> None:
    ok, _ = check_fits_relevance({"ctype1": "RA---TAN", "ctype2": "DEC--TAN"})
    assert ok is True


def test_fits_header_rule_accepts_object_only_as_weak_signal() -> None:
    ok, reason = check_fits_relevance({"object": "M31"})
    assert ok is True
    assert reason == "object_only_signal"


def test_fits_header_rule_rejects_when_no_signal() -> None:
    ok, reason = check_fits_relevance(
        {
            "telescope": None,
            "instrument": None,
            "has_wcs": False,
            "ctype1": None,
            "ctype2": None,
            "object": None,
        }
    )
    assert ok is False
    assert reason == "no_astronomy_header_signal"


# --- FITS LLM fallback (header has no signal) ------------------------------


@pytest.mark.asyncio
async def test_fits_llm_fallback_runs_only_on_mute_header() -> None:
    llm = AsyncMock()
    llm.complete.return_value = '{"is_astronomy": true, "reason": "spectrum"}'

    ok, reason = await check_fits_relevance_with_llm(
        llm,
        "data.fits",
        {"telescope": "HST"},  # header rule accepts → LLM must not run
    )
    assert ok is True
    assert reason == "header_signal"
    llm.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_fits_llm_fallback_rejects_mute_non_astro_fits() -> None:
    llm = AsyncMock()
    llm.complete.return_value = (
        '{"is_astronomy": false, "reason": "medical imaging"}'
    )

    ok, _ = await check_fits_relevance_with_llm(
        llm,
        "ct_scan.fits",
        {"telescope": None, "instrument": None, "has_wcs": False},
    )
    assert ok is False
    llm.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_fits_llm_fallback_fails_open_on_llm_error() -> None:
    llm = AsyncMock()
    llm.complete.side_effect = RuntimeError("provider down")

    ok, reason = await check_fits_relevance_with_llm(
        llm,
        "data.fits",
        {"telescope": None, "instrument": None, "has_wcs": False},
    )
    assert ok is True
    assert "fail_open" in reason


# --- Document gate ---------------------------------------------------------


@pytest.mark.asyncio
async def test_document_gate_accepts_astronomy_text() -> None:
    llm = AsyncMock()
    llm.complete.return_value = '{"is_astronomy": true, "reason": "stellar"}'

    ok, _ = await check_document_relevance(
        llm, "paper.pdf", "Stellar evolution of M-dwarfs..."
    )
    assert ok is True


@pytest.mark.asyncio
async def test_document_gate_rejects_off_topic() -> None:
    llm = AsyncMock()
    llm.complete.return_value = '{"is_astronomy": false, "reason": "CV"}'

    ok, reason = await check_document_relevance(
        llm, "resume.pdf", "John Doe — software engineer with 10 years..."
    )
    assert ok is False
    assert reason == "CV"


@pytest.mark.asyncio
async def test_document_gate_fail_open_on_empty_sample() -> None:
    llm = AsyncMock()

    ok, reason = await check_document_relevance(llm, "scanned.pdf", "")
    assert ok is True
    assert "empty_sample" in reason
    llm.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_gate_fail_open_on_llm_error() -> None:
    llm = AsyncMock()
    llm.complete.side_effect = RuntimeError("provider 503")

    ok, reason = await check_document_relevance(
        llm, "paper.pdf", "Some long astronomy-ish text..."
    )
    assert ok is True
    assert "fail_open" in reason


@pytest.mark.asyncio
async def test_document_gate_fail_open_on_bad_json() -> None:
    llm = AsyncMock()
    llm.complete.return_value = "not json at all"

    ok, _ = await check_document_relevance(
        llm, "paper.pdf", "Some long astronomy-ish text..."
    )
    assert ok is True
