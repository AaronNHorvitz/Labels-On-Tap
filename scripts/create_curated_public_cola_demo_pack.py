#!/usr/bin/env python3
"""Create a curated public COLA demo pack with stable OCR sidecars.

The public walkthrough needs to show the happy path without waiting on live OCR
or exposing every OCR edge case. This exporter builds a gitignored demo pack
from already-downloaded public COLA records, copies valid label panels, and
writes OCR/typography JSON sidecars that the server-hosted demo route can use
for deterministic parsing.

Notes
-----
This script does not change model evaluation metrics. It creates a curated demo
artifact under ``data/work`` so the interview walkthrough can focus on the user
experience: application fields on the left, parsed label evidence on the right,
and reviewer actions around a clean pass.
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
from app.services.preflight.file_signature import has_allowed_image_signature, is_pillow_decodable_image
from app.services.rules.registry import CANONICAL_WARNING


DEFAULT_SOURCE = ROOT / "data/work/cola/official-sample-3000-balanced"
DEFAULT_PREVIOUS_PACK = ROOT / "data/work/demo-upload/public-cola-300/manifest.csv"
DEFAULT_OUTPUT = ROOT / "data/work/demo-upload/public-cola-curated-300"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the curated exporter."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="COLA corpus root with applications/ and images/")
    parser.add_argument("--previous-pack", type=Path, default=DEFAULT_PREVIOUS_PACK, help="Manifest to exclude from the new pack")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory under data/work")
    parser.add_argument("--limit", type=int, default=300, help="Applications to export")
    parser.add_argument("--max-panels", type=int, default=3, help="Maximum label panels per application")
    parser.add_argument("--force", action="store_true", help="Replace an existing output directory")
    parser.add_argument("--zip", action="store_true", help="Create public-cola-demo-pack.zip")
    return parser.parse_args()


def main() -> None:
    """Build the curated demo pack."""

    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not (source / "applications").exists() or not (source / "images").exists():
        raise SystemExit(f"Missing source corpus directories: {source}")
    if output.exists() and args.force:
        shutil.rmtree(output)

    excluded = load_excluded_ids(args.previous_pack)
    (output / "images").mkdir(parents=True, exist_ok=True)
    (output / "ocr").mkdir(parents=True, exist_ok=True)
    (output / "typography").mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    skipped_invalid_images: list[str] = []
    skipped_existing = 0
    skipped_incomplete = 0
    skipped_panel_count = 0
    skipped_malt = 0

    for application_path in sorted((source / "applications").glob("*.json")):
        if len(rows) >= args.limit:
            break
        parsed = json.loads(application_path.read_text(encoding="utf-8"))
        ttb_id = str(parsed.get("ttb_id") or application_path.stem)
        if ttb_id in excluded:
            skipped_existing += 1
            continue
        expected = expected_fields(parsed)
        if not required_fields_present(expected):
            skipped_incomplete += 1
            continue
        application = parsed.get("application", {})
        if str(application.get("product_type") or "").strip() == "malt_beverage":
            skipped_malt += 1
            continue
        image_paths = [
            path
            for path in sorted((source / "images" / ttb_id).glob("*"))
            if is_valid_demo_image(path, skipped_invalid_images)
        ]
        if not image_paths:
            skipped_incomplete += 1
            continue
        if len(image_paths) > args.max_panels:
            skipped_panel_count += 1
            continue

        target_image_dir = output / "images" / ttb_id
        target_ocr_dir = output / "ocr" / ttb_id
        target_image_dir.mkdir(parents=True, exist_ok=True)
        target_ocr_dir.mkdir(parents=True, exist_ok=True)

        panel_filenames = []
        for index, image_path in enumerate(image_paths, start=1):
            target = target_image_dir / image_path.name
            shutil.copy2(image_path, target)
            relative = f"images/{ttb_id}/{image_path.name}"
            panel_filenames.append(relative)
            ocr_payload = curated_ocr_payload(ttb_id, target.name, expected, include_full_text=index == len(image_paths))
            (target_ocr_dir / f"{Path(relative).stem}.json").write_text(
                json.dumps(ocr_payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        (output / "typography" / f"{ttb_id}.json").write_text(
            json.dumps(curated_typography_payload(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

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

    write_manifest(output / "manifest.csv", rows)
    write_readme(
        output,
        rows=rows,
        source=source,
        skipped_existing=skipped_existing,
        skipped_invalid_images=skipped_invalid_images,
        skipped_incomplete=skipped_incomplete,
        skipped_panel_count=skipped_panel_count,
        skipped_malt=skipped_malt,
    )
    if args.zip:
        write_zip(output)

    print(f"Wrote {len(rows)} curated applications to {output}")
    print(f"Skipped applications already in previous pack: {skipped_existing}")
    print(f"Skipped incomplete applications: {skipped_incomplete}")
    print(f"Skipped malt beverages: {skipped_malt}")
    print(f"Skipped applications with more than {args.max_panels} panels: {skipped_panel_count}")
    print(f"Skipped invalid image files: {len(skipped_invalid_images)}")
    if len(rows) < args.limit:
        raise SystemExit(f"Only found {len(rows)} applications for requested limit {args.limit}")


def load_excluded_ids(path: Path) -> set[str]:
    """Load TTB IDs to exclude from an older demo manifest."""

    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {row.get("filename", "").strip() for row in csv.DictReader(handle) if row.get("filename", "").strip()}


def required_fields_present(expected: dict[str, str]) -> bool:
    """Return whether an application has enough truth fields for the demo."""

    required = ["brand_name", "class_type", "alcohol_content", "net_contents"]
    return all(str(expected.get(field) or "").strip() for field in required)


def is_valid_demo_image(path: Path, skipped_invalid_images: list[str]) -> bool:
    """Return whether an image matches the deployed upload policy."""

    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return False
    if not has_allowed_image_signature(path) or not is_pillow_decodable_image(path):
        skipped_invalid_images.append(path.as_posix())
        return False
    return True


def curated_ocr_payload(ttb_id: str, filename: str, expected: dict[str, str], include_full_text: bool) -> dict[str, object]:
    """Return deterministic OCR text for one curated demo panel."""

    if include_full_text:
        lines = [
            expected["brand_name"],
            expected["fanciful_name"],
            expected["class_type"],
            expected["alcohol_content"],
            f"NET CONTENTS {expected['net_contents']}",
            expected["applicant_or_producer"],
            f"PRODUCT OF {expected['country_of_origin']}" if expected["country_of_origin"] else "",
            CANONICAL_WARNING,
        ]
    else:
        lines = [f"Additional approved label panel for {expected['brand_name']}"]
    text = "\n".join(line for line in lines if line).strip()
    blocks = [
        {"text": line, "confidence": 0.99, "bbox": [[0.08, 0.08 + index * 0.07], [0.9, 0.12 + index * 0.07]]}
        for index, line in enumerate(text.splitlines())
    ]
    return {
        "fixture_id": ttb_id,
        "filename": filename,
        "full_text": text,
        "avg_confidence": 0.99,
        "blocks": blocks,
        "source": "curated public COLA demo OCR cache",
        "ocr_ms": 0,
        "total_ms": 0,
    }


def curated_typography_payload() -> dict[str, object]:
    """Return deterministic pass evidence for the warning-heading demo cache."""

    return {
        "verdict": "pass",
        "probability": 0.999,
        "threshold": 0.9546,
        "crop_available": True,
        "model_name": "curated-demo-warning-heading-boldness",
        "model_version": "v1",
        "matched_text": "GOVERNMENT WARNING:",
        "match_score": 100.0,
        "ocr_confidence": 0.99,
        "crop_ms": 0.0,
        "classification_ms": 0.0,
        "message": "Curated demo typography cache cleared the bold warning heading.",
        "reviewer_action": None,
    }


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    """Write the curated application manifest."""

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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(
    output: Path,
    *,
    rows: list[dict[str, str]],
    source: Path,
    skipped_existing: int,
    skipped_invalid_images: list[str],
    skipped_incomplete: int,
    skipped_panel_count: int,
    skipped_malt: int,
) -> None:
    """Write a plain-language audit note beside the generated pack."""

    image_count = sum(len(row["panel_filenames"].split(";")) for row in rows)
    (output / "README.md").write_text(
        "\n".join(
            [
                "# Curated Public COLA Demo Pack",
                "",
                f"Applications: {len(rows)}",
                f"Images: {image_count}",
                f"Source corpus: {source}",
                "",
                "This pack is for the live interview walkthrough. It uses public COLA image panels",
                "plus curated OCR/typography sidecars so the demo can show a stable green-path",
                "field comparison without waiting on live OCR or exposing known vertical-text gaps.",
                "",
                f"Skipped previous demo applications: {skipped_existing}",
                f"Skipped incomplete applications: {skipped_incomplete}",
                f"Skipped malt beverages for green-path demo: {skipped_malt}",
                f"Skipped applications with too many panels: {skipped_panel_count}",
                f"Skipped invalid image files: {len(skipped_invalid_images)}",
                "",
                "Do not use this pack as an accuracy metric. Use the documented evaluation corpus",
                "and holdout metrics for model-performance claims.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_zip(output: Path) -> None:
    """Create a ZIP archive of the curated demo pack images."""

    zip_path = output / "public-cola-demo-pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted((output / "images").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output).as_posix())


if __name__ == "__main__":
    main()
