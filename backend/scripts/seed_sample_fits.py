"""
Copy curated FITS samples from the FITS agent-evaluation dataset into the
backend storage root so the anomaly-audit landing page has files to offer.

Idempotent — files already present are skipped. Source directory is the
FITS evaluation dataset (downloaded via `benchmarks/fits_agent_eval.ipynb`);
adjust `--source` if your checkout lives elsewhere.

Usage:
    python -m scripts.seed_sample_fits                 # default paths
    python -m scripts.seed_sample_fits --source <dir>  # custom source
    python -m scripts.seed_sample_fits --force         # overwrite existing
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Make `core.*` importable when run as a script from backend/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings  # noqa: E402
from core.sample_fits import SAMPLE_FITS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT.parent / "docs" / "benchmarks" / "fits_agent_eval_data" / "fits_files",
        help="Directory containing the FITS files downloaded by the evaluation notebook.",
    )
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Override storage root (defaults to STORAGE_ROOT from .env).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-copy even if the destination file already exists.",
    )
    args = parser.parse_args()

    storage_root = (
        args.storage_root or get_settings().STORAGE_ROOT
    ).expanduser().resolve()
    dest_dir = storage_root / "fits"
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"Source: {args.source}")
    print(f"Target: {dest_dir}")

    if not args.source.exists():
        print(f"ERROR: source directory not found: {args.source}", file=sys.stderr)
        return 1

    copied = 0
    skipped = 0
    missing = 0
    for sample in SAMPLE_FITS:
        src = args.source / sample.source_filename
        dst = dest_dir / sample.storage_filename
        if not src.exists():
            print(f"  [MISSING] {sample.source_filename} — skipping")
            missing += 1
            continue
        if dst.exists() and not args.force:
            print(f"  [SKIP]    {dst.name} already present ({dst.stat().st_size / 1e6:.1f} MB)")
            skipped += 1
            continue
        shutil.copyfile(src, dst)
        print(f"  [COPY]    {sample.source_filename} -> {dst.name}")
        copied += 1

    print()
    print(f"Done. copied={copied} skipped={skipped} missing={missing} total={len(SAMPLE_FITS)}")
    if missing > 0:
        print(
            "Run the FITS evaluation notebook's download step first to fetch the missing files:\n"
            "    open benchmarks/fits_agent_eval.ipynb and execute the download cell\n"
            "    (or call download_dataset(n_normal=30, n_anomaly=10) directly)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
