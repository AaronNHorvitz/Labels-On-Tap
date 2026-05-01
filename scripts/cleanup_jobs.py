#!/usr/bin/env python3
"""Delete old prototype job directories from ``data/jobs``.

Notes
-----
This is a conservative operational helper for the public prototype. It ignores
temporary upload directories and defaults to a dry-run friendly retention model.
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from app.config import JOBS_DIR


def cleanup_jobs(days: int, dry_run: bool) -> list[Path]:
    """Remove job directories older than a retention window.

    Parameters
    ----------
    days:
        Minimum job age in days before deletion.
    dry_run:
        When true, report matching paths without deleting them.

    Returns
    -------
    list[pathlib.Path]
        Job directories that were, or would be, removed.
    """

    cutoff = time.time() - (days * 24 * 60 * 60)
    removed: list[Path] = []
    if not JOBS_DIR.exists():
        return removed

    for path in sorted(JOBS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_upload-"):
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        removed.append(path)
        if not dry_run:
            shutil.rmtree(path)
    return removed


def main() -> None:
    """Parse CLI arguments and run cleanup."""

    parser = argparse.ArgumentParser(description="Clean old Labels On Tap prototype jobs.")
    parser.add_argument("--days", type=int, default=7, help="Delete jobs older than this many days.")
    parser.add_argument("--dry-run", action="store_true", help="Print matching job directories without deleting.")
    args = parser.parse_args()

    if args.days < 1:
        raise SystemExit("--days must be at least 1")

    removed = cleanup_jobs(days=args.days, dry_run=args.dry_run)
    action = "would remove" if args.dry_run else "removed"
    for path in removed:
        print(f"{action}: {path}")
    print(f"{action} {len(removed)} job director{'y' if len(removed) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
