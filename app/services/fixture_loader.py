"""Helpers for loading deterministic demo fixtures.

Notes
-----
Fixtures make tests and evaluator demos reproducible without live scraping,
hosted OCR, or access to confidential rejected applications.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.config import DEMO_FIXTURE_DIR, SOURCE_MAP_DIR
from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult


DEMO_SCENARIOS = {
    "clean": ["clean_malt_pass"],
    "warning": ["warning_missing_comma_fail"],
    "abv": ["abv_prohibited_fail"],
    "net_contents": ["malt_16_fl_oz_fail"],
    "country_origin": ["imported_country_origin_pass"],
    "batch": [
        "clean_malt_pass",
        "warning_missing_comma_fail",
        "warning_title_case_fail",
        "abv_prohibited_fail",
        "malt_16_fl_oz_fail",
        "brand_case_difference_pass",
        "low_confidence_blur_review",
        "brand_mismatch_fail",
        "imported_missing_country_review",
        "conflicting_country_origin_fail",
        "warning_missing_block_review",
        "imported_country_origin_pass",
    ],
}


def load_json(path: Path) -> dict:
    """Load a UTF-8 JSON document from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def fixture_path(fixture_id: str, suffix: str) -> Path:
    """Return the path for a fixture sidecar file."""

    return DEMO_FIXTURE_DIR / f"{fixture_id}.{suffix}"


def load_application(fixture_id: str) -> ColaApplication:
    """Load fixture application fields."""

    return ColaApplication(**load_json(fixture_path(fixture_id, "application.json")))


def load_fixture_ocr(fixture_id: str) -> OCRResult:
    """Load fixture OCR ground truth and mark its source explicitly."""

    payload = load_json(fixture_path(fixture_id, "ocr_text.json"))
    payload["source"] = "fixture ground truth"
    return OCRResult(**payload)


def load_expected_results() -> dict:
    """Load source-map expected results keyed by fixture ID."""

    return load_json(SOURCE_MAP_DIR / "expected-results.json")["fixtures"]


def load_batch_manifest() -> list[dict[str, str]]:
    """Load the generated CSV batch manifest as dictionaries."""

    with (DEMO_FIXTURE_DIR / "batch_manifest.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
