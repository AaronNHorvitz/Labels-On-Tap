#!/usr/bin/env python
"""Pull a bounded COLA Cloud API corpus into the local OCR workspace.

This command is a development-data bridge, not a runtime integration. It reads
``COLACLOUD_API_KEY`` from the environment, saves raw API responses under
gitignored ``data/work/public-cola/raw/colacloud-api/``, imports application and
image metadata into the existing local SQLite/JSON workspace, and optionally
downloads/validates label images for local OCR evaluation.

Use list calls first. Detail calls count against COLA Cloud detail-view quota,
so only enable details once the list response shape has been inspected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cola_etl.csv_import import normalize_value
from cola_etl.database import (
    connect,
    record_attachment_download,
    record_parsed_form,
    replace_attachments,
    upsert_registry_record,
)
from cola_etl.images import validate_image_bytes
from cola_etl.paths import PARSED_APPLICATIONS_DIR, PUBLIC_COLA_WORK_DIR, RAW_IMAGES_DIR
from download_public_cola_images import safe_filename
from import_colacloud_sample_pack import PUBLIC_FORM_URL, float_or_none, product_type_slug


API_BASE_URL = "https://app.colacloud.us/api/v1"
RAW_API_DIR = PUBLIC_COLA_WORK_DIR / "raw" / "colacloud-api"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="latest", help="Raw response folder name")
    parser.add_argument("--limit", type=int, default=25, help="Maximum COLA records to import")
    parser.add_argument("--per-page", type=int, default=25, help="API list page size")
    parser.add_argument("--product-type", help="Optional product_type filter")
    parser.add_argument("--q", help="Optional full-text search query")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Additional list query parameter as key=value; may be repeated",
    )
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="Fetch /colas/{ttb_id}; spends detail-view quota",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=None,
        help="Maximum detail records to fetch when --include-details is set",
    )
    parser.add_argument("--download-images", action="store_true", help="Download label images for imported records")
    parser.add_argument("--image-limit", type=int, default=None, help="Maximum images to download")
    parser.add_argument(
        "--delay",
        type=float,
        default=6.5,
        help="Delay between API/image requests; default respects a 10 requests/minute burst limit",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--force-images", action="store_true", help="Redownload existing local images")
    parser.add_argument("--dry-run", action="store_true", help="Fetch/list only; do not write SQLite/imported files")
    return parser.parse_args()


def api_key() -> str:
    """Load the COLA Cloud API key from environment or .env."""

    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("COLACLOUD_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set COLACLOUD_API_KEY in .env or the shell before running this script.")
    return key


def parse_extra_params(values: list[str]) -> dict[str, str]:
    """Parse repeated key=value CLI parameters."""

    params: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--param must be key=value, got: {value}")
        key, raw = value.split("=", 1)
        params[key] = raw
    return params


def client_for_key(key: str, timeout: float) -> httpx.Client:
    """Create an authenticated COLA Cloud API client."""

    return httpx.Client(
        base_url=API_BASE_URL,
        headers={
            "X-API-Key": key,
            "Accept": "application/json",
            "User-Agent": "LabelsOnTapResearch/0.1 (+https://www.labelsontap.ai)",
        },
        timeout=timeout,
        follow_redirects=True,
    )


def raw_run_dir(run_name: str) -> Path:
    """Return/create the raw API response directory for a run."""

    path = RAW_API_DIR / run_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, payload: Any) -> None:
    """Write JSON payload to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def response_items(payload: Any) -> list[dict[str, Any]]:
    """Extract list items from common API response shapes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "results", "colas"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def response_detail(payload: Any) -> dict[str, Any]:
    """Extract one detail object from the documented detail response shape."""

    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def pagination_next(payload: Any, current_page: int) -> int | None:
    """Infer the next page number from common pagination response shapes."""

    if not isinstance(payload, dict):
        return None
    pagination = payload.get("pagination") or payload.get("meta") or {}
    if not isinstance(pagination, dict):
        return None
    if pagination.get("next_page"):
        return int(pagination["next_page"])
    total_pages = pagination.get("total_pages") or pagination.get("pages")
    if total_pages and current_page < int(total_pages):
        return current_page + 1
    has_more = pagination.get("has_more")
    if has_more is True:
        return current_page + 1
    return None


def field(record: dict[str, Any], *names: str) -> Any:
    """Read the first present field from snake, upper, or camel-ish names."""

    for name in names:
        variants = {
            name,
            name.upper(),
            name.lower(),
            "".join(part.title() if index else part for index, part in enumerate(name.split("_"))),
        }
        for variant in variants:
            if variant in record and record[variant] not in (None, ""):
                return record[variant]
    return ""


def ttb_id(record: dict[str, Any]) -> str:
    """Return the TTB ID from a COLA Cloud record."""

    return str(field(record, "ttb_id", "TTB_ID")).strip()


def list_colas(client: httpx.Client, args: argparse.Namespace, output_dir: Path) -> list[dict[str, Any]]:
    """Fetch list pages until the requested limit is reached."""

    collected: list[dict[str, Any]] = []
    page = 1
    params = parse_extra_params(args.param)
    if args.product_type:
        params["product_type"] = args.product_type
    if args.q:
        params["q"] = args.q

    while len(collected) < args.limit:
        page_params = {**params, "page": page, "per_page": min(args.per_page, args.limit - len(collected))}
        response = client.get("/colas", params=page_params)
        response.raise_for_status()
        payload = response.json()
        save_json(output_dir / f"list-page-{page:04d}.json", payload)
        items = response_items(payload)
        if not items:
            break
        collected.extend(items)
        next_page = pagination_next(payload, page)
        if next_page is None:
            break
        page = next_page
        if args.delay:
            time.sleep(args.delay)

    return collected[: args.limit]


def fetch_details(
    client: httpx.Client,
    records: list[dict[str, Any]],
    *,
    output_dir: Path,
    limit: int | None,
    delay: float,
) -> list[dict[str, Any]]:
    """Fetch detail payloads for selected records."""

    detailed: list[dict[str, Any]] = []
    for index, record in enumerate(records[:limit] if limit else records, start=1):
        ident = ttb_id(record)
        if not ident:
            continue
        response = client.get(f"/colas/{ident}")
        response.raise_for_status()
        payload = response.json()
        save_json(output_dir / "details" / f"{ident}.json", payload)
        detail = response_detail(payload)
        detailed.append(detail or record)
        print(f"[detail {index}] {ident}")
        if delay:
            time.sleep(delay)
    return detailed


def images_for_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return image metadata rows from a detail or list record."""

    images = field(record, "images", "cola_images")
    if isinstance(images, list):
        return [item for item in images if isinstance(item, dict)]
    main_image_id = field(record, "main_ttb_image_id", "ttb_image_id")
    main_url = field(record, "main_image_url", "image_url")
    if main_image_id or main_url:
        return [{"ttb_image_id": main_image_id, "image_url": main_url, "image_index": 0, "container_position": "main"}]
    return []


def registry_row(record: dict[str, Any]) -> dict[str, str]:
    """Map API record fields to the local registry row contract."""

    return {
        "ttb_id": ttb_id(record),
        "permit_no": normalize_value(field(record, "permit_number")),
        "serial_number": normalize_value(field(record, "serial_number")),
        "completed_date": normalize_value(field(record, "latest_update_date", "approval_date")),
        "fanciful_name": normalize_value(field(record, "product_name", "fanciful_name")),
        "brand_name": normalize_value(field(record, "brand_name")),
        "origin": normalize_value(field(record, "origin_id")),
        "origin_desc": normalize_value(field(record, "origin_name")),
        "class_type": normalize_value(field(record, "class_id")),
        "class_type_desc": normalize_value(field(record, "class_name")),
    }


def imported(record: dict[str, Any]) -> bool:
    """Return whether a record is imported."""

    domestic_or_imported = normalize_value(field(record, "domestic_or_imported")).lower()
    if domestic_or_imported:
        return domestic_or_imported == "imported"

    origin = normalize_value(field(record, "origin_name")).lower()
    domestic_origins = {"american", "united states", "usa", "u.s.", "us"}
    return bool(origin and origin not in domestic_origins)


def write_selected_ids(output_dir: Path, records: list[dict[str, Any]], filename: str) -> Path:
    """Write selected TTB IDs in evaluator-friendly text format."""

    ids = [ident for record in records if (ident := ttb_id(record))]
    path = output_dir / filename
    path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return path


def image_url(image: dict[str, Any]) -> str:
    """Return a downloadable image URL from an image object."""

    url = field(image, "image_url", "url", "webp_url")
    if url:
        return str(url)
    image_id = field(image, "ttb_image_id")
    if image_id:
        return f"https://dyuie4zgfxmt6.cloudfront.net/{image_id}.webp"
    return ""


def image_index(image: dict[str, Any]) -> int:
    """Return image index as an integer."""

    value = field(image, "image_index", "index")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def image_attachment(image: dict[str, Any]) -> dict[str, Any]:
    """Map API image metadata to local attachment metadata."""

    idx = image_index(image)
    image_id = normalize_value(field(image, "ttb_image_id")) or f"image_{idx}"
    position = normalize_value(field(image, "container_position", "position"))
    extension = normalize_value(field(image, "extension_type")) or "png"
    return {
        "panel_order": idx + 1,
        "filename": f"{image_id}.{extension}",
        "source_url": image_url(image),
        "image_type": position,
        "width_inches": float_or_none(field(image, "width_inches")),
        "height_inches": float_or_none(field(image, "height_inches")),
        "alt_text": f"COLA Cloud API label image: {position}".strip(),
    }


def parsed_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Build evaluator-compatible parsed application JSON from an API record."""

    ident = ttb_id(record)
    is_imported = imported(record)
    images = images_for_record(record)
    brand = normalize_value(field(record, "brand_name"))
    product_name = normalize_value(field(record, "product_name", "fanciful_name"))
    class_name = normalize_value(field(record, "class_name"))
    origin = normalize_value(field(record, "origin_name"))
    product_type = normalize_value(field(record, "product_type"))
    return {
        "source_type": "cola_cloud_api",
        "source_url": PUBLIC_FORM_URL.format(ttb_id=ident),
        "ttb_id": ident,
        "form_fields": {
            "ttb_id": ident,
            "plant_registry_basic_permit_brewers_number": normalize_value(field(record, "permit_number")),
            "source_of_product": normalize_value(field(record, "domestic_or_imported")),
            "serial_number": normalize_value(field(record, "serial_number")),
            "type_of_product": product_type,
            "brand_name": brand,
            "fanciful_name": product_name,
            "applicant_name_address": normalize_value(field(record, "address_text", "permit_number")),
            "formula_id": normalize_value(field(record, "formula_code")),
            "net_contents": "",
            "alcohol_content": "",
            "type_of_application": normalize_value(field(record, "application_type")),
            "date_of_application": normalize_value(field(record, "application_date")),
            "date_issued": normalize_value(field(record, "approval_date")),
            "qualifications": normalize_value(field(record, "approval_qualifications")),
            "status": normalize_value(field(record, "application_status")),
            "class_type_description": class_name,
        },
        "application": {
            "fixture_id": ident,
            "filename": f"{ident}.json",
            "product_type": product_type_slug(product_type),
            "brand_name": brand,
            "fanciful_name": product_name,
            "class_type": class_name,
            "alcohol_content": "",
            "net_contents": "",
            "country_of_origin": origin if is_imported else None,
            "imported": is_imported,
            "formula_id": normalize_value(field(record, "formula_code")),
            "statement_of_composition": "",
        },
        "attachments": [image_attachment(image) for image in images],
        "third_party_reference": {
            "provider": "COLA Cloud API",
            "note": "Provider OCR/enrichment fields are diagnostic references only.",
        },
    }


def write_parsed(record: dict[str, Any]) -> Path:
    """Write parsed API record to the local application JSON folder."""

    ident = ttb_id(record)
    path = PARSED_APPLICATIONS_DIR / f"{ident}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parsed_payload(record), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def attachment_id_for_panel(connection, *, ident: str, panel_order: int) -> int | None:
    """Return the SQLite attachment row ID for one panel."""

    row = connection.execute(
        "SELECT id FROM attachments WHERE ttb_id = ? AND panel_order = ? LIMIT 1",
        (ident, panel_order),
    ).fetchone()
    return int(row["id"]) if row else None


def download_image(client: httpx.Client, image: dict[str, Any]) -> bytes:
    """Download an image and return PNG bytes."""

    url = image_url(image)
    if not url:
        raise ValueError("image has no URL")
    response = client.get(url)
    response.raise_for_status()
    validate_image_bytes(response.content, content_type=response.headers.get("content-type", ""))
    with Image.open(BytesIO(response.content)) as img:
        output = BytesIO()
        img.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def store_image(connection, *, record: dict[str, Any], image: dict[str, Any], png_bytes: bytes) -> Path:
    """Store one downloaded API image and update SQLite."""

    ident = ttb_id(record)
    idx = image_index(image)
    image_id = normalize_value(field(image, "ttb_image_id")) or f"{ident}_{idx}"
    output_path = RAW_IMAGES_DIR / ident / f"{idx + 1:02d}_{safe_filename(image_id + '.png', image_id + '.png')}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png_bytes)

    attachment_id = attachment_id_for_panel(connection, ident=ident, panel_order=idx + 1)
    if attachment_id is not None:
        record_attachment_download(
            connection,
            attachment_id=attachment_id,
            raw_image_path=str(output_path),
            http_status=200,
        )
    return output_path


def import_records(records: list[dict[str, Any]], *, source_label: str, dry_run: bool) -> None:
    """Import API records into the local public-COLA workspace."""

    if dry_run:
        print(f"Dry run: would import {len(records)} record(s)")
        return

    with connect() as connection:
        for record in records:
            ident = ttb_id(record)
            if not ident:
                continue
            upsert_registry_record(connection, registry_row(record), source_csv=source_label)
            parsed_path = write_parsed(record)
            record_parsed_form(
                connection,
                ttb_id=ident,
                parsed_json_path=str(parsed_path),
                parse_status="parsed",
            )
            payload = parsed_payload(record)
            replace_attachments(connection, ttb_id=ident, attachments=payload["attachments"])
        connection.commit()


def download_images_for_records(
    client: httpx.Client,
    records: list[dict[str, Any]],
    *,
    image_limit: int | None,
    force: bool,
    delay: float,
) -> int:
    """Download images for imported records."""

    count = 0
    with connect() as connection:
        for record in records:
            ident = ttb_id(record)
            for image in images_for_record(record):
                if image_limit is not None and count >= image_limit:
                    connection.commit()
                    return count
                idx = image_index(image)
                image_id = normalize_value(field(image, "ttb_image_id")) or f"{ident}_{idx}"
                output_path = RAW_IMAGES_DIR / ident / f"{idx + 1:02d}_{safe_filename(image_id + '.png', image_id + '.png')}"
                if output_path.exists() and not force:
                    continue
                try:
                    print(f"[image {count + 1}] {ident} {image_id}")
                    store_image(connection, record=record, image=image, png_bytes=download_image(client, image))
                    count += 1
                except Exception as exc:  # noqa: BLE001 - data pull should keep going.
                    print(f"  error: {exc}")
                if delay:
                    time.sleep(delay)
        connection.commit()
    return count


def main() -> None:
    """Pull list/detail records and optional images from COLA Cloud."""

    args = parse_args()
    output_dir = raw_run_dir(args.run_name)
    with client_for_key(api_key(), timeout=args.timeout) as client:
        records = list_colas(client, args, output_dir)
        save_json(output_dir / "selected-list-records.json", records)
        write_selected_ids(output_dir, records, "selected-list-ttb-ids.txt")
        print(f"Fetched {len(records)} list record(s).")

        imported_records = records
        if args.include_details:
            imported_records = fetch_details(
                client,
                records,
                output_dir=output_dir,
                limit=args.detail_limit,
                delay=args.delay,
            )
            save_json(output_dir / "selected-detail-records.json", imported_records)
            write_selected_ids(output_dir, imported_records, "selected-detail-ttb-ids.txt")
            print(f"Fetched {len(imported_records)} detail record(s).")

        import_records(imported_records, source_label=str(output_dir), dry_run=args.dry_run)
        if args.download_images and not args.dry_run:
            downloaded = download_images_for_records(
                client,
                imported_records,
                image_limit=args.image_limit,
                force=args.force_images,
                delay=args.delay,
            )
            print(f"Downloaded {downloaded} image(s).")

    print(f"Raw API responses: {output_dir}")


if __name__ == "__main__":
    main()
