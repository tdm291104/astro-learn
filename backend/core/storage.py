"""Filesystem layout and safe IO helpers for uploaded artefacts."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from core.exceptions import ValidationError


def documents_dir(root: Path) -> Path:
    """Return STORAGE_ROOT/documents/, creating it if missing."""
    path = root / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fits_dir(root: Path) -> Path:
    """Return STORAGE_ROOT/fits/, creating it if missing."""
    path = root / "fits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fits_artifacts_dir(root: Path, file_id: uuid.UUID) -> Path:
    """Return STORAGE_ROOT/fits_artifacts/{file_id}/, creating it if missing."""
    path = root / "fits_artifacts" / str(file_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def analysis_dir(root: Path, analysis_id: uuid.UUID) -> Path:
    """Return STORAGE_ROOT/analyses/{analysis_id}/, creating it if missing."""
    path = root / "analyses" / str(analysis_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir(root: Path) -> Path:
    """Return STORAGE_ROOT/reports/, creating it if missing."""
    path = root / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_bytes(path: Path, data: bytes) -> None:
    """Atomic write via temp file + os.replace; crash leaves whole or temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{uuid.uuid4().hex}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        # Swallow secondary errors so original exception isn't masked.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def safe_extension(
    filename: str,
    *,
    allowed: set[str],
    default: str,
) -> str:
    """Pick a safe lowercase extension; defends against path-traversal payloads."""
    if not filename or not filename.strip():
        raise ValidationError(
            message="Upload filename is empty",
            code="empty_filename",
        )

    # Strip both POSIX/Windows separators since Path.name on POSIX leaves \\.
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(cleaned).suffix.lower()

    if suffix in allowed:
        return suffix
    return default
