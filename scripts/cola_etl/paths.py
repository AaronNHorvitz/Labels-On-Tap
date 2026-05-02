"""Filesystem paths used by the local public COLA ETL workspace.

Notes
-----
All paths in this module point either to ``data/work/`` for gitignored bulk
work or ``data/fixtures/public-cola/`` for curated, reviewable exports.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_COLA_WORK_DIR = REPO_ROOT / "data" / "work" / "public-cola"
RAW_SEARCH_RESULTS_DIR = PUBLIC_COLA_WORK_DIR / "raw" / "search-results"
RAW_FORMS_DIR = PUBLIC_COLA_WORK_DIR / "raw" / "forms"
RAW_IMAGES_DIR = PUBLIC_COLA_WORK_DIR / "raw" / "images"
PARSED_APPLICATIONS_DIR = PUBLIC_COLA_WORK_DIR / "parsed" / "applications"
PARSED_OCR_DIR = PUBLIC_COLA_WORK_DIR / "parsed" / "ocr"
SAMPLING_DIR = PUBLIC_COLA_WORK_DIR / "sampling"
PUBLIC_COLA_DB_PATH = PUBLIC_COLA_WORK_DIR / "registry.sqlite"

PUBLIC_COLA_FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "public-cola"


def ensure_public_cola_work_dirs() -> None:
    """Create the local public COLA ETL directory tree."""

    for path in (
        RAW_SEARCH_RESULTS_DIR,
        RAW_FORMS_DIR,
        RAW_IMAGES_DIR,
        PARSED_APPLICATIONS_DIR,
        PARSED_OCR_DIR,
        SAMPLING_DIR,
        PUBLIC_COLA_FIXTURE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
