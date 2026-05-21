"""Wipe DB + seed 3 demo accounts.

Usage:
    cd backend
    .venv/Scripts/python.exe -m scripts.seed_demo

Accounts created (password = "DemoPass123"):
    admin@astrolearn.dev   — admin user
    alice@astrolearn.dev   — power user (3 notebooks, 4 FITS, full chat history)
    newuser@astrolearn.dev — empty account (no data)

The "power user" data is inserted directly into the DB with the same shapes the
live agent pipeline produces, so the UI renders everything without needing
LLM / Qdrant / Celery to actually run.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure backend root is importable when run as `python -m scripts.seed_demo`.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from core.config import get_settings  # noqa: E402
from core.security import hash_password  # noqa: E402
from models.agent_model import AgentModel  # noqa: E402
from models.analysis_model import AnalysisModel  # noqa: E402, F401
from models.document_model import DocumentModel  # noqa: E402
from models.fits_file_model import FitsFileModel  # noqa: E402
from models.message_model import MessageModel  # noqa: E402
from models.notebook_artifact_model import NotebookArtifactModel  # noqa: E402
from models.notebook_model import NotebookModel  # noqa: E402
from models.session_model import SessionModel, session_fits_files  # noqa: E402
from models.token_usage_event_model import TokenUsageEventModel  # noqa: E402
from models.user_model import UserModel  # noqa: E402

# Tables wiped in dependency order; CASCADE handles fan-out.
_TABLES_TO_WIPE = (
    "messages",
    "agent_runs",
    "session_fits_files",
    "sessions",
    "documents",
    "notebook_artifacts",
    "notebooks",
    "analyses",
    "reports",
    "fits_files",
    "token_usage_events",
    "users",
    "catalog_cache",
)

PASSWORD = "DemoPass123"

NOW = datetime.now(UTC)


def days_ago(n: int, *, hour: int = 12, minute: int = 0) -> datetime:
    return (NOW - timedelta(days=n)).replace(hour=hour, minute=minute, second=0, microsecond=0)


async def wipe(db) -> None:
    print("[*] Wiping database...")
    await db.execute(
        text("TRUNCATE " + ", ".join(_TABLES_TO_WIPE) + " RESTART IDENTITY CASCADE")
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def seed_users(db) -> dict[str, UserModel]:
    print("[*] Creating users...")
    pwd_hash = hash_password(PASSWORD)

    admin = UserModel(
        id=uuid.uuid4(),
        email="admin@astrolearn.dev",
        password_hash=pwd_hash,
        full_name="Admin Observer",
        is_active=True,
        is_admin=True,
        created_at=days_ago(60),
        updated_at=days_ago(60),
    )
    alice = UserModel(
        id=uuid.uuid4(),
        email="alice@astrolearn.dev",
        password_hash=pwd_hash,
        full_name="Alice Carter",
        is_active=True,
        is_admin=False,
        created_at=days_ago(45),
        updated_at=days_ago(45),
    )
    newuser = UserModel(
        id=uuid.uuid4(),
        email="newuser@astrolearn.dev",
        password_hash=pwd_hash,
        full_name=None,
        is_active=True,
        is_admin=False,
        created_at=days_ago(0, hour=9),
        updated_at=days_ago(0, hour=9),
    )
    db.add_all([admin, alice, newuser])
    await db.flush()
    return {"admin": admin, "alice": alice, "newuser": newuser}


# ---------------------------------------------------------------------------
# Alice's notebooks + documents + artifacts
# ---------------------------------------------------------------------------


def _doc(
    *,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
    filename: str,
    chunks: int,
    size_kb: int,
    days: int,
) -> DocumentModel:
    doc_id = uuid.uuid4()
    ext = filename.rsplit(".", 1)[-1]
    return DocumentModel(
        id=doc_id,
        notebook_id=notebook_id,
        owner_id=owner_id,
        filename=filename,
        content_type=f"application/{ext}" if ext == "pdf" else "text/plain",
        size_bytes=size_kb * 1024,
        storage_path=f"documents/{doc_id}.{ext}",
        status="indexed",
        indexed_chunks=chunks,
        created_at=days_ago(days),
        updated_at=days_ago(days),
    )


async def seed_alice_notebooks(db, alice: UserModel) -> list[NotebookModel]:
    print("[*] Seeding Alice's notebooks + documents...")
    nb1 = NotebookModel(
        id=uuid.uuid4(),
        owner_id=alice.id,
        title="Galactic Surveys 2024",
        description="DES Y3 / DESI papers on galaxy clustering + photometric redshifts.",
        share_token=secrets.token_urlsafe(24),
        share_settings={"show_filenames": True},
        created_at=days_ago(40),
        updated_at=days_ago(2),
    )
    nb2 = NotebookModel(
        id=uuid.uuid4(),
        owner_id=alice.id,
        title="Stellar Evolution Notes",
        description="Personal notes on H-R diagram + late-type stars.",
        share_token=None,
        share_settings={"show_filenames": False},
        created_at=days_ago(28),
        updated_at=days_ago(8),
    )
    nb3 = NotebookModel(
        id=uuid.uuid4(),
        owner_id=alice.id,
        title="Cosmology Reading Group",
        description="Weekly reading list — CMB, large-scale structure, dark energy.",
        share_token=None,
        share_settings={"show_filenames": False},
        created_at=days_ago(15),
        updated_at=days_ago(1),
    )
    db.add_all([nb1, nb2, nb3])
    await db.flush()

    db.add_all([
        _doc(notebook_id=nb1.id, owner_id=alice.id,
             filename="des_y3_galaxy_clustering.pdf", chunks=142, size_kb=2480, days=40),
        _doc(notebook_id=nb1.id, owner_id=alice.id,
             filename="desi_lrg_target_selection.pdf", chunks=98, size_kb=1850, days=38),
        _doc(notebook_id=nb1.id, owner_id=alice.id,
             filename="stellar_contamination_mitigation.pdf", chunks=124, size_kb=2210, days=35),
        _doc(notebook_id=nb1.id, owner_id=alice.id,
             filename="weak_lensing_systematics_notes.md", chunks=18, size_kb=42, days=12),

        _doc(notebook_id=nb2.id, owner_id=alice.id,
             filename="hr_diagram_basics.pdf", chunks=64, size_kb=1120, days=28),
        _doc(notebook_id=nb2.id, owner_id=alice.id,
             filename="red_giant_branch_physics.pdf", chunks=87, size_kb=1640, days=22),
        _doc(notebook_id=nb2.id, owner_id=alice.id,
             filename="my_lecture_notes.md", chunks=14, size_kb=36, days=8),

        _doc(notebook_id=nb3.id, owner_id=alice.id,
             filename="planck_2018_cosmo_params.pdf", chunks=156, size_kb=2840, days=15),
        _doc(notebook_id=nb3.id, owner_id=alice.id,
             filename="bao_overview.pdf", chunks=72, size_kb=1340, days=10),
        _doc(notebook_id=nb3.id, owner_id=alice.id,
             filename="dark_energy_eos.txt", chunks=22, size_kb=58, days=3),
    ])

    # Cached artifacts so the studio panels load instantly without re-running LLM.
    summary_payload = {
        "summary": [
            "The DES Y3 MagLim sample uses six redshift bins from 0.2 to 1.05.",
            "Stellar contamination dominates additive systematics in galaxy clustering.",
            "NIR (W1-band) data improves star/galaxy separation versus optical-only.",
            "Optimal weights jointly correct additive + multiplicative systematics.",
            "Direct catalog-level rejection avoids integral-constraint suppression.",
        ],
        "source_document_count": 4,
    }
    quiz_payload = {
        "questions": [
            {
                "question": "Which band primarily improves star-galaxy separation in MagLim?",
                "options": ["u-band", "g-band", "W1 (NIR)", "Hα"],
                "correct_index": 2,
                "explanation": "W1 from unWISE flags stars via the W1-z color cut.",
            },
            {
                "question": "What is the dominant additive systematic for galaxy clustering?",
                "options": ["Sky background", "Stellar contamination", "PSF errors", "CCD readout"],
                "correct_index": 1,
                "explanation": "Misclassified stars add interlopers independent of true galaxy density.",
            },
            {
                "question": "How many redshift bins does the Y3 MagLim sample use?",
                "options": ["3", "4", "6", "10"],
                "correct_index": 2,
                "explanation": "Edges at z = [0.2, 0.4, 0.55, 0.70, 0.85, 0.95, 1.05].",
            },
        ],
    }
    flashcards_payload = {
        "cards": [
            {"front": "MagLim", "back": "DES Y3 photometric galaxy sample with luminosity-redshift cut."},
            {"front": "EXTMASH", "back": "DES morphological star-galaxy classifier; ==3 selects galaxies."},
            {"front": "Integral constraint", "back": "Normalisation residual when stellar contaminants are present."},
            {"front": "unWISE W1", "back": "Stacked WISE 3.4µm photometry used to flag stars via z-W1."},
        ],
    }
    db.add_all([
        NotebookArtifactModel(
            id=uuid.uuid4(), notebook_id=nb1.id, kind="summary",
            params={"style": "bullets", "max_bullets": 5},
            payload=summary_payload,
            created_at=days_ago(4), updated_at=days_ago(4),
        ),
        NotebookArtifactModel(
            id=uuid.uuid4(), notebook_id=nb1.id, kind="quiz",
            params={"n_questions": 3, "difficulty": "medium"},
            payload=quiz_payload,
            created_at=days_ago(3), updated_at=days_ago(3),
        ),
        NotebookArtifactModel(
            id=uuid.uuid4(), notebook_id=nb1.id, kind="flashcards",
            params={"n_cards": 4},
            payload=flashcards_payload,
            created_at=days_ago(2), updated_at=days_ago(2),
        ),
    ])

    return [nb1, nb2, nb3]


# ---------------------------------------------------------------------------
# Alice's FITS files + analyses + agent runs
# ---------------------------------------------------------------------------


def _fake_header_summary(*, obj: str, instrument: str, exptime: float, has_wcs: bool) -> dict[str, Any]:
    return {
        "naxis": 2,
        "naxis1": 2048,
        "naxis2": 2048,
        "bitpix": -32,
        "instrument": instrument,
        "telescope": "HST",
        "filter": "F606W",
        "exptime": exptime,
        "object": obj,
        "bunit": "ELECTRONS/S",
        "has_wcs": has_wcs,
    }


async def seed_alice_fits(
    db, alice: UserModel
) -> tuple[list[FitsFileModel], list[AnalysisModel]]:
    print("[*] Seeding Alice's FITS files + analyses...")
    fits: list[FitsFileModel] = []
    for spec in [
        {"name": "ngc1300_v1.fits", "obj": "NGC 1300", "days": 30, "exp": 600.0},
        {"name": "m31_uv.fits", "obj": "M31", "days": 22, "exp": 1200.0},
        {"name": "crab_xray.fits", "obj": "CRAB NEBULA", "days": 14, "exp": 800.0},
        {"name": "hub_deep_field.fits", "obj": "HDF-N", "days": 5, "exp": 3600.0},
    ]:
        fid = uuid.uuid4()
        fits.append(FitsFileModel(
            id=fid,
            owner_id=alice.id,
            filename=spec["name"],
            content_type="application/fits",
            size_bytes=int(8 * 1024 * 1024),
            storage_path=f"fits/{fid}.fits",
            hdu_count=2,
            hdus=[
                {"index": 0, "name": "PRIMARY", "type": "PrimaryHDU",
                 "shape": [2048, 2048], "n_keywords": 86},
                {"index": 1, "name": "SCI", "type": "ImageHDU",
                 "shape": [2048, 2048], "n_keywords": 42},
            ],
            primary_headers={"OBJECT": spec["obj"], "EXPTIME": spec["exp"]},
            header_summary=_fake_header_summary(
                obj=spec["obj"], instrument="WFC3/UVIS",
                exptime=spec["exp"], has_wcs=True,
            ),
            status="parsed",
            created_at=days_ago(spec["days"]),
            updated_at=days_ago(spec["days"]),
        ))
    db.add_all(fits)
    await db.flush()

    # Two analyses per file across different types to populate dashboards.
    analyses: list[AnalysisModel] = []
    analysis_specs = [
        (fits[0], "image_stats", 29),
        (fits[0], "wcs_solve", 29),
        (fits[1], "image_stats", 21),
        (fits[1], "photometry", 20),
        (fits[2], "image_stats", 13),
        (fits[3], "spectroscopy", 4),
    ]
    for fits_file, atype, days in analysis_specs:
        aid = uuid.uuid4()
        started = days_ago(days, hour=14)
        finished = started + timedelta(seconds=42)
        analyses.append(AnalysisModel(
            id=aid,
            owner_id=alice.id,
            file_id=fits_file.id,
            agent_run_id=None,
            analysis_type=atype,
            hdu_index=0,
            params={},
            status="succeeded",
            results=_fake_analysis_results(atype),
            artifacts=[f"fits_artifacts/{fits_file.id}/thumbnail.png",
                       f"fits_artifacts/{fits_file.id}/sources.json"],
            interpretation=_fake_interpretation(fits_file.filename, atype),
            started_at=started,
            finished_at=finished,
            created_at=started,
            updated_at=finished,
        ))
    db.add_all(analyses)
    return fits, analyses


def _fake_analysis_results(atype: str) -> dict[str, Any]:
    if atype == "image_stats":
        return {"min": 0.0, "max": 143.2, "mean": 8.35, "stddev": 12.41,
                "median": 6.18, "n_pixels": 2048 * 2048, "nan_count": 0}
    if atype == "wcs_solve":
        return {"wcs": {"CRVAL1": 49.95, "CRVAL2": 41.27,
                        "CRPIX1": 1024.0, "CRPIX2": 1024.0,
                        "CDELT1": -6.83e-5, "CDELT2": 6.83e-5,
                        "CROTA2": 0.0}}
    if atype == "photometry":
        return {"sources": [{"x": 512.3, "y": 1024.7, "flux": 1.2e-15}] * 24,
                "zero_point": 25.7, "fwhm": 2.4, "background": 0.08}
    if atype == "spectroscopy":
        return {"wavelength_min": 3500.0, "wavelength_max": 7500.0,
                "peak_flux": 5.4e-16, "n_lines": 12}
    return {}


def _fake_interpretation(filename: str, atype: str) -> dict[str, Any]:
    return {
        "context": {
            "filename": filename,
            "image_type": "2D broadband optical image",
            "dimensions": "2048 × 2048 px",
            "instrument": "WFC3/UVIS",
            "filter": "F606W",
        },
        "decision": {
            "analysis_types": [atype],
            "reasoning": f"Header has WCS + EXPTIME, suitable for {atype}.",
        },
        "results": [
            {
                "type": atype,
                "headline": f"{atype.replace('_', ' ').title()} completed successfully.",
                "metrics": [
                    {"label": "Mean pixel value", "value": "8.35 e-/s",
                     "interpretation": "Typical for sky-dominated exposures."}
                ],
                "interpretation": "The image is suitable for further analysis.",
                "anomalies": [],
            }
        ],
        "next_steps": ["Run photometry on detected sources.",
                       "Cross-match with Gaia DR3."],
    }


# ---------------------------------------------------------------------------
# Alice's chat sessions + messages
# ---------------------------------------------------------------------------


def _reasoning_extra(steps: list[dict[str, Any]], summary: str | None = None) -> dict[str, Any]:
    return {"reasoning": {"plan_summary": summary, "steps": steps}}


async def seed_alice_chats(
    db,
    alice: UserModel,
    notebooks: list[NotebookModel],
    fits: list[FitsFileModel],
) -> list[SessionModel]:
    print("[*] Seeding Alice's chat sessions + messages...")
    nb1, nb2, nb3 = notebooks
    sessions: list[SessionModel] = []

    # Session 1: notebook Q&A on Galactic Surveys (4 turns)
    s1 = SessionModel(
        id=uuid.uuid4(), user_id=alice.id, notebook_id=nb1.id,
        title="Summary of MagLim systematics",
        mode="notebook",
        created_at=days_ago(20), updated_at=days_ago(20),
    )
    db.add(s1)
    await db.flush()
    _add_messages(db, s1.id, days_ago(20), [
        ("user", "Summarize the key systematics in the MagLim sample."),
        ("assistant",
         "The dominant systematics are stellar contamination (additive) and "
         "obscuration (multiplicative). Stars get misclassified as galaxies, "
         "and bright stars suppress detection of nearby sources.",
         _reasoning_extra(
             steps=[
                 {
                     "agent_name": "qa",
                     "rationale": "Retrieve grounding chunks, then synthesise.",
                     "tool_invocations": [
                         {"name": "vector_search",
                          "arguments": {"query": "MagLim systematics", "top_k": 6},
                          "result": "[{\"chunk_id\": \"abc:1\", \"text\": \"...\", \"score\": 0.92}]"},
                     ],
                 }
             ],
             summary="Retrieve relevant chunks from the notebook then answer.",
         )),
        ("user", "How is stellar contamination mitigated?"),
        ("assistant",
         "Using NIR (W1) photometry to detect stars via the W1-z color cut. "
         "This catches ~3% of objects that morphology alone misses.",
         _reasoning_extra(
             steps=[{
                 "agent_name": "qa",
                 "rationale": "Same retrieval pipeline; narrower query.",
                 "tool_invocations": [
                     {"name": "vector_search",
                      "arguments": {"query": "stellar contamination mitigation"},
                      "result": "[{\"chunk_id\": \"abc:42\", \"score\": 0.88}]"},
                 ],
             }]
         )),
    ])
    sessions.append(s1)

    # Session 2: FITS analysis chat
    s2 = SessionModel(
        id=uuid.uuid4(), user_id=alice.id, notebook_id=None,
        title="NGC 1300 image stats",
        mode="fits",
        created_at=days_ago(29), updated_at=days_ago(29),
    )
    db.add(s2)
    await db.flush()
    # Attach FITS files via association table.
    await db.execute(
        session_fits_files.insert().values(session_id=s2.id, fits_file_id=fits[0].id)
    )
    _add_messages(db, s2.id, days_ago(29), [
        ("user", "Analyse this FITS file."),
        ("assistant",
         "Image statistics on NGC 1300 (2048×2048, F606W): mean 8.35 e-/s, "
         "stddev 12.41. WCS is present and well-anchored at RA 49.95°, Dec 41.27°. "
         "Suitable for photometry next.",
         _reasoning_extra(
             steps=[{
                 "agent_name": "fits_analyst",
                 "rationale": "Planning to run: image_stats, wcs. Inferred from header.",
                 "tool_invocations": [
                     {"name": "run_fits_analysis",
                      "arguments": {"file_id": str(fits[0].id), "analysis_type": "image_stats"},
                      "result": "{\"status\": \"succeeded\", \"results\": {\"mean\": 8.35}}"},
                     {"name": "run_fits_analysis",
                      "arguments": {"file_id": str(fits[0].id), "analysis_type": "wcs_solve"},
                      "result": "{\"status\": \"succeeded\", \"results\": {\"wcs\": {}}}"},
                 ],
             }]
         )),
    ])
    sessions.append(s2)

    # Session 3: Catalog search
    s3 = SessionModel(
        id=uuid.uuid4(), user_id=alice.id, notebook_id=None,
        title="What is M31?",
        mode="catalog",
        created_at=days_ago(11), updated_at=days_ago(11),
    )
    db.add(s3)
    await db.flush()
    _add_messages(db, s3.id, days_ago(11), [
        ("user", "Tell me about M31."),
        ("assistant",
         "M31 (Andromeda Galaxy) — RA 10.68°, Dec 41.27°. Type SA(s)b, "
         "~780 kpc away, the nearest large spiral to the Milky Way.",
         _reasoning_extra(
             steps=[{
                 "agent_name": "catalog_chat",
                 "rationale": "Catalog hit; narrate the row.",
                 "tool_invocations": [
                     {"name": "simbad_query",
                      "arguments": {"query": "M31"},
                      "result": "{\"results\": [{\"name\": \"M  31\", \"object_type\": \"Galaxy\", \"ra_deg\": 10.68, \"dec_deg\": 41.27}], \"source\": \"simbad\", \"query\": \"M31\"}"},
                 ],
             }]
         )),
    ])
    sessions.append(s3)

    # Session 4: Recent general chat (no notebook)
    s4 = SessionModel(
        id=uuid.uuid4(), user_id=alice.id, notebook_id=None,
        title="What can you do?",
        mode="general",
        created_at=days_ago(1, hour=10), updated_at=days_ago(1, hour=10),
    )
    db.add(s4)
    await db.flush()
    _add_messages(db, s4.id, days_ago(1, hour=10), [
        ("user", "What can you do?"),
        ("assistant",
         "I can help with notebook Q&A, summarise/quiz/flashcards, FITS file "
         "analysis, and catalog searches across Simbad/NED/VizieR.",
         None),
    ])
    sessions.append(s4)

    return sessions


def _add_messages(
    db,
    session_id: uuid.UUID,
    base_time: datetime,
    turns: list[tuple[str, str] | tuple[str, str, dict[str, Any] | None]],
) -> None:
    """Insert chat turns spaced ~30s apart starting from base_time."""
    for i, turn in enumerate(turns):
        role = turn[0]
        content = turn[1]
        extra = turn[2] if len(turn) > 2 else None
        ts = base_time + timedelta(seconds=30 * i)
        db.add(MessageModel(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            extra=extra,
            created_at=ts,
            updated_at=ts,
        ))


# ---------------------------------------------------------------------------
# Alice's agent_runs + token_usage_events
# ---------------------------------------------------------------------------


async def seed_alice_agent_runs(
    db, alice: UserModel, sessions: list[SessionModel]
) -> None:
    print("[*] Seeding Alice's agent runs...")
    specs: list[tuple[str, int]] = [
        ("orchestrator", 20), ("orchestrator", 29), ("orchestrator", 11),
        ("orchestrator", 1), ("qa", 20), ("qa", 18), ("qa", 14),
        ("summarizer", 4), ("quiz", 3), ("flashcard", 2),
        ("fits_analyst", 29), ("fits_analyst", 21), ("fits_analyst", 13),
        ("catalog_chat", 11), ("catalog", 10),
    ]
    for name, days in specs:
        started = days_ago(days, hour=14)
        finished = started + timedelta(seconds=12)
        db.add(AgentModel(
            id=uuid.uuid4(),
            user_id=alice.id,
            session_id=sessions[0].id if name in ("qa", "summarizer", "quiz", "flashcard") else None,
            agent_name=name,
            status="succeeded",
            task_input={"query": "demo"},
            output={"ok": True},
            error=None,
            started_at=started,
            finished_at=finished,
            step_count=2 if name == "orchestrator" else 1,
            current_step=None,
            progress=1.0,
            created_at=started,
            updated_at=finished,
        ))


async def seed_alice_tokens(db, alice: UserModel) -> None:
    print("[*] Seeding Alice's token usage events...")
    # Spread roughly 40 events across the last 30 days for chart density.
    models = [
        ("groq/llama-3.3-70b-versatile", 1200, 480),
        ("groq/llama-3.3-70b-versatile", 850, 320),
        ("anthropic/claude-sonnet-4-6", 2400, 720),
        ("openai/gpt-4o", 1800, 540),
        ("groq/llama-3.3-70b-versatile", 600, 260),
    ]
    for day in range(30, 0, -1):
        for hour, (model, prompt_t, completion_t) in zip(
            [9, 11, 14, 17, 20], models, strict=False
        ):
            if (day + hour) % 3 == 0:
                continue  # Sparse days so the chart isn't a flat block.
            db.add(TokenUsageEventModel(
                id=uuid.uuid4(),
                user_id=alice.id,
                model=model,
                prompt_tokens=prompt_t,
                completion_tokens=completion_t,
                total_tokens=prompt_t + completion_t,
                created_at=days_ago(day, hour=hour),
            ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    settings = get_settings()
    print(f"Target DB: {settings.DATABASE_URL}\n")

    engine = create_async_engine(settings.DATABASE_URL, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessionmaker() as db:
            await wipe(db)
            users = await seed_users(db)
            notebooks = await seed_alice_notebooks(db, users["alice"])
            fits, _ = await seed_alice_fits(db, users["alice"])
            sessions = await seed_alice_chats(db, users["alice"], notebooks, fits)
            await seed_alice_agent_runs(db, users["alice"], sessions)
            await seed_alice_tokens(db, users["alice"])
            await db.commit()
    finally:
        await engine.dispose()

    print("\n[OK] Seed complete.\n")
    print(f"  admin@astrolearn.dev   / {PASSWORD}  (admin)")
    print(f"  alice@astrolearn.dev   / {PASSWORD}  (power user)")
    print(f"  newuser@astrolearn.dev / {PASSWORD}  (empty account)")


if __name__ == "__main__":
    asyncio.run(main())
