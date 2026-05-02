#!/usr/bin/env python
"""Run the overnight public COLA sampling workflow end to end."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sqlite3
import subprocess
import time
from pathlib import Path

from cola_etl.csv_import import normalize_value
from cola_etl.paths import PUBLIC_COLA_DB_PATH, SAMPLING_DIR, ensure_public_cola_work_dirs


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2025-05-01")
    parser.add_argument("--end-date", default="2026-05-01")
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--days-per-month", type=int, default=3)
    parser.add_argument("--target-total", type=int, default=300)
    parser.add_argument("--hard-cap", type=int, default=500)
    parser.add_argument("--time-budget-hours", type=float, default=7.0)
    parser.add_argument("--search-delay", type=float, default=3.0)
    parser.add_argument("--search-jitter", type=float, default=1.0)
    parser.add_argument("--form-delay", type=float, default=3.0)
    parser.add_argument("--form-jitter", type=float, default=1.0)
    parser.add_argument("--image-delay", type=float, default=2.0)
    parser.add_argument("--image-jitter", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--search-retries", type=int, default=3)
    parser.add_argument("--image-retries", type=int, default=2)
    parser.add_argument(
        "--exclude-ttb-id-file",
        help="Optional newline or CSV file of TTB IDs to exclude from selection.",
    )
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def configure_logging() -> tuple[logging.Logger, Path]:
    """Configure a file-backed sampling logger."""

    ensure_public_cola_work_dirs()
    log_path = SAMPLING_DIR / "run.log"
    logger = logging.getLogger("public_cola_sampling")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger, log_path


def run_command(logger: logging.Logger, command: list[str]) -> None:
    """Run one command, streaming output and failing loudly on errors."""

    logger.info("RUN %s", " ".join(command))
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        logger.info(result.stdout.strip())
    if result.stderr:
        logger.warning(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def load_selected_ids(path: Path) -> list[str]:
    """Load selected TTB IDs from CSV."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [normalize_value(row["ttb_id"]) for row in csv.DictReader(handle)]


def write_id_file(path: Path, ids: list[str]) -> None:
    """Write one TTB ID per line for downstream scripts."""

    path.write_text("\n".join(ids) + "\n", encoding="utf-8")


def count_csv_rows(path: Path) -> int:
    """Count data rows in a CSV file, excluding the header."""

    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def load_json(path: Path) -> dict:
    """Load a JSON file if it exists, otherwise return an empty mapping."""

    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def db_counts(ttb_ids: list[str]) -> dict[str, int]:
    """Return form/attachment/image counts for selected IDs."""

    if not ttb_ids:
        return {
            "selected_applications": 0,
            "fetched_forms": 0,
            "parsed_forms": 0,
            "attachments_found": 0,
            "images_downloaded": 0,
        }
    placeholders = ",".join("?" for _ in ttb_ids)
    with sqlite3.connect(PUBLIC_COLA_DB_PATH) as connection:
        fetched_forms = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM form_fetches
            WHERE ttb_id IN ({placeholders}) AND raw_html_path IS NOT NULL
            """,
            ttb_ids,
        ).fetchone()[0]
        parsed_forms = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM form_fetches
            WHERE ttb_id IN ({placeholders}) AND parse_status = 'parsed'
            """,
            ttb_ids,
        ).fetchone()[0]
        attachments_found = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM attachments
            WHERE ttb_id IN ({placeholders})
            """,
            ttb_ids,
        ).fetchone()[0]
        images_downloaded = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM attachments
            WHERE ttb_id IN ({placeholders}) AND raw_image_path IS NOT NULL AND raw_image_path != ''
            """,
            ttb_ids,
        ).fetchone()[0]
        failed_image_downloads = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM attachments
            WHERE ttb_id IN ({placeholders})
              AND (raw_image_path IS NULL OR raw_image_path = '')
              AND http_status IS NOT NULL
            """,
            ttb_ids,
        ).fetchone()[0]
    return {
        "selected_applications": len(ttb_ids),
        "fetched_forms": fetched_forms,
        "parsed_forms": parsed_forms,
        "attachments_found": attachments_found,
        "images_downloaded": images_downloaded,
        "failed_image_downloads": failed_image_downloads,
    }


def remaining_seconds(deadline: float) -> float:
    """Return remaining monotonic seconds, never below zero."""

    return max(0.0, deadline - time.monotonic())


def main() -> None:
    """Run the stratified public COLA overnight workflow."""

    args = parse_args()
    logger, log_path = configure_logging()
    started = time.monotonic()
    deadline = started + args.time_budget_hours * 3600.0
    ensure_public_cola_work_dirs()
    selected_ids_path = SAMPLING_DIR / "selected_ttb_ids.txt"

    run_command(logger, ["python", "-m", "py_compile", "scripts/cola_etl/search.py", "scripts/cola_etl/sampling.py", "scripts/plan_public_cola_sample.py", "scripts/fetch_public_cola_search_results.py", "scripts/select_public_cola_sample.py", "scripts/run_public_cola_sampling_job.py"])
    run_command(logger, ["pytest", "-q", "tests/unit/test_public_cola_etl.py", "tests/unit/test_public_cola_sampling.py"])

    run_command(
        logger,
        [
            "python",
            "scripts/plan_public_cola_sample.py",
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
            "--seed",
            str(args.seed),
            "--days-per-month",
            str(args.days_per_month),
        ],
    )

    search_command = [
        "python",
        "scripts/fetch_public_cola_search_results.py",
        "--selected-days-csv",
        str(SAMPLING_DIR / "selected_days.csv"),
        "--imported-days-csv",
        str(SAMPLING_DIR / "imported_days.csv"),
        "--delay",
        str(args.search_delay),
        "--jitter",
        str(args.search_jitter),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.search_retries),
        "--time-budget-seconds",
        str(remaining_seconds(deadline)),
    ]
    if args.insecure:
        search_command.append("--insecure")
    if args.resume:
        search_command.append("--resume")
    run_command(logger, search_command)

    select_command = [
        "python",
        "scripts/select_public_cola_sample.py",
        "--target-total",
        str(min(args.target_total, args.hard_cap)),
        "--seed",
        str(args.seed),
    ]
    if args.exclude_ttb_id_file:
        select_command.extend(["--exclude-ttb-id-file", args.exclude_ttb_id_file])
    run_command(logger, select_command)

    selected_ids = load_selected_ids(SAMPLING_DIR / "selected_ttbs.csv")
    if len(selected_ids) > args.hard_cap:
        selected_ids = selected_ids[: args.hard_cap]
    write_id_file(selected_ids_path, selected_ids)
    logger.info("Selected %s TTB IDs for fetch/parse/download", len(selected_ids))

    if remaining_seconds(deadline) <= 0:
        raise RuntimeError("Time budget exhausted before form fetch.")

    form_command = [
        "python",
        "scripts/fetch_public_cola_forms.py",
        "--ttb-id-file",
        str(selected_ids_path),
        "--delay",
        str(args.form_delay),
        "--jitter",
        str(args.form_jitter),
        "--timeout",
        str(args.timeout),
        "--time-budget-seconds",
        str(remaining_seconds(deadline)),
    ]
    if args.insecure:
        form_command.append("--insecure")
    if args.resume:
        form_command.append("--resume")
    run_command(logger, form_command)

    parse_command = [
        "python",
        "scripts/parse_public_cola_forms.py",
        "--ttb-id-file",
        str(selected_ids_path),
        "--time-budget-seconds",
        str(remaining_seconds(deadline)),
    ]
    if args.resume:
        parse_command.append("--resume")
    run_command(logger, parse_command)

    image_command = [
        "python",
        "scripts/download_public_cola_images.py",
        "--ttb-id-file",
        str(selected_ids_path),
        "--delay",
        str(args.image_delay),
        "--jitter",
        str(args.image_jitter),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.image_retries),
        "--time-budget-seconds",
        str(remaining_seconds(deadline)),
    ]
    if args.insecure:
        image_command.append("--insecure")
    if args.resume:
        image_command.append("--resume")
    run_command(logger, image_command)

    counts = db_counts(selected_ids)
    selection_summary = load_json(SAMPLING_DIR / "selection_summary.json")
    summary = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "seed": args.seed,
        "target_total": args.target_total,
        "hard_cap": args.hard_cap,
        "time_budget_hours": args.time_budget_hours,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "log_path": str(log_path),
        "exclude_ttb_id_file": args.exclude_ttb_id_file,
        "selected_day_count": count_csv_rows(SAMPLING_DIR / "selected_days.csv"),
        "imported_day_count": count_csv_rows(SAMPLING_DIR / "imported_days.csv"),
    }
    summary.update(counts)
    if selection_summary:
        summary["split_counts"] = selection_summary.get("split_counts", {})
        summary["monthly_allocation"] = selection_summary.get("monthly_allocation", {})
    (SAMPLING_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    logger.info("SUMMARY %s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
