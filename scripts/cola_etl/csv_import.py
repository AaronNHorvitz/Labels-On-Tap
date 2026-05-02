"""Import public COLA registry search-result CSV files."""

from __future__ import annotations

import csv
from pathlib import Path


HEADER_MAP = {
    "ttb id": "ttb_id",
    "permit no.": "permit_no",
    "permit no": "permit_no",
    "serial number": "serial_number",
    "completed date": "completed_date",
    "fanciful name": "fanciful_name",
    "brand name": "brand_name",
    "origin": "origin",
    "origin desc": "origin_desc",
    "class/type": "class_type",
    "class/type desc": "class_type_desc",
}


def normalize_header(value: str) -> str:
    """Normalize a registry CSV column name to an internal key."""

    cleaned = " ".join(value.replace("\ufeff", "").strip().lower().split())
    return HEADER_MAP.get(cleaned, cleaned.replace(" ", "_").replace("/", "_"))


def read_registry_csv(path: Path) -> list[dict[str, str]]:
    """Read a TTB registry search-results CSV into normalized dictionaries."""

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        fieldnames = [normalize_header(name) for name in reader.fieldnames]
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            normalized: dict[str, str] = {}
            for original, normalized_name in zip(reader.fieldnames, fieldnames, strict=True):
                normalized[normalized_name] = (raw_row.get(original) or "").strip()
            if normalized.get("ttb_id"):
                rows.append(normalized)
        return rows
