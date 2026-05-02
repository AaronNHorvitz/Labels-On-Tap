#!/usr/bin/env python
"""Export public COLA form and attachment links for manual browser download.

This script does not contact the TTB registry. It reads parsed public COLA
application JSON files from ``data/work/public-cola`` and writes a small CSV
manifest with the parent form URL and each label attachment URL. The manifest is
useful when the attachment endpoint works in a browser but automated HTTP
fetches are being reset or served HTML error pages.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse, urlunparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cola_etl.paths import PARSED_APPLICATIONS_DIR, PUBLIC_COLA_WORK_DIR


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", default=[], help="Specific TTB ID to export")
    parser.add_argument("--limit", type=int, default=None, help="Maximum parsed applications to export")
    parser.add_argument(
        "--output",
        type=Path,
        default=PUBLIC_COLA_WORK_DIR / "sampling" / "manual-attachment-links.csv",
        help="CSV output path",
    )
    return parser.parse_args()


def encoded_attachment_url(url: str) -> str:
    """Percent-encode the attachment filename query value for browser use."""

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    filename = params.get("filename", [""])[0]
    filetype = params.get("filetype", ["l"])[0]
    if not filename:
        return url
    query = f"filename={quote(filename)}&filetype={quote(filetype)}"
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def selected_paths(ttb_ids: list[str], limit: int | None) -> list[Path]:
    """Return parsed application paths for the requested export."""

    if ttb_ids:
        paths = [PARSED_APPLICATIONS_DIR / f"{ttb_id}.json" for ttb_id in ttb_ids]
        return [path for path in paths if path.exists()]
    paths = sorted(PARSED_APPLICATIONS_DIR.glob("*.json"))
    return paths[:limit] if limit else paths


def rows_for_path(path: Path) -> list[dict[str, object]]:
    """Build CSV rows for one parsed public COLA application."""

    parsed = json.loads(path.read_text(encoding="utf-8"))
    ttb_id = parsed.get("ttb_id") or parsed.get("application", {}).get("fixture_id") or path.stem
    form_url = parsed.get("source_url") or (
        "https://ttbonline.gov/colasonline/viewColaDetails.do"
        f"?action=publicFormDisplay&ttbid={ttb_id}"
    )
    rows = []
    for attachment in parsed.get("attachments", []):
        rows.append(
            {
                "ttb_id": ttb_id,
                "form_url": form_url,
                "panel_order": attachment.get("panel_order"),
                "image_type": attachment.get("image_type"),
                "filename": attachment.get("filename"),
                "attachment_url": encoded_attachment_url(attachment.get("source_url", "")),
            }
        )
    return rows


def main() -> None:
    """Write the manual-download attachment manifest."""

    args = parse_args()
    all_rows: list[dict[str, object]] = []
    for path in selected_paths(args.ttb_id, args.limit):
        all_rows.extend(rows_for_path(path))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ttb_id", "form_url", "panel_order", "image_type", "filename", "attachment_url"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} attachment link(s) to {args.output}")


if __name__ == "__main__":
    main()
