#!/usr/bin/env python3
"""Create a local upload-ready public COLA demo pack.

The generated pack is intentionally written under ``data/work`` so the raw
public application records and label images stay out of Git. It creates:

``manifest.csv``
    One row per COLA application.
``images/{ttb_id}/...``
    One folder per application containing its label panels.
``public-cola-demo-pack.zip``
    Optional ZIP containing the same images for the batch-upload form.

The manifest uses one application row with semicolon-separated panel filenames,
which matches the runtime batch upload contract.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import ROOT
from app.services.cola_cloud_demo import expected_fields


DEFAULT_SOURCE = ROOT / "data/work/cola/official-sample-3000-balanced"
DEFAULT_OUTPUT = ROOT / "data/work/demo-upload/public-cola-300"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the demo-pack exporter."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="COLA corpus root with applications/ and images/")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory under data/work")
    parser.add_argument("--limit", type=int, default=300, help="Maximum applications to export")
    parser.add_argument("--force", action="store_true", help="Replace an existing output directory")
    parser.add_argument("--zip", action="store_true", help="Create public-cola-demo-pack.zip")
    return parser.parse_args()


def main() -> None:
    """Build the upload pack from local COLA Cloud-derived public data."""

    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not (source / "applications").exists() or not (source / "images").exists():
        raise SystemExit(f"Missing source corpus directories: {source}")
    if output.exists() and args.force:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    images_output = output / "images"
    images_output.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for application_path in sorted((source / "applications").glob("*.json")):
        if len(rows) >= args.limit:
            break
        parsed = json.loads(application_path.read_text(encoding="utf-8"))
        ttb_id = str(parsed.get("ttb_id") or application_path.stem)
        image_paths = [
            path
            for path in sorted((source / "images" / ttb_id).glob("*"))
            if path.suffix.lower() in IMAGE_SUFFIXES
        ]
        if not image_paths:
            continue
        target_image_dir = images_output / ttb_id
        target_image_dir.mkdir(parents=True, exist_ok=True)
        panel_filenames = []
        for image_path in image_paths:
            target = target_image_dir / image_path.name
            shutil.copy2(image_path, target)
            panel_filenames.append(f"images/{ttb_id}/{image_path.name}")
        expected = expected_fields(parsed)
        application = parsed.get("application", {})
        rows.append(
            {
                "filename": ttb_id,
                "panel_filenames": ";".join(panel_filenames),
                "fixture_id": ttb_id,
                "product_type": str(application.get("product_type") or "malt_beverage"),
                "brand_name": expected["brand_name"],
                "fanciful_name": expected["fanciful_name"],
                "class_type": expected["class_type"],
                "alcohol_content": expected["alcohol_content"],
                "net_contents": expected["net_contents"],
                "bottler_producer_name_address": expected["applicant_or_producer"],
                "imported": "true" if expected["country_of_origin"] else "false",
                "country_of_origin": expected["country_of_origin"],
            }
        )

    fieldnames = [
        "filename",
        "panel_filenames",
        "fixture_id",
        "product_type",
        "brand_name",
        "fanciful_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "bottler_producer_name_address",
        "imported",
        "country_of_origin",
    ]
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    (output / "README.md").write_text(
        "\n".join(
            [
                "# Public COLA Demo Upload Pack",
                "",
                f"Applications: {len(rows)}",
                "",
                "Use `manifest.csv` as the application manifest.",
                "Upload `images/` as the application-folder image source, or upload `public-cola-demo-pack.zip` if generated.",
                "",
                "This directory is generated from gitignored public COLA working data and should not be committed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if args.zip:
        zip_path = output / "public-cola-demo-pack.zip"
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(images_output.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output).as_posix())

    print(f"Wrote {len(rows)} applications to {output}")
    print(f"Manifest: {output / 'manifest.csv'}")
    if args.zip:
        print(f"ZIP: {output / 'public-cola-demo-pack.zip'}")


if __name__ == "__main__":
    main()
