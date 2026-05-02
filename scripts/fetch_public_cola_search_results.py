#!/usr/bin/env python
"""Fetch daily public COLA registry search-result CSV files."""

from __future__ import annotations

import argparse
import csv
import time
from datetime import date
from pathlib import Path

from cola_etl.csv_import import read_registry_csv
from cola_etl.database import connect, upsert_registry_record
from cola_etl.http import polite_sleep
from cola_etl.paths import RAW_SEARCH_RESULTS_DIR, SAMPLING_DIR, ensure_public_cola_work_dirs
from cola_etl.sampling import read_sample_days_csv
from cola_etl.search import fetch_search_results_csv


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument("--selected-days-csv", default=str(SAMPLING_DIR / "selected_days.csv"))
    parser.add_argument("--imported-days-csv", default=str(SAMPLING_DIR / "imported_days.csv"))
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--jitter", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry transient daily-search fetch failures before skipping the day",
    )
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--time-budget-seconds", type=float, default=None)
    return parser.parse_args()


def load_dates(args: argparse.Namespace) -> list[date]:
    """Load explicit or planned search dates."""

    if args.date:
        return [date.fromisoformat(item) for item in args.date]
    return [item.search_date for item in read_sample_days_csv(Path(args.selected_days_csv))]


def append_imported_day(
    path: Path,
    *,
    search_date: date,
    csv_path: Path,
    row_count: int,
) -> None:
    """Append one imported-day checkpoint row."""

    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["search_date", "csv_path", "row_count", "imported_at"],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "search_date": search_date.isoformat(),
                "csv_path": str(csv_path),
                "row_count": row_count,
                "imported_at": int(time.time()),
            }
        )


def fetch_search_results_with_retries(
    search_date: date,
    *,
    timeout: float,
    verify: bool,
    retries: int,
    delay: float,
    jitter: float,
) -> bytes | None:
    """Fetch one daily search export, retrying transient network failures."""

    for attempt in range(1, retries + 2):
        try:
            csv_bytes, _, _ = fetch_search_results_csv(
                search_date,
                timeout=timeout,
                verify=verify,
            )
            return csv_bytes
        except Exception as exc:  # noqa: BLE001 - ETL should keep walking.
            if attempt > retries:
                print(f"  failed after {attempt} attempt(s): {exc}")
                return None
            print(f"  transient fetch error on attempt {attempt}; retrying: {exc}")
            polite_sleep(delay, jitter)
    return None


def main() -> None:
    """Fetch and import daily public search-result CSV exports."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    dates = load_dates(args)
    if args.limit is not None:
        dates = dates[: args.limit]
    if not dates:
        print("No search dates selected.")
        return

    deadline = (
        time.monotonic() + args.time_budget_seconds
        if args.time_budget_seconds is not None
        else None
    )
    imported_path = Path(args.imported_days_csv)
    with connect() as connection:
        for index, search_date in enumerate(dates, start=1):
            if deadline is not None and time.monotonic() >= deadline:
                print("Time budget reached before next search fetch.")
                break

            csv_path = RAW_SEARCH_RESULTS_DIR / f"completed-{search_date.isoformat()}.csv"
            if args.resume and csv_path.exists():
                print(f"[{index}/{len(dates)}] skip existing {search_date.isoformat()}")
                continue

            print(f"[{index}/{len(dates)}] fetch search results for {search_date.isoformat()}")
            csv_bytes = fetch_search_results_with_retries(
                search_date,
                timeout=args.timeout,
                verify=not args.insecure,
                retries=args.retries,
                delay=args.delay,
                jitter=args.jitter,
            )
            if csv_bytes is None:
                continue
            csv_path.write_bytes(csv_bytes)
            rows = read_registry_csv(csv_path)
            for row in rows:
                upsert_registry_record(connection, row, str(csv_path))
            connection.commit()
            append_imported_day(
                imported_path,
                search_date=search_date,
                csv_path=csv_path,
                row_count=len(rows),
            )
            print(f"  imported {len(rows)} row(s)")
            if index < len(dates):
                polite_sleep(args.delay, args.jitter)


if __name__ == "__main__":
    main()
