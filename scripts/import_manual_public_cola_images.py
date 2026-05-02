#!/usr/bin/env python
"""Import manually downloaded public COLA label images.

The automated TTB attachment endpoint can be brittle, while a browser may still
download the official label image successfully after opening the parent form.
This script bridges that gap: it validates browser-downloaded image files,
matches them to parsed public COLA attachment metadata, copies them into the
gitignored ETL workspace, and marks the corresponding SQLite row as downloaded.

No image files are committed by this command. They remain under
``data/work/public-cola/raw/images``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cola_etl.database import connect, record_attachment_download
from cola_etl.images import is_valid_image_path
from cola_etl.paths import RAW_IMAGES_DIR
from download_public_cola_images import safe_filename


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Downloaded image file or directory")
    parser.add_argument("--ttb-id", action="append", default=[], help="Limit matching to one or more TTB IDs")
    parser.add_argument("--recursive", action="store_true", help="Scan source directories recursively")
    parser.add_argument("--dry-run", action="store_true", help="Report matches without copying or updating SQLite")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional CSV with columns ttb_id,panel_order,path for explicit imports",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/work/public-cola/sampling/manual-image-import-report.csv"),
        help="CSV report path",
    )
    return parser.parse_args()


def normalized_filename(value: str) -> str:
    """Normalize a browser filename for attachment matching."""

    path = Path(value)
    stem = re.sub(r"\s+\(\d+\)$", "", path.stem)
    text = f"{stem}{path.suffix}".lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def candidate_files(source: Path, *, recursive: bool) -> list[Path]:
    """Return valid-looking image paths from a source path."""

    if source.is_file():
        return [source] if source.suffix.lower() in IMAGE_SUFFIXES else []
    globber = source.rglob("*") if recursive else source.glob("*")
    return sorted(path for path in globber if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def attachment_rows(connection, ttb_ids: list[str]) -> list:
    """Return candidate attachment rows from SQLite."""

    params: list[object] = []
    where_sql = ""
    if ttb_ids:
        placeholders = ",".join("?" for _ in ttb_ids)
        where_sql = f"WHERE ttb_id IN ({placeholders})"
        params.extend(ttb_ids)
    return connection.execute(
        f"""
        SELECT *
        FROM attachments
        {where_sql}
        ORDER BY ttb_id, panel_order
        """,
        params,
    ).fetchall()


def copy_attachment(path: Path, row) -> Path:
    """Copy one validated manual image into the public COLA raw image layout."""

    filename = safe_filename(row["filename"] or path.name, f"{row['ttb_id']}_{row['panel_order']:02d}{path.suffix}")
    output_path = RAW_IMAGES_DIR / row["ttb_id"] / f"{int(row['panel_order']):02d}_{filename}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, output_path)
    return output_path


def explicit_manifest_rows(path: Path) -> list[dict[str, str]]:
    """Read explicit import mappings from a CSV manifest."""

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def find_explicit_row(connection, *, ttb_id: str, panel_order: str):
    """Find one attachment row by TTB ID and panel order."""

    return connection.execute(
        """
        SELECT *
        FROM attachments
        WHERE ttb_id = ? AND panel_order = ?
        LIMIT 1
        """,
        (ttb_id, panel_order),
    ).fetchone()


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a CSV report for manual import results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "source_path",
        "ttb_id",
        "panel_order",
        "filename",
        "output_path",
        "reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def import_explicit_manifest(connection, args: argparse.Namespace) -> list[dict[str, object]]:
    """Import images using an explicit ttb_id/panel_order/path manifest."""

    report: list[dict[str, object]] = []
    for item in explicit_manifest_rows(args.manifest):
        source_path = Path(item.get("path", ""))
        row = find_explicit_row(
            connection,
            ttb_id=item.get("ttb_id", ""),
            panel_order=item.get("panel_order", ""),
        )
        if row is None:
            report.append(
                {
                    "status": "skipped",
                    "source_path": str(source_path),
                    "ttb_id": item.get("ttb_id", ""),
                    "panel_order": item.get("panel_order", ""),
                    "filename": "",
                    "output_path": "",
                    "reason": "no matching attachment row",
                }
            )
            continue
        report.extend(import_mapped_file(connection, source_path, row, args.dry_run))
    return report


def import_mapped_file(connection, path: Path, row, dry_run: bool) -> list[dict[str, object]]:
    """Validate and import one explicitly mapped image file."""

    if not path.exists() or not is_valid_image_path(path):
        return [
            {
                "status": "skipped",
                "source_path": str(path),
                "ttb_id": row["ttb_id"],
                "panel_order": row["panel_order"],
                "filename": row["filename"],
                "output_path": "",
                "reason": "not a readable image",
            }
        ]

    output_path = RAW_IMAGES_DIR / row["ttb_id"] / f"{int(row['panel_order']):02d}_{safe_filename(row['filename'] or path.name, path.name)}"
    if not dry_run:
        output_path = copy_attachment(path, row)
        record_attachment_download(
            connection,
            attachment_id=row["id"],
            raw_image_path=str(output_path),
            http_status=200,
        )
    return [
        {
            "status": "imported" if not dry_run else "would_import",
            "source_path": str(path),
            "ttb_id": row["ttb_id"],
            "panel_order": row["panel_order"],
            "filename": row["filename"],
            "output_path": str(output_path),
            "reason": "",
        }
    ]


def import_one_file(connection, path: Path, rows: list, dry_run: bool) -> list[dict[str, object]]:
    """Validate and import one downloaded image file."""

    if not path.exists() or not is_valid_image_path(path):
        return [
            {
                "status": "skipped",
                "source_path": str(path),
                "ttb_id": "",
                "panel_order": "",
                "filename": path.name,
                "output_path": "",
                "reason": "not a readable image",
            }
        ]

    key = normalized_filename(path.name)
    matches = [row for row in rows if normalized_filename(row["filename"] or "") == key]
    if not matches:
        return [
            {
                "status": "skipped",
                "source_path": str(path),
                "ttb_id": "",
                "panel_order": "",
                "filename": path.name,
                "output_path": "",
                "reason": "no attachment filename match",
            }
        ]
    if len(matches) > 1:
        return [
            {
                "status": "skipped",
                "source_path": str(path),
                "ttb_id": "",
                "panel_order": "",
                "filename": path.name,
                "output_path": "",
                "reason": f"ambiguous filename match: {len(matches)} rows; rerun with --ttb-id or manifest",
            }
        ]

    row = matches[0]
    output_path = RAW_IMAGES_DIR / row["ttb_id"] / f"{int(row['panel_order']):02d}_{safe_filename(row['filename'] or path.name, path.name)}"
    if not dry_run:
        output_path = copy_attachment(path, row)
        record_attachment_download(
            connection,
            attachment_id=row["id"],
            raw_image_path=str(output_path),
            http_status=200,
        )
    return [
        {
            "status": "imported" if not dry_run else "would_import",
            "source_path": str(path),
            "ttb_id": row["ttb_id"],
            "panel_order": row["panel_order"],
            "filename": row["filename"],
            "output_path": str(output_path),
            "reason": "",
        }
    ]


def main() -> None:
    """Run the manual image importer."""

    args = parse_args()
    with connect() as connection:
        if args.manifest:
            report = import_explicit_manifest(connection, args)
        else:
            rows = attachment_rows(connection, args.ttb_id)
            report = []
            for path in candidate_files(args.source, recursive=args.recursive):
                report.extend(import_one_file(connection, path, rows, args.dry_run))
        if not args.dry_run:
            connection.commit()

    write_report(args.report, report)
    imported = sum(1 for item in report if item["status"] in {"imported", "would_import"})
    skipped = len(report) - imported
    print(f"{'Would import' if args.dry_run else 'Imported'} {imported} image(s); skipped {skipped}.")
    print(f"Wrote report: {args.report}")
    if skipped:
        skipped_path = args.report.with_suffix(".skipped.json")
        skipped_path.write_text(
            json.dumps([item for item in report if item["status"] == "skipped"], indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote skipped details: {skipped_path}")


if __name__ == "__main__":
    main()
