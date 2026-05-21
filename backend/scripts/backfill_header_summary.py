"""Backfill `header_summary` for existing fits_files rows.

Idempotent — skips rows that already have a non-null `header_summary` unless
``--force`` is passed. Reads the existing `primary_headers` JSONB column and
runs it through ``agents.astronomy.fits_decision.extract_header_summary``; no
FITS files are re-opened from disk.

Usage::

    # 1. Always start with a dry run. Prints counts + a sample row, writes nothing.
    python -m scripts.backfill_header_summary --dry-run

    # 2. Only after eyeballing the dry-run output, apply for real.
    python -m scripts.backfill_header_summary --apply

    # Re-run even for rows already populated (use with care).
    python -m scripts.backfill_header_summary --apply --force

The script refuses to run without one of ``--dry-run`` or ``--apply`` so
operators can't accidentally invoke a no-op or a real write.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from agents.astronomy.fits_decision import extract_header_summary
from core.config import get_settings
from models.fits_file_model import FitsFileModel

# Batch size from the approved plan — small enough to keep transactions short
# under contention on the fits_files table, large enough to be efficient.
BATCH_SIZE: int = 50

# Inter-batch pause; keeps the script from monopolising DB capacity on a hot
# instance and lets WAL flushes catch up between commits.
INTER_BATCH_SLEEP_SECONDS: float = 0.5


log = structlog.get_logger("backfill_header_summary")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute summaries and log counts without writing anything.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write computed summaries back to fits_files.header_summary.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process rows that already have a non-null header_summary.",
    )
    return parser.parse_args()


async def run(*, dry_run: bool, force: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    started_at = time.monotonic()
    total = 0
    processed = 0
    skipped = 0
    sample_logged = False

    try:
        async with session_factory() as session:
            count_stmt = select(FitsFileModel.id)
            if not force:
                count_stmt = count_stmt.where(FitsFileModel.header_summary.is_(None))
            total = len(list(await session.scalars(count_stmt)))

        log.info("backfill.started", mode="dry-run" if dry_run else "apply",
                 force=force, total=total, batch_size=BATCH_SIZE)

        if total == 0:
            log.info("backfill.nothing_to_do")
            return 0

        offset = 0
        while True:
            async with session_factory() as session:
                stmt = select(FitsFileModel).order_by(FitsFileModel.id)
                if not force:
                    stmt = stmt.where(FitsFileModel.header_summary.is_(None))
                stmt = stmt.limit(BATCH_SIZE).offset(offset)
                rows = list(await session.scalars(stmt))
                if not rows:
                    break

                for row in rows:
                    summary = _compute_summary_for_row(row)
                    if summary is None:
                        skipped += 1
                        continue

                    if not sample_logged:
                        log.info("backfill.sample", file_id=str(row.id),
                                 filename=row.filename, summary=summary)
                        sample_logged = True

                    if not dry_run:
                        await session.execute(
                            update(FitsFileModel)
                            .where(FitsFileModel.id == row.id)
                            .values(header_summary=summary)
                        )

                    processed += 1

                if not dry_run:
                    await session.commit()

            elapsed = time.monotonic() - started_at
            log.info("backfill.batch_done", processed=processed, skipped=skipped,
                     total=total, elapsed_seconds=round(elapsed, 2))

            # With --force we read ALL rows and rewrite them, so the where-clause
            # never narrows — advance the offset. Without --force the WHERE shrinks
            # the working set, so offset stays at 0.
            if force:
                offset += BATCH_SIZE

            if not rows or len(rows) < BATCH_SIZE:
                break

            time.sleep(INTER_BATCH_SLEEP_SECONDS)
    finally:
        await engine.dispose()

    elapsed = time.monotonic() - started_at
    log.info("backfill.finished", mode="dry-run" if dry_run else "apply",
             processed=processed, skipped=skipped, total=total,
             elapsed_seconds=round(elapsed, 2))
    return 0


def _compute_summary_for_row(row: FitsFileModel) -> dict[str, Any] | None:
    """Recompute header_summary from the stored primary_headers + hdu shapes."""
    primary = row.primary_headers or {}
    if not primary:
        # No header to project. Skip rather than write an empty dict; caller
        # can re-run with the original FITS file if needed.
        return None
    hdu_shapes: list[list[int] | None] = []
    for hdu in row.hdus or []:
        shape = hdu.get("shape") if isinstance(hdu, dict) else None
        hdu_shapes.append(list(shape) if isinstance(shape, list) else None)
    return extract_header_summary(primary, hdu_shapes=hdu_shapes)


def main() -> int:
    args = parse_args()
    return asyncio.run(run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
