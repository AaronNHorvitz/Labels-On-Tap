#!/usr/bin/env python
"""Audit locally downloaded public COLA attachment files.

The command only inspects gitignored files under ``data/work/public-cola``. By
default it reports invalid files without changing metadata. With
``--mark-invalid`` it clears the corresponding SQLite attachment rows so the
downloader can retry them later.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cola_etl.database import connect, record_attachment_download
from cola_etl.images import is_valid_image_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Maximum attachment rows to inspect")
    parser.add_argument(
        "--mark-invalid",
        action="store_true",
        help="Clear invalid attachment paths in SQLite so they can be redownloaded",
    )
    return parser.parse_args()


def main() -> None:
    """Audit downloaded attachment paths recorded in SQLite."""

    args = parse_args()
    valid_count = 0
    invalid_count = 0
    missing_count = 0

    with connect() as connection:
        params: list[object] = []
        limit_sql = ""
        if args.limit:
            limit_sql = "LIMIT ?"
            params.append(args.limit)
        rows = connection.execute(
            f"""
            SELECT id, ttb_id, panel_order, raw_image_path
            FROM attachments
            WHERE raw_image_path IS NOT NULL AND raw_image_path != ''
            ORDER BY ttb_id, panel_order
            {limit_sql}
            """,
            params,
        ).fetchall()

        for row in rows:
            path = Path(row["raw_image_path"])
            if not path.exists():
                missing_count += 1
                invalid = True
                reason = "missing file"
            else:
                invalid = not is_valid_image_path(path)
                reason = "not a readable image" if invalid else ""

            if invalid:
                invalid_count += 1
                print(f"invalid {row['ttb_id']} panel {row['panel_order']}: {reason}: {path}")
                if args.mark_invalid:
                    record_attachment_download(
                        connection,
                        attachment_id=row["id"],
                        raw_image_path=None,
                        http_status=0,
                    )
            else:
                valid_count += 1

        connection.commit()

    print(
        "Summary: "
        f"{valid_count} valid, {invalid_count} invalid, {missing_count} missing"
    )
    if args.mark_invalid and invalid_count:
        print("Invalid attachment rows were marked pending for future redownload.")


if __name__ == "__main__":
    main()
