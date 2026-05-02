#!/usr/bin/env python
"""Select a deterministic stratified public COLA sample from imported rows."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from cola_etl.csv_import import normalize_value
from cola_etl.database import connect
from cola_etl.paths import RAW_SEARCH_RESULTS_DIR, SAMPLING_DIR, ensure_public_cola_work_dirs
from cola_etl.sampling import (
    allocate_targets,
    assign_splits,
    parse_registry_date,
    product_family,
    read_sample_days_csv,
    round_robin_sample,
    source_bucket,
    write_json,
    write_rows_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-total", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument(
        "--selected-days-csv",
        default=str(SAMPLING_DIR / "selected_days.csv"),
    )
    parser.add_argument(
        "--imported-days-csv",
        default=str(SAMPLING_DIR / "imported_days.csv"),
    )
    parser.add_argument("--selected-ttbs-csv", default=str(SAMPLING_DIR / "selected_ttbs.csv"))
    parser.add_argument("--split-manifest-csv", default=str(SAMPLING_DIR / "split_manifest.csv"))
    parser.add_argument("--summary-json", default=str(SAMPLING_DIR / "selection_summary.json"))
    return parser.parse_args()


def imported_csv_paths(args: argparse.Namespace) -> list[str]:
    """Return the expected daily search-result CSV paths for this sampling plan."""

    selected_days = read_sample_days_csv(Path(args.selected_days_csv))
    selected_paths = [
        str(RAW_SEARCH_RESULTS_DIR / f"completed-{item.search_date.isoformat()}.csv")
        for item in selected_days
    ]

    imported_days_path = Path(args.imported_days_csv)
    if not imported_days_path.exists():
        return selected_paths

    imported_paths: list[str] = []
    with imported_days_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            csv_path = row.get("csv_path", "").strip()
            if csv_path:
                imported_paths.append(csv_path)

    if not imported_paths:
        return selected_paths
    imported_set = set(imported_paths)
    return [path for path in selected_paths if path in imported_set or Path(path).exists()]


def main() -> None:
    """Build a stratified sample from imported registry rows."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    source_csv_paths = imported_csv_paths(args)
    if not source_csv_paths:
        print("No imported day CSV paths found. Fetch search results first.")
        return

    placeholders = ",".join("?" for _ in source_csv_paths)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                ttb_id,
                permit_no,
                serial_number,
                completed_date,
                fanciful_name,
                brand_name,
                origin,
                origin_desc,
                class_type,
                class_type_desc
            FROM registry_records
            WHERE source_csv IN ({placeholders})
            ORDER BY completed_date, ttb_id
            """,
            source_csv_paths,
        ).fetchall()

    if not rows:
        print("No registry rows imported. Fetch search results first.")
        return

    prepared: list[dict[str, str]] = []
    monthly_counts: dict[str, int] = {}
    by_month: dict[str, list[dict[str, str]]] = {}
    seen_ttb_ids: set[str] = set()
    for row in rows:
        canonical_ttb_id = normalize_value(row["ttb_id"])
        if not canonical_ttb_id or canonical_ttb_id in seen_ttb_ids:
            continue
        seen_ttb_ids.add(canonical_ttb_id)
        completed = parse_registry_date(row["completed_date"])
        month = completed.strftime("%Y-%m")
        prepared_row = {
            "ttb_id": canonical_ttb_id,
            "permit_no": row["permit_no"],
            "serial_number": row["serial_number"],
            "completed_date": row["completed_date"],
            "month_key": month,
            "fanciful_name": row["fanciful_name"],
            "brand_name": row["brand_name"],
            "origin": row["origin"],
            "origin_desc": row["origin_desc"],
            "class_type": row["class_type"],
            "class_type_desc": row["class_type_desc"],
            "product_family": product_family(row["class_type_desc"]),
            "source_bucket": source_bucket(row["permit_no"], row["origin_desc"]),
        }
        prepared.append(prepared_row)
        by_month.setdefault(month, []).append(prepared_row)

    monthly_counts = {month: len(items) for month, items in by_month.items()}
    allocation = allocate_targets(monthly_counts, args.target_total)

    selected: list[dict[str, str]] = []
    for month in sorted(by_month):
        month_rows = round_robin_sample(
            by_month[month],
            allocation.get(month, 0),
            seed=args.seed + int(month.replace("-", "")),
        )
        selected.extend(month_rows)

    selected = sorted(selected, key=lambda row: (row["completed_date"], row["ttb_id"]))
    split_rows = assign_splits(selected, seed=args.seed)

    fieldnames = [
        "ttb_id",
        "completed_date",
        "month_key",
        "permit_no",
        "serial_number",
        "brand_name",
        "fanciful_name",
        "origin",
        "origin_desc",
        "source_bucket",
        "class_type",
        "class_type_desc",
        "product_family",
    ]
    split_fieldnames = fieldnames + ["split"]
    write_rows_csv(Path(args.selected_ttbs_csv), selected, fieldnames)
    write_rows_csv(Path(args.split_manifest_csv), split_rows, split_fieldnames)

    by_month_selected = {}
    for month in sorted(by_month):
        month_selected = [row for row in selected if row["month_key"] == month]
        by_month_selected[month] = {
            "available_rows": len(by_month[month]),
            "selected_rows": len(month_selected),
        }

    split_counts = {"train": 0, "dev": 0, "test": 0}
    for row in split_rows:
        split_counts[row["split"]] += 1

    write_json(
        Path(args.summary_json),
        {
            "target_total": args.target_total,
            "selected_total": len(selected),
            "source_csv_count": len(source_csv_paths),
            "monthly_allocation": allocation,
            "monthly_counts": by_month_selected,
            "split_counts": split_counts,
        },
    )
    print(f"Selected {len(selected)} application(s)")
    print(f"selected_ttbs.csv -> {args.selected_ttbs_csv}")
    print(f"split_manifest.csv -> {args.split_manifest_csv}")


if __name__ == "__main__":
    main()
