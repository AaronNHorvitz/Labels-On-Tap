"""Filesystem-backed batch queue for manifest upload jobs.

Notes
-----
This is intentionally small: one local worker thread processes queued jobs from
JSON files under each job directory. It is durable enough for the take-home
demo because queued work is visible on disk and unfinished jobs are recovered on
application startup. A production federal deployment should replace this with a
real broker and worker pool.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import JOBS_DIR
from app.services.job_store import job_dir, read_json, write_json


QUEUE_FILENAME = "queue.json"
BatchProcessor = Callable[[str, dict[str, Any], Callable[[int, int], None]], None]

_processor: BatchProcessor | None = None
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_wake_event = threading.Event()


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for queue status files."""

    return datetime.now(timezone.utc).isoformat()


def queue_path(job_id: str) -> Path:
    """Return the queue status path for a job."""

    return job_dir(job_id) / QUEUE_FILENAME


def write_queue_status(job_id: str, status: dict[str, Any]) -> None:
    """Persist one queue status object."""

    status["updated_at"] = utc_now()
    write_json(queue_path(job_id), status)


def load_queue_status(job_id: str) -> dict[str, Any] | None:
    """Load queue status for a job if the job was queue-backed."""

    path = queue_path(job_id)
    if not path.exists():
        return None
    return read_json(path)


def enqueue_batch(job_id: str, payload: dict[str, Any]) -> None:
    """Create or replace a pending queue record and wake the worker."""

    total = len(payload.get("items", []))
    write_queue_status(
        job_id,
        {
            "job_id": job_id,
            "kind": "batch",
            "status": "queued",
            "created_at": utc_now(),
            "started_at": "",
            "finished_at": "",
            "total": total,
            "processed": 0,
            "failures": [],
            "payload": payload,
        },
    )
    _wake_event.set()


def mark_progress(job_id: str, processed: int, total: int) -> None:
    """Update queue progress after a worker writes item results."""

    status = load_queue_status(job_id)
    if status is None:
        return
    if not status.get("started_at"):
        status["started_at"] = utc_now()
    status["processed"] = processed
    status["total"] = total
    write_queue_status(job_id, status)


def _claim(job_id: str) -> dict[str, Any] | None:
    """Move a queued job to running state."""

    status = load_queue_status(job_id)
    if status is None or status.get("status") != "queued":
        return None
    status["status"] = "running"
    status["started_at"] = status.get("started_at") or utc_now()
    write_queue_status(job_id, status)
    return status


def _finish(job_id: str, *, failed: bool = False, error: str = "") -> None:
    """Mark a queue job completed or failed."""

    status = load_queue_status(job_id)
    if status is None:
        return
    status["status"] = "failed" if failed else "completed"
    status["finished_at"] = utc_now()
    if error:
        status.setdefault("failures", []).append({"error": error, "at": utc_now()})
    write_queue_status(job_id, status)


def _queued_job_ids() -> list[str]:
    """Return queued job IDs in creation order."""

    jobs: list[tuple[str, str]] = []
    if not JOBS_DIR.exists():
        return []
    for path in JOBS_DIR.iterdir():
        if not path.is_dir():
            continue
        status_path = path / QUEUE_FILENAME
        if not status_path.exists():
            continue
        try:
            status = read_json(status_path)
        except Exception:
            continue
        if status.get("status") == "queued":
            jobs.append((status.get("created_at", ""), path.name))
    return [job_id for _, job_id in sorted(jobs)]


def recover_unfinished_jobs() -> None:
    """Put interrupted running jobs back into the queue on startup."""

    if not JOBS_DIR.exists():
        return
    for path in JOBS_DIR.iterdir():
        status_path = path / QUEUE_FILENAME
        if not status_path.exists():
            continue
        try:
            status = read_json(status_path)
        except Exception:
            continue
        if status.get("status") == "running":
            status["status"] = "queued"
            status["recovered_at"] = utc_now()
            write_json(status_path, status)


def _worker_loop() -> None:
    """Run queued batch jobs sequentially."""

    while True:
        _wake_event.clear()
        if _processor is None:
            _wake_event.wait(1.0)
            continue
        for job_id in _queued_job_ids():
            status = _claim(job_id)
            if status is None:
                continue
            try:
                payload = status.get("payload", {})
                _processor(job_id, payload, lambda processed, total, jid=job_id: mark_progress(jid, processed, total))
            except Exception as exc:  # pragma: no cover - defensive worker armor
                _finish(job_id, failed=True, error=str(exc))
            else:
                _finish(job_id)
        _wake_event.wait(0.5)


def start_worker(processor: BatchProcessor) -> None:
    """Start the singleton local queue worker if it is not already running."""

    global _processor, _worker_thread
    with _worker_lock:
        _processor = processor
        recover_unfinished_jobs()
        if _worker_thread and _worker_thread.is_alive():
            _wake_event.set()
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="labels-on-tap-batch-worker", daemon=True)
        _worker_thread.start()
        _wake_event.set()


def wait_for_completion(job_id: str, *, timeout_seconds: float = 10.0) -> dict[str, Any] | None:
    """Wait for a queue-backed job to finish.

    This helper is used only by tests and smoke checks. UI code should poll the
    normal job status route instead.
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = load_queue_status(job_id)
        if status is None or status.get("status") in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    return load_queue_status(job_id)
