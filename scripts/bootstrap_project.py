#!/usr/bin/env python3
"""
Bootstrap source-backed project data needed by tests and demos.

This is the one command evaluators and contributors should run before tests:

    python scripts/bootstrap_project.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}")
    subprocess.run(args, cwd=ROOT, check=True)


def assert_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Expected {label} was not created: {path}")
    print(f"verified: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Labels On Tap project data.")
    parser.add_argument("--force", action="store_true", help="Regenerate demo fixtures.")
    args = parser.parse_args()

    run_step([sys.executable, "scripts/bootstrap_legal_corpus.py"])

    seed_args = [sys.executable, "scripts/seed_demo_fixtures.py"]
    if args.force:
        seed_args.append("--force")
    run_step(seed_args)

    run_step([sys.executable, "scripts/validate_legal_corpus.py"])

    assert_exists(ROOT / "data/fixtures/demo/clean_malt_pass.png", "clean demo fixture")
    assert_exists(ROOT / "data/fixtures/demo/batch_manifest.csv", "batch manifest")
    assert_exists(ROOT / "data/source-maps/expected-results.json", "expected results")

    print("\nProject bootstrap complete.")


if __name__ == "__main__":
    main()
