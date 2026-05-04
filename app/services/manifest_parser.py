"""CSV/JSON batch manifest parsing.

Notes
-----
The parser keeps upload validation deterministic and local. It accepts only the
small manifest contract used by the UI and fixtures, then turns rows into
``ManifestItem`` objects for the batch route.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.manifest import ManifestItem


class ManifestParseError(ValueError):
    """Raised when a user-supplied batch manifest cannot be parsed safely."""


REQUIRED_FIELDS = {"filename", "product_type", "brand_name"}


def parse_manifest(filename: str, content: bytes) -> list[ManifestItem]:
    """Parse a user-supplied CSV or JSON manifest.

    Parameters
    ----------
    filename:
        Original manifest filename, used only to choose CSV vs JSON by suffix.
    content:
        Uploaded manifest bytes after size-limit enforcement.

    Returns
    -------
    list[ManifestItem]
        Validated manifest items.

    Raises
    ------
    ManifestParseError
        Raised when the suffix, encoding, schema, or row contents are invalid.
    """

    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return _parse_csv_manifest(content)
    if suffix == ".json":
        return _parse_json_manifest(content)
    raise ManifestParseError("Manifest must be a CSV or JSON file.")


def _parse_csv_manifest(content: bytes) -> list[ManifestItem]:
    """Parse UTF-8 CSV manifest bytes into manifest items."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ManifestParseError("Manifest CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ManifestParseError("Manifest CSV is missing a header row.")
    missing = REQUIRED_FIELDS - set(reader.fieldnames)
    if missing:
        raise ManifestParseError(f"Manifest CSV is missing required columns: {', '.join(sorted(missing))}.")

    items = []
    for row_number, row in enumerate(reader, start=2):
        payload = {key: (value or "").strip() for key, value in row.items() if key}
        items.append(_manifest_item_from_payload(payload, row_number=row_number))
    return _validate_manifest_items(items)


def _parse_json_manifest(content: bytes) -> list[ManifestItem]:
    """Parse JSON manifest bytes into manifest items."""

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestParseError("Manifest JSON is not valid UTF-8 JSON.") from exc

    raw_items: Any
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        raw_items = payload["items"]
    else:
        raise ManifestParseError("Manifest JSON must be a list or an object with an items list.")

    items = []
    for row_number, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ManifestParseError(f"Manifest JSON item {row_number} must be an object.")
        items.append(_manifest_item_from_payload(item, row_number=row_number))
    return _validate_manifest_items(items)


def _manifest_item_from_payload(payload: dict[str, Any], row_number: int) -> ManifestItem:
    """Normalize and validate one manifest row/object.

    Parameters
    ----------
    payload:
        Raw CSV row or JSON item.
    row_number:
        Human-readable row/item number used in error messages.
    """

    for field in REQUIRED_FIELDS:
        if not str(payload.get(field, "")).strip():
            raise ManifestParseError(f"Manifest row {row_number} is missing required field: {field}.")

    normalized = dict(payload)
    normalized["panel_filenames"] = _parse_panel_filenames(normalized.get("panel_filenames", ""))
    normalized["imported"] = _parse_bool(normalized.get("imported", False), row_number)
    if not normalized.get("country_of_origin"):
        normalized["country_of_origin"] = None

    try:
        return ManifestItem(**normalized)
    except ValidationError as exc:
        raise ManifestParseError(f"Manifest row {row_number} is invalid: {exc}") from exc


def _parse_panel_filenames(value: Any) -> list[str]:
    """Parse optional multi-panel image filenames from a manifest cell.

    Parameters
    ----------
    value:
        CSV or JSON value. CSV users can separate panel filenames with
        semicolons or pipes; JSON users may provide either a string or a list.

    Returns
    -------
    list[str]
        Ordered panel filenames for one application row.
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    separator = "|" if "|" in text else ";"
    return [part.strip() for part in text.split(separator) if part.strip()]


def _parse_bool(value: Any, row_number: int) -> bool:
    """Parse user-friendly truthy/falsy values from a manifest field."""

    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    if normalized in {"1", "true", "yes", "y"}:
        return True
    raise ManifestParseError(f"Manifest row {row_number} has invalid imported value: {value}.")


def _validate_manifest_items(items: list[ManifestItem]) -> list[ManifestItem]:
    """Validate manifest-level invariants.

    Notes
    -----
    Duplicate filenames are rejected because they make file-to-row matching
    ambiguous. Duplicate fixture IDs are also rejected because result filenames
    are keyed by item ID in the filesystem store.
    """

    if not items:
        raise ManifestParseError("Manifest must contain at least one item.")

    application_filenames = [item.filename for item in items]
    duplicate_application_filenames = sorted(
        {name for name in application_filenames if application_filenames.count(name) > 1}
    )
    if duplicate_application_filenames:
        raise ManifestParseError(f"Manifest has duplicate filenames: {', '.join(duplicate_application_filenames)}.")

    filenames: list[str] = []
    for item in items:
        filenames.extend(item.panel_filenames or [item.filename])
    duplicate_filenames = sorted({name for name in filenames if filenames.count(name) > 1})
    if duplicate_filenames:
        raise ManifestParseError(f"Manifest has duplicate filenames: {', '.join(duplicate_filenames)}.")

    fixture_ids = [item.fixture_id for item in items if item.fixture_id]
    duplicate_fixture_ids = sorted({fixture_id for fixture_id in fixture_ids if fixture_ids.count(fixture_id) > 1})
    if duplicate_fixture_ids:
        raise ManifestParseError(f"Manifest has duplicate fixture IDs: {', '.join(duplicate_fixture_ids)}.")

    return items
