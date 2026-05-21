"""End-to-end smoke test for FITS upload, ingest, analysis, and catalog."""

from __future__ import annotations

import asyncio
import pathlib
import time

import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
TEST_FILE = pathlib.Path(r"C:\Users\ACER\Downloads\crab.fits")

pytestmark = pytest.mark.live


async def _run_workflow() -> None:
    async with httpx.AsyncClient(timeout=120) as c:

        email = f"fits_test_{int(time.time())}@test.com"
        r = await c.post(
            f"{BASE}/users/register",
            json={"email": email, "password": "testpass123"},
        )
        assert r.status_code == 201, f"Register failed: {r.text}"
        print(f"[1] Register OK: {email}")

        r = await c.post(
            f"{BASE}/users/login",
            data={"username": email, "password": "testpass123"},
        )
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[2] Login OK, token: {token[:20]}...")

        assert TEST_FILE.exists(), f"File not found: {TEST_FILE}"
        with open(TEST_FILE, "rb") as f:
            r = await c.post(
                f"{BASE}/astronomy/upload-fits",
                files={"file": (TEST_FILE.name, f, "application/fits")},
                headers=headers,
            )
        assert r.status_code == 201, f"Upload failed: {r.text}"
        up = r.json()
        file_id = up["file_id"]
        print(
            f"[3] Upload OK: {file_id} "
            f"({up['size_bytes']} bytes, {up['hdu_count']} HDUs)"
        )

        # Poll ingest status via the thumbnail artifact endpoint —
        # `ingest_fits` writes thumbnail.png after the FITS row flips to ready.
        print("[4] Polling ingest status (thumbnail artifact)...")
        ready = False
        for i in range(60):
            await asyncio.sleep(2)
            r = await c.get(
                f"{BASE}/astronomy/files/{file_id}/artifacts/thumbnail.png",
                headers=headers,
            )
            print(f"    [{i*2}s] thumbnail.png -> {r.status_code}")
            if r.status_code == 200:
                ready = True
                print(f"[4] READY: thumbnail rendered ({len(r.content)} bytes)")
                break
        if not ready:
            pytest.fail("FITS ingest did not produce thumbnail within 2 minutes")

        # image_stats analysis runs inline (no agent dispatch).
        print("[5] Running image_stats analysis...")
        r = await c.post(
            f"{BASE}/astronomy/analyze",
            json={
                "file_id": file_id,
                "hdu_index": 0,
                "analysis_type": "image_stats",
                "params": {},
            },
            headers=headers,
            timeout=60,
        )
        assert r.status_code == 200, f"image_stats failed: {r.text}"
        stats = r.json()
        print(
            f"[5] image_stats OK: status={stats.get('status')}, "
            f"keys={list((stats.get('results') or {}).keys())}"
        )
        for k in ("mean", "median", "stddev", "min", "max"):
            if k in (stats.get("results") or {}):
                print(f"    {k}: {stats['results'][k]}")

        print("[6] Running image_processor stretch...")
        r = await c.post(
            f"{BASE}/agents/run",
            json={
                "agent_name": "image_processor",
                "task_input": {
                    "file_id": file_id,
                    "hdu_index": 0,
                    "operation": "stretch",
                    "params": {"stretch_type": "log"},
                },
            },
            headers=headers,
            timeout=120,
        )
        assert r.status_code == 200, f"stretch failed: {r.text}"
        run = r.json()
        out = run.get("output") or {}
        artifact_url = out.get("artifact_url")
        print(
            f"[6] stretch OK: status={run.get('status')}, "
            f"artifact_url={artifact_url}"
        )
        # Sanity-check the PNG downloads through the artifacts route.
        if artifact_url:
            png_name = artifact_url.rsplit("/", 1)[-1]
            r = await c.get(
                f"{BASE}/astronomy/files/{file_id}/artifacts/{png_name}",
                headers=headers,
            )
            assert r.status_code == 200, f"stretch PNG download failed: {r.status_code}"
            print(f"    PNG downloaded: {len(r.content)} bytes")

        print("[7] Catalog search (simbad: 'Crab Nebula')...")
        r = await c.get(
            f"{BASE}/astronomy/catalog/search",
            params={"query": "Crab Nebula", "source": "simbad"},
            headers=headers,
            timeout=60,
        )
        assert r.status_code == 200, f"catalog search failed: {r.text}"
        cat = r.json()
        results = cat.get("results", [])
        print(f"[7] Catalog OK: source={cat.get('source')}, hits={len(results)}")
        if results:
            top = results[0]
            print(f"    top: {top}")

        print("\n=== FITS WORKFLOW TEST PASSED ===")
        print(f"File:    {file_id}")
        print(f"Stats:   {stats.get('status')}")
        print(f"Stretch: {run.get('status')} -> {artifact_url}")
        print(f"Catalog: {len(results)} Simbad hits")


async def test_fits_upload_workflow() -> None:
    """Pytest entrypoint that runs the full FITS workflow against a live stack."""
    await _run_workflow()


if __name__ == "__main__":
    asyncio.run(_run_workflow())
