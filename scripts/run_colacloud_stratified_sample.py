#!/usr/bin/env python
"""Build a stratified COLA Cloud corpus for local OCR evaluation.

This script is intentionally separate from the TTB Public COLA Registry ETL.
It uses COLA Cloud as a development-only public-data bridge when TTBOnline.gov
is unavailable, but preserves TTB IDs so the same sample can be reconciled
against official printable forms later.

The workflow is staged and resumable:

1. Select deterministic business days across month strata.
2. Fetch list records for those days and build a candidate pool.
3. Select a target sample without replacement across month, product, import,
   and image-complexity strata.
4. Optionally fetch details and label images for the first N selected records.

All raw/bulk artifacts stay under gitignored ``data/work/cola/<run-name>/``.
The script also mirrors parsed applications and image paths into the existing
``data/work/public-cola/`` workspace so ``evaluate_public_cola_ocr.py`` can run
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cola_etl.csv_import import normalize_value
from cola_etl.images import validate_image_bytes
from cola_etl.paths import PARSED_APPLICATIONS_DIR, RAW_IMAGES_DIR
from cola_etl.sampling import US_DOMESTIC_ORIGINS, SampleDay, month_business_days, write_sample_days_csv
from pull_colacloud_api_corpus import (
    attachment_id_for_panel,
    api_key,
    client_for_key,
    field,
    image_index,
    images_for_record,
    import_records,
    response_detail,
    response_items,
    save_json,
    store_image,
    ttb_id,
    download_image,
)


COLA_WORK_ROOT = REPO_ROOT / "data" / "work" / "cola"
DEFAULT_START = date(2025, 5, 1)
DEFAULT_END = date(2026, 5, 1)
PRODUCT_TYPES = ("wine", "malt beverage", "distilled spirits", "other")
DOMESTIC_ORIGINS = {item.lower() for item in US_DOMESTIC_ORIGINS} | {
    "american",
    "united states",
    "usa",
    "u.s.",
    "us",
}

CANDIDATE_FIELDS = [
    "ttb_id",
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
]

SELECTED_FIELDS = CANDIDATE_FIELDS + ["split", "fetch_order"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="official-sample-1500")
    parser.add_argument("--target", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument(
        "--split-mode",
        choices=("train-dev-test", "calibration-holdout"),
        default="train-dev-test",
        help=(
            "Use train/dev/test for threshold work, or calibration/holdout for "
            "an exact 50/50 evaluation design."
        ),
    )
    parser.add_argument(
        "--calibration-size",
        type=int,
        default=None,
        help="Exact calibration split size when --split-mode=calibration-holdout",
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--days-per-month", type=int, default=2)
    parser.add_argument(
        "--min-candidates-per-month",
        type=int,
        default=0,
        help="When >0, keep drawing sampled days in each month until this many usable candidates are found",
    )
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-pages-per-day", type=int, default=20)
    parser.add_argument(
        "--delay",
        type=float,
        default=6.5,
        help="Delay between API list/detail requests; default respects 10 requests/minute",
    )
    parser.add_argument("--image-delay", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=0,
        help="Fetch detail/images for the first N selected records in deterministic fetch order",
    )
    parser.add_argument("--download-images", action="store_true")
    parser.add_argument("--force-images", action="store_true")
    parser.add_argument("--refresh-candidates", action="store_true")
    parser.add_argument(
        "--include-existing-cola-work",
        action="store_true",
        help="Allow TTB IDs already present in data/work/cola/* selected-detail files",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def collection_dir(run_name: str) -> Path:
    """Return the segregated data/work/cola collection directory."""

    root = COLA_WORK_ROOT / run_name
    for child in ("api/list", "api/details", "applications", "images", "evaluation", "sampling"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows to CSV with stable columns."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read CSV rows into dictionaries."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def existing_colawork_ids(current_root: Path) -> set[str]:
    """Return IDs already fetched into other data/work/cola collections."""

    ids: set[str] = set()
    for path in COLA_WORK_ROOT.glob("*/api/selected-detail-ttb-ids.txt"):
        if current_root in path.parents:
            continue
        ids.update(
            normalize_value(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if normalize_value(line)
        )
    return ids


def month_key(value: str) -> str:
    """Return a YYYY-MM key from an ISO approval date string."""

    return value[:7] if len(value) >= 7 else "unknown"


def origin_bucket(record: dict[str, Any]) -> str:
    """Classify a record as domestic or imported from origin text."""

    origin = normalize_value(field(record, "origin_name")).lower()
    if not origin:
        return "unknown"
    return "domestic" if origin in DOMESTIC_ORIGINS else "imported"


def product_type(record: dict[str, Any]) -> str:
    """Normalize the API product type into a broad product stratum."""

    value = normalize_value(field(record, "product_type")).lower()
    return value if value in PRODUCT_TYPES else "other"


def image_count(record: dict[str, Any]) -> int:
    """Return image count as an integer."""

    try:
        return int(field(record, "image_count") or 0)
    except (TypeError, ValueError):
        return len(images_for_record(record))


def candidate_row(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map an API list record into the sampling candidate contract."""

    ident = ttb_id(record)
    if not ident:
        return None
    approval_date = normalize_value(field(record, "approval_date", "latest_update_date"))
    if not approval_date:
        return None
    images = image_count(record)
    if images <= 0:
        return None
    product = product_type(record)
    origin = origin_bucket(record)
    image_bucket = "multi_panel" if images > 1 else "single_panel"
    stratum = "|".join([month_key(approval_date), product, origin, image_bucket])
    return {
        "ttb_id": ident,
        "approval_date": approval_date,
        "month_key": month_key(approval_date),
        "brand_name": normalize_value(field(record, "brand_name")),
        "product_name": normalize_value(field(record, "product_name")),
        "product_type": product,
        "class_name": normalize_value(field(record, "class_name")),
        "origin_name": normalize_value(field(record, "origin_name")),
        "origin_bucket": origin,
        "image_count": images,
        "image_bucket": image_bucket,
        "has_barcode": str(field(record, "has_barcode")).lower(),
        "permit_number": normalize_value(field(record, "permit_number")),
        "stratum": stratum,
    }


def planned_days_by_month(args: argparse.Namespace) -> dict[str, list[SampleDay]]:
    """Choose deterministic candidate days bucketed by month.

    ``days_per_month`` is treated as a cap. When
    ``min_candidates_per_month`` is set, the fetch loop can stop early once a
    month has enough usable candidates. This preserves random month coverage
    while avoiding unnecessary list-record spend in high-volume months.
    """

    buckets = month_business_days(args.start_date, args.end_date)
    planned: dict[str, list[SampleDay]] = {}
    for month, days in sorted(buckets.items()):
        month_seed = args.seed + int(month.replace("-", ""))
        rng = random.Random(month_seed)
        pool = list(days)
        rng.shuffle(pool)
        chosen = pool[: min(args.days_per_month, len(pool))]
        planned[month] = [
            SampleDay(
                month_key=month,
                search_date=sample_date,
                selection_rank=index,
                role="primary" if index <= 2 else "backup",
            )
            for index, sample_date in enumerate(chosen, start=1)
        ]
    return planned


def list_page_path(root: Path, sample_date: date, page: int) -> Path:
    """Return the raw API list path for one date/page."""

    return root / "api" / "list" / f"{sample_date.isoformat()}-page-{page:04d}.json"


def fetch_day_candidates(
    client: httpx.Client,
    *,
    root: Path,
    sample_date: date,
    per_page: int,
    max_pages: int,
    delay: float,
    resume: bool,
) -> list[dict[str, Any]]:
    """Fetch all list pages for one approval date."""

    records: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        path = list_page_path(root, sample_date, page)
        if resume and path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            response = client.get(
                "/colas",
                params={
                    "approval_date_from": sample_date.isoformat(),
                    "approval_date_to": sample_date.isoformat(),
                    "page": page,
                    "per_page": per_page,
                },
            )
            response.raise_for_status()
            payload = response.json()
            save_json(path, payload)
            if delay:
                time.sleep(delay)

        items = response_items(payload)
        records.extend(items)
        pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        if not items or not pagination.get("has_more"):
            break

    return records


def build_candidate_pool(
    client: httpx.Client,
    *,
    args: argparse.Namespace,
    root: Path,
    exclusions: set[str],
) -> list[dict[str, Any]]:
    """Fetch daily list records and write a deduplicated candidate pool."""

    candidate_path = root / "sampling" / "candidate_pool.csv"
    if args.resume and candidate_path.exists() and not args.refresh_candidates:
        return read_csv(candidate_path)

    rows_by_id: dict[str, dict[str, Any]] = {}
    day_plan = planned_days_by_month(args)
    imported_days: list[dict[str, Any]] = []
    fetched_days: list[SampleDay] = []
    total_planned_days = sum(len(days) for days in day_plan.values())
    day_index = 0
    for month, days in sorted(day_plan.items()):
        monthly_usable = 0
        for sample_day in days:
            day_index += 1
            sample_date = sample_day.search_date
            print(f"[list {day_index}/{total_planned_days}] {sample_date.isoformat()}")
            records = fetch_day_candidates(
                client,
                root=root,
                sample_date=sample_date,
                per_page=args.per_page,
                max_pages=args.max_pages_per_day,
                delay=args.delay,
                resume=args.resume,
            )
            usable = 0
            for record in records:
                row = candidate_row(record)
                if row is None or row["ttb_id"] in exclusions:
                    continue
                rows_by_id.setdefault(row["ttb_id"], row)
                usable += 1
            monthly_usable += usable
            fetched_days.append(sample_day)
            imported_days.append(
                {
                    "approval_date": sample_date.isoformat(),
                    "month_key": month,
                    "records_returned": len(records),
                    "usable_records": usable,
                    "monthly_usable_so_far": monthly_usable,
                }
            )
            print(f"  returned {len(records)} record(s), usable {usable}")
            if args.min_candidates_per_month and monthly_usable >= args.min_candidates_per_month:
                break

    candidates = sorted(rows_by_id.values(), key=lambda row: (row["approval_date"], row["ttb_id"]))
    write_sample_days_csv(root / "sampling" / "selected_days.csv", fetched_days)
    write_csv(candidate_path, candidates, CANDIDATE_FIELDS)
    write_csv(
        root / "sampling" / "imported_days.csv",
        imported_days,
        ["approval_date", "month_key", "records_returned", "usable_records", "monthly_usable_so_far"],
    )
    return candidates


def allocate_months(candidates: list[dict[str, Any]], target: int, *, floor: int) -> dict[str, int]:
    """Allocate sample counts across months with a coverage floor."""

    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_month[str(row["month_key"])].append(row)

    allocation = {month: min(floor, len(rows)) for month, rows in by_month.items()}
    remaining = min(target, len(candidates)) - sum(allocation.values())
    capacities = {month: max(0, len(rows) - allocation[month]) for month, rows in by_month.items()}
    capacity_total = sum(capacities.values())
    if remaining <= 0 or capacity_total <= 0:
        return allocation

    fractions: list[tuple[float, str]] = []
    for month, capacity in capacities.items():
        exact = remaining * (capacity / capacity_total)
        add = min(capacity, int(exact))
        allocation[month] += add
        fractions.append((exact - add, month))

    leftover = min(target, len(candidates)) - sum(allocation.values())
    for _, month in sorted(fractions, reverse=True):
        if leftover <= 0:
            break
        if allocation[month] < len(by_month[month]):
            allocation[month] += 1
            leftover -= 1
    return allocation


def balanced_month_sample(rows: list[dict[str, Any]], target: int, *, seed: int) -> list[dict[str, Any]]:
    """Sample one month with round-robin secondary strata balancing."""

    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_stratum[str(row["stratum"])].append(dict(row))

    rng = random.Random(seed)
    keys = sorted(by_stratum)
    for key in keys:
        rng.shuffle(by_stratum[key])
    rng.shuffle(keys)

    selected: list[dict[str, Any]] = []
    while len(selected) < target and keys:
        next_keys: list[str] = []
        for key in keys:
            bucket = by_stratum[key]
            if bucket and len(selected) < target:
                selected.append(bucket.pop())
            if bucket:
                next_keys.append(key)
        keys = next_keys
    return selected


def allocate_calibration_by_month(
    by_month: dict[str, list[dict[str, Any]]],
    calibration_size: int,
) -> dict[str, int]:
    """Allocate exact calibration counts across month buckets.

    The largest-remainder allocation keeps the 50/50 split exact globally while
    preserving each month's representation as closely as possible.
    """

    total = sum(len(bucket) for bucket in by_month.values())
    if calibration_size < 0 or calibration_size > total:
        raise ValueError(f"calibration_size must be between 0 and {total}")

    allocation: dict[str, int] = {}
    fractions: list[tuple[float, str]] = []
    for month, bucket in by_month.items():
        exact = calibration_size * (len(bucket) / total) if total else 0
        count = int(exact)
        allocation[month] = count
        fractions.append((exact - count, month))

    remaining = calibration_size - sum(allocation.values())
    for _, month in sorted(fractions, reverse=True):
        if remaining <= 0:
            break
        if allocation[month] < len(by_month[month]):
            allocation[month] += 1
            remaining -= 1
    return allocation


def assign_splits_and_fetch_order(
    selected: list[dict[str, Any]],
    *,
    seed: int,
    split_mode: str,
    calibration_size: int | None,
) -> list[dict[str, Any]]:
    """Assign deterministic evaluation splits and fetch order."""

    rows = [dict(row) for row in selected]
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[str(row["month_key"])].append(row)

    with_splits: list[dict[str, Any]] = []
    calibration_allocation: dict[str, int] = {}
    if split_mode == "calibration-holdout":
        calibration_allocation = allocate_calibration_by_month(
            by_month,
            calibration_size if calibration_size is not None else len(rows) // 2,
        )

    for month, bucket in sorted(by_month.items()):
        rng = random.Random(seed + int(month.replace("-", "")))
        rng.shuffle(bucket)
        if split_mode == "calibration-holdout":
            calibration_cut = calibration_allocation[month]
            for index, row in enumerate(bucket):
                row["split"] = "calibration" if index < calibration_cut else "holdout"
                with_splits.append(row)
            continue

        train_cut = int(len(bucket) * 0.60)
        dev_cut = train_cut + int(len(bucket) * 0.20)
        for index, row in enumerate(bucket):
            if index < train_cut:
                row["split"] = "train"
            elif index < dev_cut:
                row["split"] = "dev"
            else:
                row["split"] = "test"
            with_splits.append(row)

    fetch_rng = random.Random(seed + 1500)
    fetch_order = list(with_splits)
    fetch_rng.shuffle(fetch_order)
    order_by_id = {row["ttb_id"]: index + 1 for index, row in enumerate(fetch_order)}
    for row in with_splits:
        row["fetch_order"] = order_by_id[row["ttb_id"]]

    return sorted(with_splits, key=lambda row: int(row["fetch_order"]))


def select_sample(candidates: list[dict[str, Any]], *, args: argparse.Namespace, root: Path) -> list[dict[str, Any]]:
    """Select and persist the stratified sample."""

    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_month[str(row["month_key"])].append(row)

    floor = max(1, min(30, args.target // 24))
    allocation = allocate_months(candidates, args.target, floor=floor)
    selected: list[dict[str, Any]] = []
    for month in sorted(by_month):
        selected.extend(
            balanced_month_sample(
                by_month[month],
                allocation.get(month, 0),
                seed=args.seed + int(month.replace("-", "")),
            )
        )

    selected = assign_splits_and_fetch_order(
        selected,
        seed=args.seed,
        split_mode=args.split_mode,
        calibration_size=args.calibration_size,
    )
    write_csv(root / "sampling" / "selected_ttbs.csv", selected, SELECTED_FIELDS)
    selected_ids_text(root, selected, "selected-list-ttb-ids.txt")

    split_counts: dict[str, int] = defaultdict(int)
    month_counts: dict[str, int] = defaultdict(int)
    stratum_counts: dict[str, int] = defaultdict(int)
    for row in selected:
        split_counts[str(row["split"])] += 1
        month_counts[str(row["month_key"])] += 1
        stratum_counts[str(row["stratum"])] += 1

    summary = {
        "run_name": args.run_name,
        "target": args.target,
        "selected_total": len(selected),
        "candidate_total": len(candidates),
        "seed": args.seed,
        "date_range": {"start": args.start_date.isoformat(), "end": args.end_date.isoformat()},
        "sampling_design": (
            "Two-stage deterministic sample: random business-day clusters within month strata, "
            "then without-replacement secondary balancing by product type, import bucket, "
            "and single/multi-panel image complexity."
        ),
        "split_mode": args.split_mode,
        "calibration_size": args.calibration_size,
        "month_allocation": allocation,
        "selected_by_month": dict(sorted(month_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "secondary_strata_count": len(stratum_counts),
    }
    save_json(root / "sampling" / "summary.json", summary)
    return selected


def fetch_detail(
    client: httpx.Client,
    *,
    root: Path,
    ident: str,
    delay: float,
    resume: bool,
) -> dict[str, Any] | None:
    """Fetch or load one detail response."""

    path = root / "api" / "details" / f"{ident}.json"
    if resume and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return response_detail(payload)

    response = client.get(f"/colas/{ident}")
    response.raise_for_status()
    payload = response.json()
    save_json(path, payload)
    if delay:
        time.sleep(delay)
    return response_detail(payload)


def mirror_application(root: Path, ident: str) -> None:
    """Copy parsed application JSON into the segregated collection."""

    source = PARSED_APPLICATIONS_DIR / f"{ident}.json"
    if source.exists():
        shutil.copy2(source, root / "applications" / source.name)


def mirror_images(root: Path, ident: str) -> None:
    """Copy downloaded image files into the segregated collection."""

    source_dir = RAW_IMAGES_DIR / ident
    target_dir = root / "images" / ident
    if not source_dir.exists():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, target_dir / source.name)


def selected_ids_text(root: Path, records: list[dict[str, Any]], filename: str) -> None:
    """Write evaluator-friendly selected IDs."""

    text = "\n".join(str(row["ttb_id"]) for row in records) + ("\n" if records else "")
    (root / "api" / filename).write_text(text, encoding="utf-8")


def valid_existing_image_path(ident: str, panel_order: int) -> Path | None:
    """Return a readable existing image path for a panel, if one exists."""

    for path in sorted((RAW_IMAGES_DIR / ident).glob(f"{panel_order:02d}_*")):
        try:
            validate_image_bytes(path.read_bytes(), content_type="")
            return path
        except Exception:  # noqa: BLE001 - invalid legacy files should be redownloaded.
            continue
    return None


def fetch_details_and_images(
    client: httpx.Client,
    *,
    args: argparse.Namespace,
    root: Path,
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch details/images for the first N selected records."""

    if args.fetch_limit <= 0:
        return []

    target_rows = sorted(selected, key=lambda row: int(row["fetch_order"]))[: args.fetch_limit]
    details: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, row in enumerate(target_rows, start=1):
        ident = str(row["ttb_id"])
        print(f"[detail {index}/{len(target_rows)}] {ident}")
        try:
            detail = fetch_detail(client, root=root, ident=ident, delay=args.delay, resume=args.resume)
            if not detail:
                continue
            details.append(detail)
            import_records([detail], source_label=str(root), dry_run=False)
            mirror_application(root, ident)
        except Exception as exc:  # noqa: BLE001 - keep long data pulls resumable.
            failures.append({"ttb_id": ident, "stage": "detail", "error": str(exc)})
            print(f"  detail error: {exc}")

    selected_ids_text(root, details, "selected-detail-ttb-ids.txt")
    save_json(root / "api" / "selected-detail-records.json", details)

    if args.download_images:
        from cola_etl.database import connect, record_attachment_download

        image_count_total = 0
        with connect() as connection:
            for record_index, detail in enumerate(details, start=1):
                ident = ttb_id(detail)
                for image in images_for_record(detail):
                    idx = image_index(image)
                    print(f"[image {image_count_total + 1}] {ident} panel {idx + 1}")
                    try:
                        existing_path = valid_existing_image_path(ident, idx + 1)
                        if not args.force_images and existing_path is not None:
                            attachment_id = attachment_id_for_panel(
                                connection,
                                ident=ident,
                                panel_order=idx + 1,
                            )
                            if attachment_id is not None:
                                record_attachment_download(
                                    connection,
                                    attachment_id=attachment_id,
                                    raw_image_path=str(existing_path),
                                    http_status=200,
                                )
                            mirror_images(root, ident)
                            continue
                        store_image(
                            connection,
                            record=detail,
                            image=image,
                            png_bytes=download_image(client, image),
                        )
                        image_count_total += 1
                        mirror_images(root, ident)
                    except Exception as exc:  # noqa: BLE001 - keep image pulls resumable.
                        failures.append({"ttb_id": ident, "stage": "image", "error": str(exc)})
                        print(f"  image error: {exc}")
                    if args.image_delay:
                        time.sleep(args.image_delay)
                if record_index % 25 == 0:
                    connection.commit()
            connection.commit()

    save_json(root / "sampling" / "fetch_failures.json", failures)
    return details


def main() -> None:
    """Run the staged COLA Cloud sampling workflow."""

    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    root = collection_dir(args.run_name)
    exclusions = set() if args.include_existing_cola_work else existing_colawork_ids(root)
    if exclusions:
        (root / "sampling" / "excluded_existing_ttb_ids.txt").write_text(
            "\n".join(sorted(exclusions)) + "\n",
            encoding="utf-8",
        )

    with client_for_key(api_key(), timeout=args.timeout) as client:
        candidates = build_candidate_pool(client, args=args, root=root, exclusions=exclusions)
        selected = select_sample(candidates, args=args, root=root)
        print(f"Candidate pool: {len(candidates)}")
        print(f"Selected sample: {len(selected)}")

        if args.plan_only:
            print(f"Plan-only run complete: {root}")
            return

        details = fetch_details_and_images(client, args=args, root=root, selected=selected)
        print(f"Fetched detail records in this stage: {len(details)}")

    print(f"Collection: {root}")


if __name__ == "__main__":
    main()
