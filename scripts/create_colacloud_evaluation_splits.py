#!/usr/bin/env python
"""Create application-level COLA Cloud evaluation split manifests.

The split is intentionally application-level: field-pair examples must be
generated after this step so the same TTB ID cannot leak between train,
validation, and holdout.

Default design:

* development cohort: ``official-sample-3000-balanced``
* train split: 2,000 applications from the development cohort
* validation split: 1,000 applications from the development cohort
* locked holdout: all 3,000 applications from
  ``official-sample-next-3000-balanced``

All generated manifests live under gitignored ``data/work/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COLA_WORK_ROOT = REPO_ROOT / "data" / "work" / "cola"
DEFAULT_OUTPUT = COLA_WORK_ROOT / "evaluation-splits" / "field-support-v1"

BASE_FIELDS = [
    "ttb_id",
    "split",
    "source_run",
    "approval_date",
    "month_key",
    "brand_name",
    "product_name",
    "product_type",
    "class_name",
    "origin_name",
    "origin_bucket",
    "image_count",
    "image_bucket",
    "has_barcode",
    "permit_number",
    "stratum",
    "source_fetch_order",
    "application_path",
    "image_dir",
    "local_image_count",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-run", default="official-sample-3000-balanced")
    parser.add_argument("--holdout-run", default="official-sample-next-3000-balanced")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--validation-size", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into a list of dictionaries."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_ids(path: Path) -> set[str]:
    """Read one TTB ID per line."""

    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def stable_int(value: str) -> int:
    """Return a deterministic integer for stable random seeding."""

    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def image_files(path: Path) -> list[Path]:
    """Return local image files under a per-TTB image directory."""

    if not path.exists():
        return []
    return [
        item
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]


def run_root(name: str) -> Path:
    """Return a named COLA Cloud work collection root."""

    root = COLA_WORK_ROOT / name
    if not root.exists():
        raise FileNotFoundError(f"Missing COLA work collection: {root}")
    return root


def fetched_rows(run_name: str) -> list[dict[str, str]]:
    """Return selected rows that have fetched detail/application JSON files."""

    root = run_root(run_name)
    selected_path = root / "sampling" / "selected_ttbs.csv"
    detail_ids_path = root / "api" / "selected-detail-ttb-ids.txt"
    if not selected_path.exists():
        raise FileNotFoundError(f"Missing selected TTB manifest: {selected_path}")
    if not detail_ids_path.exists():
        raise FileNotFoundError(f"Missing selected detail ID file: {detail_ids_path}")

    fetched = read_ids(detail_ids_path)
    rows_by_id = {row["ttb_id"]: row for row in read_csv(selected_path) if row.get("ttb_id") in fetched}
    missing = fetched - set(rows_by_id)
    if missing:
        raise ValueError(f"{run_name} has fetched IDs missing from selected manifest: {sorted(missing)[:5]}")

    rows: list[dict[str, str]] = []
    for ident in sorted(fetched, key=lambda value: int(rows_by_id[value].get("fetch_order") or 0)):
        source = rows_by_id[ident]
        application_path = root / "applications" / f"{ident}.json"
        image_dir = root / "images" / ident
        if not application_path.exists():
            raise FileNotFoundError(f"Missing parsed application JSON: {application_path}")
        item = dict(source)
        item["source_run"] = run_name
        item["source_fetch_order"] = source.get("fetch_order", "")
        item["application_path"] = str(application_path.relative_to(REPO_ROOT))
        item["image_dir"] = str(image_dir.relative_to(REPO_ROOT))
        item["local_image_count"] = str(len(image_files(image_dir)))
        rows.append(item)
    return rows


def allocate_validation(rows: list[dict[str, str]], validation_size: int) -> dict[str, int]:
    """Allocate validation counts across strata with largest remainders."""

    by_stratum: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_stratum[row.get("stratum") or "unknown"].append(row)

    total = len(rows)
    if validation_size < 0 or validation_size > total:
        raise ValueError(f"validation_size must be between 0 and {total}")

    allocation: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for stratum, bucket in sorted(by_stratum.items()):
        exact = validation_size * (len(bucket) / total)
        count = min(len(bucket), int(exact))
        allocation[stratum] = count
        remainders.append((exact - count, stratum))

    remaining = validation_size - sum(allocation.values())
    for _, stratum in sorted(remainders, reverse=True):
        if remaining <= 0:
            break
        if allocation[stratum] < len(by_stratum[stratum]):
            allocation[stratum] += 1
            remaining -= 1

    if remaining:
        for stratum, bucket in sorted(by_stratum.items()):
            if remaining <= 0:
                break
            if allocation[stratum] < len(bucket):
                allocation[stratum] += 1
                remaining -= 1

    if sum(allocation.values()) != validation_size:
        raise AssertionError("Validation allocation did not hit requested size")
    return allocation


def split_development_rows(
    rows: list[dict[str, str]],
    *,
    train_size: int,
    validation_size: int,
    seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split development rows into train and validation sets."""

    if train_size + validation_size != len(rows):
        raise ValueError(
            f"train_size + validation_size must equal development row count: "
            f"{train_size} + {validation_size} != {len(rows)}"
        )

    allocation = allocate_validation(rows, validation_size)
    by_stratum: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_stratum[row.get("stratum") or "unknown"].append(dict(row))

    train: list[dict[str, str]] = []
    validation: list[dict[str, str]] = []
    for stratum, bucket in sorted(by_stratum.items()):
        rng = random.Random(seed + stable_int(stratum))
        rng.shuffle(bucket)
        validation_cut = allocation[stratum]
        for item in bucket[:validation_cut]:
            item["split"] = "validation"
            validation.append(item)
        for item in bucket[validation_cut:]:
            item["split"] = "train"
            train.append(item)

    train.sort(key=lambda row: (row["month_key"], row["stratum"], row["ttb_id"]))
    validation.sort(key=lambda row: (row["month_key"], row["stratum"], row["ttb_id"]))
    if len(train) != train_size or len(validation) != validation_size:
        raise AssertionError("Unexpected train/validation split sizes")
    return train, validation


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a split manifest CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BASE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean_cell(row.get(field, "")) for field in BASE_FIELDS})


def clean_cell(value: object) -> str:
    """Return a one-line CSV cell value."""

    return " ".join(str(value or "").split())


def write_ids(path: Path, rows: list[dict[str, str]]) -> None:
    """Write one TTB ID per line."""

    path.write_text("\n".join(row["ttb_id"] for row in rows) + "\n", encoding="utf-8")


def distribution(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    """Return a sorted count dictionary for one row field."""

    counts = Counter(row.get(field) or "unknown" for row in rows)
    return dict(sorted(counts.items()))


def split_summary(
    *,
    args: argparse.Namespace,
    train: list[dict[str, str]],
    validation: list[dict[str, str]],
    holdout: list[dict[str, str]],
) -> dict[str, Any]:
    """Build the split summary JSON."""

    first_ids = {row["ttb_id"] for row in train + validation}
    holdout_ids = {row["ttb_id"] for row in holdout}
    overlap = sorted(first_ids & holdout_ids)
    if overlap:
        raise AssertionError(f"Holdout overlaps with development IDs: {overlap[:5]}")

    all_rows = {"train": train, "validation": validation, "holdout": holdout}
    return {
        "split_name": args.output_dir.name,
        "created_by": "scripts/create_colacloud_evaluation_splits.py",
        "seed": args.seed,
        "development_source_run": args.dev_run,
        "holdout_source_run": args.holdout_run,
        "design": {
            "unit": "COLA application / TTB ID",
            "train": len(train),
            "validation": len(validation),
            "holdout": len(holdout),
            "leakage_rule": "Generate field-pair examples only after this split.",
            "holdout_policy": "Do not tune thresholds or features on holdout results.",
        },
        "overlap": {
            "development_holdout": len(overlap),
        },
        "image_counts": {
            name: sum(int(row.get("local_image_count") or 0) for row in rows)
            for name, rows in all_rows.items()
        },
        "distributions": {
            name: {
                "month_key": distribution(rows, "month_key"),
                "product_type": distribution(rows, "product_type"),
                "origin_bucket": distribution(rows, "origin_bucket"),
                "image_bucket": distribution(rows, "image_bucket"),
            }
            for name, rows in all_rows.items()
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    """Create split manifests."""

    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"Output directory already has files; pass --force: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    development_rows = fetched_rows(args.dev_run)
    holdout = fetched_rows(args.holdout_run)
    for row in holdout:
        row["split"] = "holdout"

    train, validation = split_development_rows(
        development_rows,
        train_size=args.train_size,
        validation_size=args.validation_size,
        seed=args.seed,
    )

    all_rows = train + validation + holdout
    write_manifest(output_dir / "train_applications.csv", train)
    write_manifest(output_dir / "validation_applications.csv", validation)
    write_manifest(output_dir / "holdout_applications.csv", holdout)
    write_manifest(output_dir / "all_applications.csv", all_rows)
    write_ids(output_dir / "train_ttb_ids.txt", train)
    write_ids(output_dir / "validation_ttb_ids.txt", validation)
    write_ids(output_dir / "holdout_ttb_ids.txt", holdout)
    write_json(
        output_dir / "split_summary.json",
        split_summary(args=args, train=train, validation=validation, holdout=holdout),
    )

    print(f"Split directory: {output_dir.relative_to(REPO_ROOT)}")
    print(f"Train applications: {len(train)}")
    print(f"Validation applications: {len(validation)}")
    print(f"Holdout applications: {len(holdout)}")
    print(f"Total applications: {len(all_rows)}")
    print(f"Development/holdout overlap: {len({row['ttb_id'] for row in train + validation} & {row['ttb_id'] for row in holdout})}")


if __name__ == "__main__":
    main()
