#!/usr/bin/env python
"""Import a CSV exported from the TTB Public COLA Registry search page."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from cola_etl.csv_import import read_registry_csv
from cola_etl.database import connect, upsert_registry_record
from cola_etl.paths import RAW_SEARCH_RESULTS_DIR, ensure_public_cola_work_dirs


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV saved from the public registry")
    parser.add_argument(
        "--copy-raw",
        action="store_true",
        help="Copy the input CSV into data/work/public-cola/raw/search-results/",
    )
    return parser.parse_args()


def main() -> None:
    """Import registry search results into local SQLite."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    rows = read_registry_csv(args.csv_path)
    raw_path = args.csv_path
    if args.copy_raw:
        raw_path = RAW_SEARCH_RESULTS_DIR / args.csv_path.name
        shutil.copy2(args.csv_path, raw_path)

    with connect() as connection:
        for row in rows:
            upsert_registry_record(connection, row, str(raw_path))
        connection.commit()

    print(f"Imported {len(rows)} registry row(s) from {args.csv_path}")


if __name__ == "__main__":
    main()
