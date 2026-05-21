"""Curated FITS files for the public landing anomaly-audit demo (stable uuid5 ids)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

# Namespace for deterministic uuid5; must stay stable across releases.
_SAMPLE_NAMESPACE: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000fb1")


@dataclass(frozen=True)
class SampleFits:
    """One curated FITS file the frontend can offer for analysis."""

    file_id: uuid.UUID
    source_filename: str
    display_name: str
    description: str
    instrument: str
    size_mb: float
    expected_anomalies: int

    @property
    def storage_filename(self) -> str:
        return f"{self.file_id}.fits"


def _sid(name: str) -> uuid.UUID:
    return uuid.uuid5(_SAMPLE_NAMESPACE, name)


SAMPLE_FITS: list[SampleFits] = [
    SampleFits(
        file_id=_sid("icdb88jqq_raw.fits"),
        source_filename="icdb88jqq_raw.fits",
        display_name="HST WFC3 — raw level-1 exposure",
        description=(
            "Uncalibrated raw exposure from HST/WFC3 UVIS. Small 4-HDU "
            "structure (primary + science/error/DQ). Demonstrates how the "
            "symbolic checker flags BITPIX/dtype mismatches caused by "
            "BZERO/BSCALE rescaling — a quirk common to raw HST products."
        ),
        instrument="HST WFC3/UVIS",
        size_mb=2.1,
        expected_anomalies=1,
    ),
    SampleFits(
        file_id=_sid("icdb88jqq_flt.fits"),
        source_filename="icdb88jqq_flt.fits",
        display_name="HST WFC3 — flat-calibrated single exposure",
        description=(
            "Flat-fielded single exposure (FLT) with 13 HDUs including "
            "WCS extensions. Reveals NAXIS/data-shape inconsistencies in "
            "table HDU 8 and partial WCS coverage in HDU 9–12 — five "
            "anomalies in total."
        ),
        instrument="HST WFC3/UVIS",
        size_mb=10.3,
        expected_anomalies=5,
    ),
    SampleFits(
        file_id=_sid("icdb88jrq_flc.fits"),
        source_filename="icdb88jrq_flc.fits",
        display_name="HST WFC3 — CTE-corrected exposure",
        description=(
            "Flat-fielded + charge-transfer-efficiency corrected exposure "
            "(FLC) from the same observation as the FLT sample. Adds an "
            "extra HDU for the CTE diagnostics and surfaces the same "
            "five quality concerns plus the CTE artefact."
        ),
        instrument="HST WFC3/UVIS",
        size_mb=10.3,
        expected_anomalies=5,
    ),
    SampleFits(
        file_id=_sid("id0h05m3q_raw.fits"),
        source_filename="id0h05m3q_raw.fits",
        display_name="HST WFC3 — large-format raw exposure",
        description=(
            "Larger raw 2070×3920 mosaic from a different observation "
            "program. Two science HDUs each expose a BITPIX-vs-dtype "
            "mismatch, which the symbolic checker pinpoints by HDU index "
            "for the agent to confirm."
        ),
        instrument="HST WFC3/UVIS",
        size_mb=31.0,
        expected_anomalies=2,
    ),
    SampleFits(
        file_id=_sid("id0h06klq_raw.fits"),
        source_filename="id0h06klq_raw.fits",
        display_name="HST WFC3 — control raw exposure",
        description=(
            "Twin to the previous file from another proposal — useful "
            "as a quick reproducibility check: same anomaly pattern, "
            "different file_id, identical Reflexion output expected "
            "(symbolic critic is deterministic)."
        ),
        instrument="HST WFC3/UVIS",
        size_mb=31.0,
        expected_anomalies=2,
    ),
]


def sample_by_id(file_id: uuid.UUID) -> SampleFits | None:
    """Look up a sample by stable UUID; None if not curated."""
    for s in SAMPLE_FITS:
        if s.file_id == file_id:
            return s
    return None


def is_sample_seeded(sample: SampleFits, storage_root: Path) -> bool:
    return (storage_root / "fits" / sample.storage_filename).exists()
