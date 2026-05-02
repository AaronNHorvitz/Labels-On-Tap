#!/usr/bin/env python
"""Download label images referenced by parsed public COLA forms."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from cola_etl.csv_import import normalize_value
from cola_etl.database import connect, pending_attachments, record_attachment_download
from cola_etl.http import make_client, polite_sleep
from cola_etl.images import InvalidImageDownload, validate_image_bytes
from cola_etl.paths import RAW_IMAGES_DIR, ensure_public_cola_work_dirs


PUBLIC_FORM_URL = "https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicFormDisplay&ttbid={ttb_id}"


def safe_filename(value: str, fallback: str) -> str:
    """Return a filesystem-safe filename for a public label image."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned or fallback


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", default=[], help="TTB ID to download")
    parser.add_argument("--ttb-id-file", help="File containing one TTB ID per line")
    parser.add_argument("--limit", type=int, default=None, help="Maximum images to download")
    parser.add_argument("--force", action="store_true", help="Redownload existing images")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests")
    parser.add_argument("--jitter", type=float, default=0.75, help="Random extra delay seconds")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry transient attachment download failures before marking the panel failed",
    )
    parser.add_argument(
        "--time-budget-seconds",
        type=float,
        default=None,
        help="Stop cleanly once this many seconds have elapsed in the current run",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for public TTB registry fetches when local CA validation fails",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Alias for the default skip-existing behavior; useful for orchestration scripts",
    )
    return parser.parse_args()


def read_ttb_ids_from_file(path: str | None) -> list[str]:
    """Read one TTB ID per line from a text file."""

    if not path:
        return []
    return [
        normalize_value(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def download_attachment_with_retries(
    client,
    source_url: str,
    *,
    retries: int,
    delay: float,
    jitter: float,
):
    """Download one attachment response with bounded retry attempts."""

    for attempt in range(1, retries + 2):
        try:
            response = client.get(source_url)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - ETL should continue.
            if attempt > retries:
                raise
            print(f"  transient image error on attempt {attempt}; retrying: {exc}")
            polite_sleep(delay, jitter)


def warm_attachment_session(client, ttb_id: str) -> None:
    """Load the public form page before attachment requests for that TTB ID.

    Notes
    -----
    The public attachment endpoint appears to be stateful in some cases: direct
    image URL fetches can return an HTML "Unable to render attachment" page.
    Loading the printable public form first mirrors how a browser reaches the
    image URLs and gives the server a chance to establish any required session
    context.
    """

    response = client.get(PUBLIC_FORM_URL.format(ttb_id=ttb_id))
    response.raise_for_status()


def main() -> None:
    """Download parsed public label image attachments."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    deadline = (
        time.monotonic() + args.time_budget_seconds
        if args.time_budget_seconds is not None
        else None
    )
    with connect() as connection:
        rows = pending_attachments(
            connection,
            explicit_ids=args.ttb_id + read_ttb_ids_from_file(args.ttb_id_file),
            missing_only=not args.force,
            limit=args.limit,
        )
        if not rows:
            print("No pending attachments. Parse forms first, or use --force.")
            return

        with make_client(timeout=args.timeout, verify=not args.insecure) as client:
            warmed_ttb_id = ""
            for index, row in enumerate(rows, start=1):
                if deadline is not None and time.monotonic() >= deadline:
                    print("Time budget reached before next image download.")
                    break
                ttb_id = row["ttb_id"]
                filename = safe_filename(
                    row["filename"] or "",
                    f"{ttb_id}_{row['panel_order']:02d}.jpg",
                )
                output_path = RAW_IMAGES_DIR / ttb_id / f"{row['panel_order']:02d}_{filename}"
                print(f"[{index}/{len(rows)}] download {ttb_id} panel {row['panel_order']}")
                try:
                    if ttb_id != warmed_ttb_id:
                        warm_attachment_session(client, ttb_id)
                        warmed_ttb_id = ttb_id
                        polite_sleep(args.delay, args.jitter)
                    response = download_attachment_with_retries(
                        client,
                        row["source_url"],
                        retries=args.retries,
                        delay=args.delay,
                        jitter=args.jitter,
                    )
                    image_bytes = validate_image_bytes(
                        response.content,
                        content_type=response.headers.get("content-type", ""),
                    )
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(image_bytes)
                    record_attachment_download(
                        connection,
                        attachment_id=row["id"],
                        raw_image_path=str(output_path),
                        http_status=response.status_code,
                    )
                except InvalidImageDownload as exc:
                    record_attachment_download(
                        connection,
                        attachment_id=row["id"],
                        raw_image_path=None,
                        http_status=0,
                    )
                    print(f"  invalid image response: {exc}")
                except Exception as exc:  # noqa: BLE001 - ETL should continue.
                    record_attachment_download(
                        connection,
                        attachment_id=row["id"],
                        raw_image_path=None,
                        http_status=getattr(getattr(exc, "response", None), "status_code", None) or 0,
                    )
                    print(f"  error: {exc}")
                connection.commit()
                if index < len(rows):
                    polite_sleep(args.delay, args.jitter)


if __name__ == "__main__":
    main()
