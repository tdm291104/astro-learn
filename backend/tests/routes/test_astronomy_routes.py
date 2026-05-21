"""End-to-end tests for /api/v1/astronomy/* — upload, analyze, catalog."""

from __future__ import annotations

import io

import numpy as np
import pytest
from astropy.io import fits
from httpx import AsyncClient

from tests.conftest import FakeAgentFactory


def _make_fits(shape: tuple[int, int] = (16, 16)) -> bytes:
    """Return a minimal valid FITS file as bytes (random 16x16 image)."""
    data = np.random.default_rng(seed=0).normal(size=shape).astype(np.float32)
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["OBJECT"] = "TEST"
    hdu.header["TELESCOP"] = "PYTEST"
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue()


# --- Auth -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_astronomy_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/astronomy/files")
    assert r.status_code == 401


# --- Upload -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_fits_returns_parsed_header(
    authed_client: AsyncClient, celery_eager: dict
) -> None:
    payload = _make_fits()
    r = await authed_client.post(
        "/api/v1/astronomy/upload-fits",
        files={"file": ("sample.fits", payload, "application/fits")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "sample.fits"
    assert body["hdu_count"] >= 1
    assert body["primary_headers"].get("OBJECT") == "TEST"
    assert celery_eager["ingest_fits"].delay.called


@pytest.mark.asyncio
async def test_upload_fits_rejects_non_fits(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/api/v1/astronomy/upload-fits",
        files={"file": ("malware.exe", b"\x00\x00", "application/octet-stream")},
    )
    assert r.status_code in {400, 422}


@pytest.mark.asyncio
async def test_list_fits_files_after_upload(
    authed_client: AsyncClient, celery_eager: dict
) -> None:
    payload = _make_fits()
    await authed_client.post(
        "/api/v1/astronomy/upload-fits",
        files={"file": ("a.fits", payload, "application/fits")},
    )
    r = await authed_client.get("/api/v1/astronomy/files")
    assert r.status_code == 200
    assert any(f["filename"] == "a.fits" for f in r.json())


@pytest.mark.asyncio
async def test_delete_fits_file(
    authed_client: AsyncClient, celery_eager: dict
) -> None:
    payload = _make_fits()
    r = await authed_client.post(
        "/api/v1/astronomy/upload-fits",
        files={"file": ("to_delete.fits", payload, "application/fits")},
    )
    file_id = r.json()["file_id"]

    r = await authed_client.delete(f"/api/v1/astronomy/files/{file_id}")
    assert r.status_code == 204


# --- Catalog ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalog_search_uses_factory_stub(
    authed_client: AsyncClient, fake_factory: FakeAgentFactory
) -> None:
    fake_factory.set_output(
        "catalog",
        {
            "results": [
                {
                    "name": "M31",
                    "ra_deg": 10.68,
                    "dec_deg": 41.27,
                    "object_type": "Galaxy",
                    "references": [],
                    "extra": {},
                }
            ],
            "source": "simbad",
            "query": "M31",
        },
    )
    r = await authed_client.get(
        "/api/v1/astronomy/catalog/search",
        params={"query": "M31", "source": "simbad"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "simbad"
    assert body["results"][0]["name"] == "M31"


# --- Sample FITS catalog (no agent calls) -----------------------------------


@pytest.mark.asyncio
async def test_sample_fits_lists_curated_items(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/astronomy/sample-fits")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    # Sample list is curated; may be empty in test env, but the shape is stable.
    assert isinstance(body["items"], list)
