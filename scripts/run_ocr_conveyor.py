#!/usr/bin/env python
"""Run a resumable, subprocess-isolated OCR conveyor over COLA images.

The conveyor is the armored layer before the final tri-engine OCR evidence run.
It does not implement OCR itself. Instead, it:

* reads application-level split manifests,
* preflights every image with signature and Pillow decode checks,
* groups valid images into small engine-specific chunks,
* launches each chunk in a subprocess using the OCR benchmark runner,
* records stdout/stderr, status, return codes, and row counts,
* skips completed chunks on resume.

Why subprocess chunks?

Python ``try/except`` catches normal OCR exceptions, but not native runtime
abort paths such as segmentation faults, hard ONNX/Paddle failures, or process
OOM kills. Running each chunk in a separate process prevents one bad image or
native engine crash from taking down the whole overnight run.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.preflight.file_signature import has_allowed_image_signature, is_pillow_decodable_image


DEFAULT_SPLIT_DIR = REPO_ROOT / "data/work/cola/evaluation-splits/field-support-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/work/ocr-conveyor/tri-engine-v1"
BENCHMARK_SCRIPT = REPO_ROOT / "experiments/ocr_engine_sweep/benchmark_ocr_engines.py"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class ImageManifestRow:
    """One image discovered from an application split manifest."""

    split: str
    ttb_id: str
    image_path: str
    preflight_status: str
    preflight_error: str = ""


@dataclass(frozen=True)
class ConveyorJob:
    """One subprocess OCR chunk job."""

    job_id: str
    split: str
    engine: str
    chunk_index: int
    image_count: int
    image_paths: list[str]


@dataclass(frozen=True)
class JobResult:
    """Final status for one conveyor chunk."""

    job_id: str
    split: str
    engine: str
    chunk_index: int
    image_count: int
    status: str
    returncode: int | None
    ok_rows: int
    error_rows: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    rows_csv: str
    stdout_log: str
    stderr_log: str
    error: str = ""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--split",
        action="append",
        choices=["train", "validation", "holdout"],
        help="Split to process. May be supplied more than once. Defaults to train + validation.",
    )
    parser.add_argument(
        "--engine",
        action="append",
        choices=["doctr", "paddleocr", "openocr"],
        help="OCR engine to process. May be supplied more than once.",
    )
    parser.add_argument("--chunk-size", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--limit-images", type=int, default=None)
    parser.add_argument("--python", default=sys.executable, help="Python executable used for subprocess OCR chunks.")
    parser.add_argument("--force", action="store_true", help="Rerun completed jobs.")
    parser.add_argument("--dry-run", action="store_true", help="Write manifests but do not run OCR subprocesses.")
    return parser.parse_args()


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat(timespec="seconds")


def resolve_path(path: Path) -> Path:
    """Resolve repo-relative paths."""

    return path if path.is_absolute() else REPO_ROOT / path


def relative_path(path: Path) -> str:
    """Return repo-relative path when possible."""

    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_split_manifest(split_dir: Path, split: str) -> list[dict[str, str]]:
    """Read one application-level split manifest."""

    path = split_dir / f"{split}_applications.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def discover_images_for_row(row: dict[str, str]) -> list[Path]:
    """Discover label image files for one manifest row."""

    image_dir_text = row.get("image_dir", "")
    if not image_dir_text:
        return []
    image_dir = resolve_path(Path(image_dir_text))
    if not image_dir.exists():
        return []
    return sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def preflight_image(path: Path) -> tuple[str, str]:
    """Return image preflight status and error text."""

    if not has_allowed_image_signature(path):
        return "invalid", "unsupported_or_missing_image_signature"
    if not is_pillow_decodable_image(path):
        return "invalid", "pillow_decode_failed"
    return "valid", ""


def build_image_manifest(
    *,
    split_dir: Path,
    splits: list[str],
    limit_images: int | None,
) -> list[ImageManifestRow]:
    """Build image manifest rows from split application manifests."""

    rows: list[ImageManifestRow] = []
    for split in splits:
        for app_row in read_split_manifest(split_dir, split):
            for image_path in discover_images_for_row(app_row):
                status, error = preflight_image(image_path)
                rows.append(
                    ImageManifestRow(
                        split=split,
                        ttb_id=app_row["ttb_id"],
                        image_path=relative_path(image_path),
                        preflight_status=status,
                        preflight_error=error,
                    )
                )
                if limit_images is not None and len(rows) >= limit_images:
                    return rows
    return rows


def chunked(items: list[ImageManifestRow], size: int) -> Iterable[list[ImageManifestRow]]:
    """Yield fixed-size chunks."""

    if size < 1:
        raise ValueError("chunk size must be at least 1")
    for index in range(0, len(items), size):
        yield items[index : index + size]


def job_id_for(engine: str, split: str, chunk_index: int) -> str:
    """Return a stable job identifier."""

    return f"{engine}_{split}_{chunk_index:06d}"


def build_jobs(rows: list[ImageManifestRow], engines: list[str], chunk_size: int) -> list[ConveyorJob]:
    """Build subprocess OCR jobs for valid images."""

    jobs: list[ConveyorJob] = []
    valid_by_split: dict[str, list[ImageManifestRow]] = {}
    for row in rows:
        if row.preflight_status != "valid":
            continue
        valid_by_split.setdefault(row.split, []).append(row)

    for engine in engines:
        for split in sorted(valid_by_split):
            for chunk_index, chunk in enumerate(chunked(valid_by_split[split], chunk_size), start=1):
                jobs.append(
                    ConveyorJob(
                        job_id=job_id_for(engine, split, chunk_index),
                        split=split,
                        engine=engine,
                        chunk_index=chunk_index,
                        image_count=len(chunk),
                        image_paths=[row.image_path for row in chunk],
                    )
                )
    return jobs


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Write dictionaries as CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict) -> None:
    """Write pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_existing_result(path: Path) -> JobResult | None:
    """Read an existing job result if it exists."""

    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return JobResult(**payload)
    except Exception:
        return None


def count_rows(rows_csv: Path) -> tuple[int, int]:
    """Count ok/error OCR rows from a benchmark rows.csv."""

    if not rows_csv.exists():
        return 0, 0
    ok_rows = error_rows = 0
    with rows_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") == "ok":
                ok_rows += 1
            else:
                error_rows += 1
    return ok_rows, error_rows


def run_job(
    *,
    job: ConveyorJob,
    output_dir: Path,
    python_executable: str,
    timeout_seconds: int,
    force: bool,
) -> JobResult:
    """Run one OCR subprocess chunk or return existing completed result."""

    job_dir = output_dir / "jobs" / job.job_id
    result_path = job_dir / "result.json"
    existing = read_existing_result(result_path)
    if existing and existing.status == "completed" and not force:
        return existing

    job_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    run_name = job.job_id
    rows_csv = runs_dir / run_name / "rows.csv"
    stdout_log = job_dir / "stdout.log"
    stderr_log = job_dir / "stderr.log"

    command = [
        python_executable,
        str(BENCHMARK_SCRIPT),
        "--engine",
        job.engine,
        "--limit",
        str(job.image_count),
        "--output-dir",
        str(runs_dir),
        "--run-name",
        run_name,
    ]
    for image_path in job.image_paths:
        command.extend(["--image", str(REPO_ROOT / image_path)])

    started_at = utc_now()
    started = datetime.now(UTC)
    error = ""
    returncode: int | None = None
    status = "completed"
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout_log.write_text(completed.stdout, encoding="utf-8")
        stderr_log.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            status = "subprocess_failed"
            error = f"returncode={completed.returncode}"
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        error = f"timeout_after_{timeout_seconds}_seconds"
        stdout_log.write_text(exc.stdout or "", encoding="utf-8")
        stderr_log.write_text(exc.stderr or "", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - conveyor records and continues.
        status = "launcher_error"
        error = str(exc)
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text(str(exc), encoding="utf-8")

    finished = datetime.now(UTC)
    ok_rows, error_rows = count_rows(rows_csv)
    if status == "completed" and ok_rows + error_rows != job.image_count:
        status = "incomplete_rows"
        error = f"expected {job.image_count} row(s), got {ok_rows + error_rows}"

    result = JobResult(
        job_id=job.job_id,
        split=job.split,
        engine=job.engine,
        chunk_index=job.chunk_index,
        image_count=job.image_count,
        status=status,
        returncode=returncode,
        ok_rows=ok_rows,
        error_rows=error_rows,
        started_at=started_at,
        finished_at=finished.isoformat(timespec="seconds"),
        elapsed_seconds=round((finished - started).total_seconds(), 3),
        rows_csv=relative_path(rows_csv),
        stdout_log=relative_path(stdout_log),
        stderr_log=relative_path(stderr_log),
        error=error,
    )
    write_json(result_path, asdict(result))
    return result


def summarize(
    *,
    image_rows: list[ImageManifestRow],
    jobs: list[ConveyorJob],
    results: list[JobResult],
    dry_run: bool,
) -> dict:
    """Build a conveyor summary payload."""

    return {
        "created_at": utc_now(),
        "dry_run": dry_run,
        "image_count": len(image_rows),
        "valid_image_count": sum(1 for row in image_rows if row.preflight_status == "valid"),
        "invalid_image_count": sum(1 for row in image_rows if row.preflight_status != "valid"),
        "image_preflight_counts": dict(Counter(row.preflight_status for row in image_rows)),
        "images_by_split": dict(Counter(row.split for row in image_rows)),
        "job_count": len(jobs),
        "job_status_counts": dict(Counter(result.status for result in results)),
        "rows_ok": sum(result.ok_rows for result in results),
        "rows_error": sum(result.error_rows for result in results),
        "engines": sorted({job.engine for job in jobs}),
        "splits": sorted({job.split for job in jobs}),
    }


def main() -> None:
    """Run the OCR conveyor."""

    args = parse_args()
    args.split_dir = resolve_path(args.split_dir)
    args.output_dir = resolve_path(args.output_dir)
    splits = args.split or ["train", "validation"]
    engines = args.engine or ["doctr", "paddleocr", "openocr"]

    image_rows = build_image_manifest(
        split_dir=args.split_dir,
        splits=splits,
        limit_images=args.limit_images,
    )
    jobs = build_jobs(image_rows, engines, args.chunk_size)

    manifest_dir = args.output_dir / "manifest"
    write_csv(
        manifest_dir / "images.csv",
        [asdict(row) for row in image_rows],
        ["split", "ttb_id", "image_path", "preflight_status", "preflight_error"],
    )
    write_csv(
        manifest_dir / "jobs.csv",
        [
            {
                "job_id": job.job_id,
                "split": job.split,
                "engine": job.engine,
                "chunk_index": job.chunk_index,
                "image_count": job.image_count,
                "image_paths": json.dumps(job.image_paths),
            }
            for job in jobs
        ],
        ["job_id", "split", "engine", "chunk_index", "image_count", "image_paths"],
    )

    results: list[JobResult] = []
    if args.dry_run:
        print(f"Dry run: {len(image_rows)} image row(s), {len(jobs)} OCR chunk job(s).")
    else:
        for index, job in enumerate(jobs, start=1):
            print(f"[{index}/{len(jobs)}] {job.job_id} {job.image_count} image(s)")
            result = run_job(
                job=job,
                output_dir=args.output_dir,
                python_executable=args.python,
                timeout_seconds=args.timeout_seconds,
                force=args.force,
            )
            results.append(result)
            print(f"  {result.status}: ok={result.ok_rows} error={result.error_rows} elapsed={result.elapsed_seconds}s")

    summary = summarize(image_rows=image_rows, jobs=jobs, results=results, dry_run=args.dry_run)
    write_json(args.output_dir / "summary.json", summary)
    print()
    print(f"Conveyor output: {relative_path(args.output_dir)}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
