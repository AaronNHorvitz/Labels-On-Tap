#!/usr/bin/env python3
"""
Bootstrap source-backed project data needed by tests and demos.

This is the one command evaluators and contributors should run before tests:

    python scripts/bootstrap_project.py
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIXTURES = [
    ROOT / "data/fixtures/demo/clean_malt_pass.png",
    ROOT / "data/fixtures/demo/warning_missing_comma_fail.png",
    ROOT / "data/fixtures/demo/warning_title_case_fail.png",
    ROOT / "data/fixtures/demo/abv_prohibited_fail.png",
    ROOT / "data/fixtures/demo/malt_16_fl_oz_fail.png",
    ROOT / "data/fixtures/demo/brand_case_difference_pass.png",
    ROOT / "data/fixtures/demo/low_confidence_blur_review.png",
]


def run_step(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}")
    subprocess.run(args, cwd=ROOT, check=True)


def assert_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Expected {label} was not created: {path}")
    print(f"verified: {path}")


def fixtures_missing() -> bool:
    return any(not path.exists() for path in REQUIRED_FIXTURES)


def validate_expected_results() -> None:
    path = ROOT / "data/source-maps/expected-results.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", {})
    if not fixtures:
        raise SystemExit("expected-results.json contains no fixtures")

    for fixture_id, expected in fixtures.items():
        checked = expected.get("checked_rule_ids")
        triggered = expected.get("triggered_rule_ids")
        if not isinstance(checked, list):
            raise SystemExit(f"{fixture_id}: checked_rule_ids must be a list")
        if not isinstance(triggered, list):
            raise SystemExit(f"{fixture_id}: triggered_rule_ids must be a list")
        if expected.get("overall_verdict") == "pass" and triggered:
            raise SystemExit(f"{fixture_id}: pass fixture must not have triggered_rule_ids")

    print(f"verified: {path}")


def validate_fixture_provenance() -> None:
    path = ROOT / "data/source-maps/fixture-provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", [])
    if not fixtures:
        raise SystemExit("fixture-provenance.json contains no fixtures")

    for fixture in fixtures:
        file_path = ROOT / fixture["file_path"]
        if fixture.get("source_type") == "synthetic_generation" and not file_path.exists():
            raise SystemExit(f"fixture provenance references missing file: {file_path}")

    print(f"verified: {path}")


def validate_batch_manifest() -> None:
    path = ROOT / "data/fixtures/demo/batch_manifest.csv"
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 5:
        raise SystemExit("batch_manifest.csv must contain at least five demo rows")
    print(f"verified: {path} ({len(rows)} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Labels On Tap project data.")
    parser.add_argument("--force", action="store_true", help="Regenerate demo fixtures.")
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="Generate fixtures only when required demo files are missing.",
    )
    args = parser.parse_args()

    run_step([sys.executable, "scripts/bootstrap_legal_corpus.py"])

    seed_args = [sys.executable, "scripts/seed_demo_fixtures.py"]
    if args.force:
        seed_args.append("--force")
    if args.force or not args.if_missing or fixtures_missing():
        run_step(seed_args)
    else:
        print("demo fixtures already exist; skipping generation")

    run_step([sys.executable, "scripts/validate_legal_corpus.py"])

    assert_exists(ROOT / "data/fixtures/demo/clean_malt_pass.png", "clean demo fixture")
    assert_exists(ROOT / "data/fixtures/demo/batch_manifest.csv", "batch manifest")
    assert_exists(ROOT / "data/source-maps/expected-results.json", "expected results")
    validate_expected_results()
    validate_fixture_provenance()
    validate_batch_manifest()

    print("\nProject bootstrap complete.")


if __name__ == "__main__":
    main()
