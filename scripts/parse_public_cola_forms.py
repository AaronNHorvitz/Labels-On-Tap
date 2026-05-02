#!/usr/bin/env python
"""Parse saved public COLA form HTML files into JSON and SQLite metadata."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from cola_etl.csv_import import normalize_value
from cola_etl.database import connect, record_parsed_form, replace_attachments
from cola_etl.parser import parse_public_cola_form
from cola_etl.paths import PARSED_APPLICATIONS_DIR, RAW_FORMS_DIR, ensure_public_cola_work_dirs


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", default=[], help="TTB ID to parse")
    parser.add_argument("--ttb-id-file", help="File containing one TTB ID per line")
    parser.add_argument("--limit", type=int, default=None, help="Maximum forms to parse")
    parser.add_argument("--force", action="store_true", help="Reparse existing JSON files")
    parser.add_argument(
        "--time-budget-seconds",
        type=float,
        default=None,
        help="Stop cleanly once this many seconds have elapsed in the current run",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Alias for the default skip-existing behavior; useful for orchestration scripts",
    )
    return parser.parse_args()


def read_ttb_ids_from_file(path: str | None) -> list[str]:
    """Read one TTB ID per line from a text file."""

    if not path:
        return []
    return [
        normalize_value(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def form_paths(ttb_ids: list[str], limit: int | None) -> list[Path]:
    """Return saved form paths to parse."""

    if ttb_ids:
        paths = [RAW_FORMS_DIR / f"{ttb_id}.html" for ttb_id in ttb_ids]
    else:
        paths = sorted(RAW_FORMS_DIR.glob("*.html"))
    return paths[:limit] if limit else paths


def read_declared_html(path: Path) -> str:
    """Read a saved public form using its declared legacy charset when present."""

    raw = path.read_bytes()
    head = raw[:2048].decode("ascii", errors="ignore")
    match = re.search(r"charset=([A-Za-z0-9_-]+)", head, re.IGNORECASE)
    encoding = match.group(1) if match else "utf-8"
    return raw.decode(encoding, errors="replace")


def main() -> None:
    """Parse saved form HTML into structured JSON."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    deadline = (
        time.monotonic() + args.time_budget_seconds
        if args.time_budget_seconds is not None
        else None
    )
    paths = form_paths(args.ttb_id + read_ttb_ids_from_file(args.ttb_id_file), args.limit)
    if not paths:
        print(f"No saved form HTML found in {RAW_FORMS_DIR}")
        return

    with connect() as connection:
        parsed_count = 0
        for path in paths:
            if deadline is not None and time.monotonic() >= deadline:
                print("Time budget reached before next parse step.")
                break
            ttb_id = path.stem
            output_path = PARSED_APPLICATIONS_DIR / f"{ttb_id}.json"
            if output_path.exists() and not args.force:
                print(f"skip existing parsed JSON {ttb_id}")
                continue
            try:
                parsed = parse_public_cola_form(
                    read_declared_html(path),
                    source_url=(
                        "https://ttbonline.gov/colasonline/viewColaDetails.do"
                        f"?action=publicFormDisplay&ttbid={ttb_id}"
                    ),
                )
                output_path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
                record_parsed_form(
                    connection,
                    ttb_id=parsed["ttb_id"] or ttb_id,
                    parsed_json_path=str(output_path),
                    parse_status="parsed",
                )
                replace_attachments(
                    connection,
                    ttb_id=parsed["ttb_id"] or ttb_id,
                    attachments=parsed["attachments"],
                )
                parsed_count += 1
            except Exception as exc:  # noqa: BLE001 - record parse failure and continue.
                record_parsed_form(
                    connection,
                    ttb_id=ttb_id,
                    parsed_json_path=None,
                    parse_status="error",
                    error=str(exc),
                )
                print(f"error parsing {path}: {exc}")
            connection.commit()

    print(f"Parsed {parsed_count} form(s)")


if __name__ == "__main__":
    main()
