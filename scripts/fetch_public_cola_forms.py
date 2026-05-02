#!/usr/bin/env python
"""Fetch public COLA printable-form HTML pages by TTB ID.

This command is intentionally slow by default. Use small limits while
developing, inspect raw files, then parse and export curated fixtures.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from cola_etl.csv_import import normalize_value
from cola_etl.database import connect, list_ttb_ids, record_form_fetch
from cola_etl.http import make_client, polite_sleep
from cola_etl.paths import RAW_FORMS_DIR, ensure_public_cola_work_dirs


FORM_URL_TEMPLATE = (
    "https://ttbonline.gov/colasonline/viewColaDetails.do"
    "?action=publicFormDisplay&ttbid={ttb_id}"
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", default=[], help="TTB ID to fetch")
    parser.add_argument("--ttb-id-file", help="File containing one TTB ID per line")
    parser.add_argument("--limit", type=int, default=None, help="Maximum forms to fetch")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Fetch only registry rows without saved form HTML",
    )
    parser.add_argument("--force", action="store_true", help="Refetch existing HTML files")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between requests")
    parser.add_argument("--jitter", type=float, default=1.0, help="Random extra delay seconds")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--time-budget-seconds",
        type=float,
        default=None,
        help="Stop cleanly once this many seconds have elapsed in the current run",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for public TTB registry fetches when local CA validation fails",
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


def main() -> None:
    """Fetch public form HTML pages into the local work directory."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    deadline = (
        time.monotonic() + args.time_budget_seconds
        if args.time_budget_seconds is not None
        else None
    )
    with connect() as connection:
        explicit_ids = args.ttb_id + read_ttb_ids_from_file(args.ttb_id_file)
        ttb_ids = list_ttb_ids(
            connection,
            explicit_ids=explicit_ids,
            missing_forms_only=args.missing_only,
            limit=args.limit,
        )
        if not ttb_ids:
            print("No TTB IDs to fetch. Import a search-result CSV or pass --ttb-id.")
            return

        with make_client(timeout=args.timeout, verify=not args.insecure) as client:
            for index, ttb_id in enumerate(ttb_ids, start=1):
                if deadline is not None and time.monotonic() >= deadline:
                    print("Time budget reached before next form fetch.")
                    break
                url = FORM_URL_TEMPLATE.format(ttb_id=ttb_id)
                output_path = RAW_FORMS_DIR / f"{ttb_id}.html"
                if output_path.exists() and not args.force:
                    print(f"[{index}/{len(ttb_ids)}] skip existing {ttb_id}")
                    continue

                print(f"[{index}/{len(ttb_ids)}] fetch {ttb_id}")
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    output_path.write_bytes(response.content)
                    record_form_fetch(
                        connection,
                        ttb_id=ttb_id,
                        detail_url=url,
                        raw_html_path=str(output_path),
                        http_status=response.status_code,
                    )
                except Exception as exc:  # noqa: BLE001 - ETL should keep walking.
                    record_form_fetch(
                        connection,
                        ttb_id=ttb_id,
                        detail_url=url,
                        raw_html_path=None,
                        http_status=getattr(getattr(exc, "response", None), "status_code", None),
                        error=str(exc),
                    )
                    print(f"  error: {exc}")
                connection.commit()
                if index < len(ttb_ids):
                    polite_sleep(args.delay, args.jitter)


if __name__ == "__main__":
    main()
