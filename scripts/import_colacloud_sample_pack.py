#!/usr/bin/env python
"""Import the COLA Cloud sample pack as a local development corpus.

The sample pack is useful when the TTB Public COLA Registry is unavailable. It
contains public COLA metadata plus CloudFront-hosted label images. This importer
keeps the data under the same gitignored ``data/work/public-cola`` workspace so
the existing OCR evaluator can run without a new runtime dependency.

Important: COLA Cloud OCR fields are treated as third-party silver labels or
diagnostic references, not as proof of Labels On Tap OCR accuracy.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from io import BytesIO, TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import httpx
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
from cola_etl.paths import PARSED_APPLICATIONS_DIR, RAW_IMAGES_DIR, RAW_SEARCH_RESULTS_DIR
from download_public_cola_images import safe_filename


CLOUDFRONT_IMAGE_URL = "https://dyuie4zgfxmt6.cloudfront.net/{ttb_image_id}.webp"
PUBLIC_FORM_URL = "https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicFormDisplay&ttbid={ttb_id}"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_pack", type=Path, help="Path to cola-sample-pack-v1.zip")
    parser.add_argument("--limit", type=int, default=None, help="Maximum COLA applications to import")
    parser.add_argument("--image-limit", type=int, default=None, help="Maximum label images to download")
    parser.add_argument("--download-images", action="store_true", help="Download CloudFront label images")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between image downloads")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--force-images", action="store_true", help="Redownload existing converted images")
    return parser.parse_args()


def read_csv_from_zip(zip_file: ZipFile, name: str) -> list[dict[str, str]]:
    """Read a CSV member from the sample-pack zip."""

    with zip_file.open(name) as handle:
        reader = csv.DictReader(TextIOWrapper(handle, encoding="utf-8"))
        return list(reader)


def product_type_slug(value: str) -> str:
    """Normalize COLA Cloud product type text to the app's product slugs."""

    text = normalize_value(value).lower()
    if "malt" in text or "beer" in text:
        return "malt_beverage"
    if "spirit" in text or "distilled" in text:
        return "distilled_spirits"
    if "wine" in text:
        return "wine"
    return text.replace(" ", "_")


def imported_flag(value: str) -> bool:
    """Return True when a COLA Cloud domestic/import field indicates import."""

    return normalize_value(value).lower() == "imported"


def format_decimal(value: str) -> str:
    """Return compact decimal text for sample-pack numeric fields."""

    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return normalize_value(value)
    return str(int(number)) if number.is_integer() else str(number).rstrip("0").rstrip(".")


def format_abv(row: dict[str, str]) -> str:
    """Return an application-style alcohol-content statement from sample-pack ABV."""

    number = format_decimal(row.get("ABV", ""))
    return f"{number}% ALC/VOL" if number else ""


def format_net_contents(row: dict[str, str]) -> str:
    """Return an application-style net-contents statement from sample-pack volume fields."""

    volume = format_decimal(row.get("VOLUME", ""))
    if not volume:
        return ""
    unit = normalize_value(row.get("VOLUME_UNIT", "")).lower()
    unit_map = {
        "milliliter": "mL",
        "milliliters": "mL",
        "ml": "mL",
        "liter": "L",
        "liters": "L",
        "l": "L",
        "fluid ounce": "fl oz",
        "fluid ounces": "fl oz",
        "fl oz": "fl oz",
        "ounce": "oz",
        "ounces": "oz",
        "pint": "Pint",
        "pints": "Pints",
        "gallon": "gal",
        "gallons": "gal",
    }
    return f"{volume} {unit_map.get(unit, normalize_value(row.get('VOLUME_UNIT', '')))}".strip()


def cola_record_to_registry_row(row: dict[str, str]) -> dict[str, str]:
    """Map a COLA Cloud COLA row to the local registry row contract."""

    return {
        "ttb_id": row.get("TTB_ID", ""),
        "permit_no": row.get("PERMIT_NUMBER", ""),
        "serial_number": "",
        "completed_date": row.get("LATEST_UPDATE_DATE") or row.get("APPROVAL_DATE", ""),
        "fanciful_name": row.get("PRODUCT_NAME", ""),
        "brand_name": row.get("BRAND_NAME", ""),
        "origin": row.get("ORIGIN_ID", ""),
        "origin_desc": row.get("ORIGIN_NAME", ""),
        "class_type": row.get("CLASS_ID", ""),
        "class_type_desc": row.get("CLASS_NAME", ""),
    }


def parsed_application_payload(row: dict[str, str], images: list[dict[str, str]]) -> dict:
    """Build a parsed-application JSON payload compatible with the evaluator."""

    ttb_id = row.get("TTB_ID", "")
    imported = imported_flag(row.get("DOMESTIC_OR_IMPORTED", ""))
    alcohol_content = format_abv(row)
    net_contents = format_net_contents(row)
    application = {
        "fixture_id": ttb_id,
        "filename": f"{ttb_id}.json",
        "product_type": product_type_slug(row.get("PRODUCT_TYPE", "")),
        "brand_name": normalize_value(row.get("BRAND_NAME", "")),
        "fanciful_name": normalize_value(row.get("PRODUCT_NAME", "")),
        "class_type": normalize_value(row.get("CLASS_NAME", "")),
        "alcohol_content": alcohol_content,
        "net_contents": net_contents,
        "country_of_origin": normalize_value(row.get("ORIGIN_NAME", "")) if imported else None,
        "imported": imported,
        "formula_id": normalize_value(row.get("FORMULA_CODE", "")),
        "statement_of_composition": "",
    }
    form_fields = {
        "ttb_id": ttb_id,
        "representative_id": "",
        "plant_registry_basic_permit_brewers_number": normalize_value(row.get("PERMIT_NUMBER", "")),
        "source_of_product": normalize_value(row.get("DOMESTIC_OR_IMPORTED", "")),
        "serial_number": "",
        "type_of_product": normalize_value(row.get("PRODUCT_TYPE", "")),
        "brand_name": application["brand_name"],
        "fanciful_name": application["fanciful_name"],
        "applicant_name_address": normalize_value(row.get("PERMIT_NUMBER", "")),
        "formula_id": application["formula_id"],
        "net_contents": net_contents,
        "alcohol_content": alcohol_content,
        "type_of_application": normalize_value(row.get("APPLICATION_TYPE", "")),
        "date_of_application": normalize_value(row.get("APPLICATION_DATE", "")),
        "date_issued": normalize_value(row.get("APPROVAL_DATE", "")),
        "qualifications": normalize_value(row.get("APPROVAL_QUALIFICATIONS", "")),
        "status": normalize_value(row.get("APPLICATION_STATUS", "")),
        "class_type_description": application["class_type"],
    }
    attachments = [image_to_attachment(image) for image in images]
    return {
        "source_type": "cola_cloud_sample_pack",
        "source_url": PUBLIC_FORM_URL.format(ttb_id=ttb_id),
        "ttb_id": ttb_id,
        "form_fields": form_fields,
        "application": application,
        "attachments": attachments,
        "third_party_reference": {
            "provider": "COLA Cloud",
            "note": (
                "Provider OCR fields may be useful diagnostics but are not "
                "used as Labels On Tap ground truth."
            ),
        },
    }


def image_to_attachment(row: dict[str, str]) -> dict:
    """Map a COLA Cloud image row to local attachment metadata."""

    image_index = int(row.get("IMAGE_INDEX") or 0)
    ttb_image_id = row.get("TTB_IMAGE_ID", "")
    position = normalize_value(row.get("CONTAINER_POSITION", ""))
    return {
        "panel_order": image_index + 1,
        "filename": f"{ttb_image_id}.png",
        "source_url": CLOUDFRONT_IMAGE_URL.format(ttb_image_id=ttb_image_id),
        "image_type": position,
        "width_inches": float_or_none(row.get("WIDTH_INCHES", "")),
        "height_inches": float_or_none(row.get("HEIGHT_INCHES", "")),
        "alt_text": f"COLA Cloud label image: {position}".strip(),
    }


def float_or_none(value: str) -> float | None:
    """Convert numeric CSV text to float when possible."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_parsed_application(ttb_id: str, payload: dict) -> Path:
    """Write a parsed application JSON payload under the local work tree."""

    path = PARSED_APPLICATIONS_DIR / f"{ttb_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def copy_source_zip(path: Path) -> Path:
    """Copy the sample pack into the gitignored raw source folder."""

    target = RAW_SEARCH_RESULTS_DIR / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.resolve() != target.resolve():
        target.write_bytes(path.read_bytes())
    return target


def download_and_convert_image(client: httpx.Client, image_row: dict[str, str]) -> bytes:
    """Download a COLA Cloud WebP image and return PNG bytes."""

    url = CLOUDFRONT_IMAGE_URL.format(ttb_image_id=image_row["TTB_IMAGE_ID"])
    response = client.get(url)
    response.raise_for_status()
    validate_image_bytes(response.content, content_type=response.headers.get("content-type", ""))
    with Image.open(BytesIO(response.content)) as image:
        output = BytesIO()
        image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def attachment_id_for_panel(connection, *, ttb_id: str, panel_order: int) -> int | None:
    """Return the SQLite attachment row ID for one panel."""

    row = connection.execute(
        """
        SELECT id
        FROM attachments
        WHERE ttb_id = ? AND panel_order = ?
        LIMIT 1
        """,
        (ttb_id, panel_order),
    ).fetchone()
    return int(row["id"]) if row else None


def store_image(connection, *, image_row: dict[str, str], png_bytes: bytes) -> Path:
    """Store one downloaded image and mark the attachment row as downloaded."""

    ttb_id = image_row["TTB_ID"]
    panel_order = int(image_row.get("IMAGE_INDEX") or 0) + 1
    filename = safe_filename(f"{image_row['TTB_IMAGE_ID']}.png", f"{ttb_id}_{panel_order:02d}.png")
    output_path = RAW_IMAGES_DIR / ttb_id / f"{panel_order:02d}_{filename}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png_bytes)

    attachment_id = attachment_id_for_panel(connection, ttb_id=ttb_id, panel_order=panel_order)
    if attachment_id is not None:
        record_attachment_download(
            connection,
            attachment_id=attachment_id,
            raw_image_path=str(output_path),
            http_status=200,
        )
    return output_path


def main() -> None:
    """Import COLA Cloud sample-pack metadata and optional images."""

    args = parse_args()
    copied_zip = copy_source_zip(args.sample_pack)
    with ZipFile(args.sample_pack) as zip_file:
        colas = read_csv_from_zip(zip_file, "cola.csv")
        images = read_csv_from_zip(zip_file, "cola_image.csv")

    images_by_ttb_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for image in images:
        if normalize_value(image.get("IS_OPENABLE", "")).lower() == "false":
            continue
        images_by_ttb_id[image["TTB_ID"]].append(image)

    selected_colas = [row for row in colas if row.get("TTB_ID") in images_by_ttb_id]
    if args.limit:
        selected_colas = selected_colas[: args.limit]
    selected_ids = {row["TTB_ID"] for row in selected_colas}
    selected_images = [image for image in images if image["TTB_ID"] in selected_ids]
    if args.image_limit:
        selected_images = selected_images[: args.image_limit]

    downloaded = 0
    with connect() as connection:
        for row in selected_colas:
            ttb_id = row["TTB_ID"]
            upsert_registry_record(
                connection,
                cola_record_to_registry_row(row),
                source_csv=str(copied_zip),
            )
            payload = parsed_application_payload(row, images_by_ttb_id[ttb_id])
            parsed_path = write_parsed_application(ttb_id, payload)
            record_parsed_form(
                connection,
                ttb_id=ttb_id,
                parsed_json_path=str(parsed_path),
                parse_status="parsed",
            )
            replace_attachments(connection, ttb_id=ttb_id, attachments=payload["attachments"])

        if args.download_images:
            with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
                for index, image in enumerate(selected_images, start=1):
                    output_path = RAW_IMAGES_DIR / image["TTB_ID"] / (
                        f"{int(image.get('IMAGE_INDEX') or 0) + 1:02d}_{safe_filename(image['TTB_IMAGE_ID'] + '.png', image['TTB_IMAGE_ID'] + '.png')}"
                    )
                    if output_path.exists() and not args.force_images:
                        continue
                    print(f"[{index}/{len(selected_images)}] download {image['TTB_IMAGE_ID']}")
                    try:
                        png_bytes = download_and_convert_image(client, image)
                        store_image(connection, image_row=image, png_bytes=png_bytes)
                        downloaded += 1
                    except Exception as exc:  # noqa: BLE001 - local ETL should continue.
                        print(f"  error: {exc}")
                    if args.delay:
                        time.sleep(args.delay)

        connection.commit()

    print(
        "Imported "
        f"{len(selected_colas)} COLA record(s), "
        f"{sum(len(images_by_ttb_id[row['TTB_ID']]) for row in selected_colas)} image metadata row(s), "
        f"{downloaded} downloaded image(s)."
    )
    print(f"Source zip copied to {copied_zip}")


if __name__ == "__main__":
    main()
