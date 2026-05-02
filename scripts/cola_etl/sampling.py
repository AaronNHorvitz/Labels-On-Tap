"""Deterministic stratified sampling helpers for public COLA data."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from cola_etl.csv_import import normalize_value
except ModuleNotFoundError:  # pragma: no cover - exercised by package-style test imports.
    from scripts.cola_etl.csv_import import normalize_value


US_DOMESTIC_ORIGINS = {
    "ALABAMA",
    "ALASKA",
    "ARIZONA",
    "ARKANSAS",
    "CALIFORNIA",
    "COLORADO",
    "CONNECTICUT",
    "DELAWARE",
    "DISTRICT OF COLUMBIA",
    "FLORIDA",
    "GEORGIA",
    "HAWAII",
    "IDAHO",
    "ILLINOIS",
    "INDIANA",
    "IOWA",
    "KANSAS",
    "KENTUCKY",
    "LOUISIANA",
    "MAINE",
    "MARYLAND",
    "MASSACHUSETTS",
    "MICHIGAN",
    "MINNESOTA",
    "MISSISSIPPI",
    "MISSOURI",
    "MONTANA",
    "NEBRASKA",
    "NEVADA",
    "NEW HAMPSHIRE",
    "NEW JERSEY",
    "NEW MEXICO",
    "NEW YORK",
    "NORTH CAROLINA",
    "NORTH DAKOTA",
    "OHIO",
    "OKLAHOMA",
    "OREGON",
    "PENNSYLVANIA",
    "PUERTO RICO",
    "RHODE ISLAND",
    "SOUTH CAROLINA",
    "SOUTH DAKOTA",
    "TENNESSEE",
    "TEXAS",
    "UTAH",
    "VERMONT",
    "VIRGINIA",
    "WASHINGTON",
    "WEST VIRGINIA",
    "WISCONSIN",
    "WYOMING",
}


@dataclass(frozen=True)
class SampleDay:
    """One deterministic sample day in the overnight plan."""

    month_key: str
    search_date: date
    selection_rank: int
    role: str


def parse_registry_date(value: str) -> date:
    """Parse a public registry MM/DD/YYYY date."""

    return datetime.strptime(value, "%m/%d/%Y").date()


def month_start(value: date) -> date:
    """Return the first day of the month containing ``value``."""

    return value.replace(day=1)


def add_month(value: date) -> date:
    """Return the first day of the next month."""

    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value.replace(month=value.month + 1, day=1)


def month_key(value: date) -> str:
    """Return a stable YYYY-MM month key."""

    return value.strftime("%Y-%m")


def business_days_in_range(start_date: date, end_date: date) -> list[date]:
    """Return weekday dates between start and end, inclusive."""

    days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def month_business_days(start_date: date, end_date: date) -> dict[str, list[date]]:
    """Return business days bucketed by month within the requested frame."""

    buckets: dict[str, list[date]] = {}
    current = month_start(start_date)
    while current <= end_date:
        month_end = add_month(current) - timedelta(days=1)
        window_start = max(start_date, current)
        window_end = min(end_date, month_end)
        if window_start <= window_end:
            days = business_days_in_range(window_start, window_end)
            if days:
                buckets[month_key(current)] = days
        current = add_month(current)
    return buckets


def choose_sample_days(
    start_date: date,
    end_date: date,
    *,
    seed: int,
    days_per_month: int = 3,
) -> list[SampleDay]:
    """Choose deterministic sample days per month.

    The first two days are treated as primary sample days. The third, when
    available, is a backup/reserve day that can be fetched as well without
    changing the deterministic plan.
    """

    plan: list[SampleDay] = []
    buckets = month_business_days(start_date, end_date)
    for month, days in sorted(buckets.items()):
        month_seed = seed + int(month.replace("-", ""))
        rng = random.Random(month_seed)
        pool = list(days)
        rng.shuffle(pool)
        chosen = sorted(pool[: min(days_per_month, len(pool))])
        for index, chosen_day in enumerate(chosen, start=1):
            role = "primary" if index <= 2 else "backup"
            plan.append(
                SampleDay(
                    month_key=month,
                    search_date=chosen_day,
                    selection_rank=index,
                    role=role,
                )
            )
    return plan


def write_sample_days_csv(path: Path, days: list[SampleDay]) -> None:
    """Write the selected search days to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["month_key", "search_date", "selection_rank", "role"],
        )
        writer.writeheader()
        for item in days:
            writer.writerow(
                {
                    "month_key": item.month_key,
                    "search_date": item.search_date.isoformat(),
                    "selection_rank": item.selection_rank,
                    "role": item.role,
                }
            )


def read_sample_days_csv(path: Path) -> list[SampleDay]:
    """Read a saved selected-days CSV."""

    days: list[SampleDay] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            days.append(
                SampleDay(
                    month_key=row["month_key"],
                    search_date=date.fromisoformat(row["search_date"]),
                    selection_rank=int(row["selection_rank"]),
                    role=row["role"],
                )
            )
    return days


def read_excluded_ttb_ids(path: str | None) -> set[str]:
    """Read TTB IDs that must not appear in the selected sample.

    The helper accepts either a plain newline-delimited text file or a CSV file
    with a ``ttb_id`` column. This keeps follow-on sampling runs reproducible
    without requiring callers to hand-edit intermediate manifests.
    """

    if not path:
        return set()

    exclusion_path = Path(path)
    if not exclusion_path.exists():
        raise FileNotFoundError(f"Exclusion file not found: {exclusion_path}")

    if exclusion_path.suffix.lower() == ".csv":
        with exclusion_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames and "ttb_id" in reader.fieldnames:
                return {
                    normalize_value(row["ttb_id"])
                    for row in reader
                    if normalize_value(row.get("ttb_id"))
                }

    return {
        normalize_value(line)
        for line in exclusion_path.read_text(encoding="utf-8").splitlines()
        if normalize_value(line)
    }


def product_family(class_type_desc: str) -> str:
    """Map class/type text into a broad product family."""

    text = class_type_desc.upper()
    wine_terms = ("WINE", "CHAMPAGNE", "CIDER", "MEAD", "SANGRIA", "SAKE")
    spirits_terms = (
        "WHISK",
        "VODKA",
        "GIN",
        "RUM",
        "TEQUILA",
        "MEZCAL",
        "LIQUEUR",
        "BRANDY",
        "COGNAC",
        "CORDIAL",
        "SPIRIT",
        "BOURBON",
        "SCOTCH",
    )
    malt_terms = ("ALE", "LAGER", "MALT", "BEER", "STOUT", "PORTER", "PILSNER")
    if any(term in text for term in wine_terms):
        return "wine"
    if any(term in text for term in spirits_terms):
        return "distilled_spirits"
    if any(term in text for term in malt_terms):
        return "malt_beverage"
    return "other"


def source_bucket(permit_no: str, origin_desc: str) -> str:
    """Derive an imported/domestic bucket from search-result metadata."""

    permit_upper = permit_no.upper()
    origin_upper = origin_desc.upper().strip()
    if "-I-" in permit_upper:
        return "imported"
    if origin_upper and origin_upper not in US_DOMESTIC_ORIGINS:
        return "imported"
    return "domestic"


def allocate_targets(
    monthly_counts: dict[str, int],
    target_total: int,
    *,
    base_floor: int = 8,
) -> dict[str, int]:
    """Allocate a target sample count across months with a coverage floor."""

    months = sorted(monthly_counts)
    if not months:
        return {}

    allocation = {month: min(count, base_floor) for month, count in monthly_counts.items()}
    remaining = max(0, target_total - sum(allocation.values()))
    capacities = {month: max(0, monthly_counts[month] - allocation[month]) for month in months}
    capacity_total = sum(capacities.values())
    if remaining == 0 or capacity_total == 0:
        return allocation

    provisional: dict[str, float] = {}
    for month in months:
        if capacities[month] == 0:
            provisional[month] = 0.0
        else:
            provisional[month] = remaining * (capacities[month] / capacity_total)

    extras = {month: min(capacities[month], math.floor(provisional[month])) for month in months}
    distributed = sum(extras.values())
    leftovers = remaining - distributed
    if leftovers > 0:
        ranked = sorted(
            months,
            key=lambda month: (provisional[month] - extras[month], capacities[month], month),
            reverse=True,
        )
        for month in ranked:
            if leftovers == 0:
                break
            if extras[month] < capacities[month]:
                extras[month] += 1
                leftovers -= 1

    for month in months:
        allocation[month] += extras[month]
    return allocation


def round_robin_sample(
    rows: list[dict[str, str]],
    target_count: int,
    *,
    seed: int,
) -> list[dict[str, str]]:
    """Sample rows from available strata in a deterministic round-robin."""

    strata: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row["product_family"], row["source_bucket"])
        strata[key].append(row)

    ordered_keys = sorted(strata)
    rng = random.Random(seed)
    for key in ordered_keys:
        rng.shuffle(strata[key])
    rng.shuffle(ordered_keys)

    selected: list[dict[str, str]] = []
    while len(selected) < target_count and ordered_keys:
        next_keys: list[tuple[str, str]] = []
        for key in ordered_keys:
            bucket = strata[key]
            if bucket:
                selected.append(bucket.pop())
                if len(selected) >= target_count:
                    break
            if bucket:
                next_keys.append(key)
        ordered_keys = next_keys
    return selected


def assign_splits(
    rows: list[dict[str, str]],
    *,
    seed: int,
    train_ratio: float = 0.6,
    dev_ratio: float = 0.2,
) -> list[dict[str, str]]:
    """Assign deterministic train/dev/test splits within each month bucket."""

    by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_month[row["month_key"]].append(dict(row))

    assigned: list[dict[str, str]] = []
    for month in sorted(by_month):
        bucket = by_month[month]
        rng = random.Random(seed + int(month.replace("-", "")))
        rng.shuffle(bucket)
        train_cut = int(len(bucket) * train_ratio)
        dev_cut = train_cut + int(len(bucket) * dev_ratio)
        for index, row in enumerate(bucket):
            if index < train_cut:
                split = "train"
            elif index < dev_cut:
                split = "dev"
            else:
                split = "test"
            row["split"] = split
            assigned.append(row)
    return assigned


def write_rows_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Write dictionaries to CSV with stable field order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_json(path: Path, payload: dict) -> None:
    """Write a JSON payload with indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
