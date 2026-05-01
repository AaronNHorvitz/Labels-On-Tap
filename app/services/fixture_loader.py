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
        "imported_country_origin_pass",
    ],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_path(fixture_id: str, suffix: str) -> Path:
    return DEMO_FIXTURE_DIR / f"{fixture_id}.{suffix}"


def load_application(fixture_id: str) -> ColaApplication:
    return ColaApplication(**load_json(fixture_path(fixture_id, "application.json")))


def load_fixture_ocr(fixture_id: str) -> OCRResult:
    payload = load_json(fixture_path(fixture_id, "ocr_text.json"))
    payload["source"] = "fixture ground truth"
    return OCRResult(**payload)


def load_expected_results() -> dict:
    return load_json(SOURCE_MAP_DIR / "expected-results.json")["fixtures"]


def load_batch_manifest() -> list[dict[str, str]]:
    with (DEMO_FIXTURE_DIR / "batch_manifest.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
