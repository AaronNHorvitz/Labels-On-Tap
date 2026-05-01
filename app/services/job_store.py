"""Filesystem job store for prototype uploads and results.

Notes
-----
The take-home avoids a database so reviewers can inspect every job artifact as
plain files. Each job has a manifest, randomized uploads, and one JSON result
file per reviewed label.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.config import JOBS_DIR
from app.schemas.results import VerificationResult


def create_job(label: str) -> str:
    """Create a new filesystem-backed job.

    Parameters
    ----------
    label:
        Human-readable job label stored in ``manifest.json``.

    Returns
    -------
    str
        Short random job identifier.
    """

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    (job_dir(job_id) / "results").mkdir(exist_ok=True)
    (job_dir(job_id) / "uploads").mkdir(exist_ok=True)
    write_json(job_dir(job_id) / "manifest.json", {"job_id": job_id, "label": label, "items": []})
    return job_id


def job_dir(job_id: str) -> Path:
    """Return the directory path for a job ID."""

    return JOBS_DIR / job_id


def write_json(path: Path, payload: object) -> None:
    """Atomically write JSON to disk.

    Notes
    -----
    A temporary file plus replace keeps readers from seeing partial JSON while
    synchronous processing is writing a result.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> dict:
    """Read a UTF-8 JSON object from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def add_manifest_item(job_id: str, item: dict) -> None:
    """Append an item entry to a job manifest."""

    path = job_dir(job_id) / "manifest.json"
    manifest = read_json(path)
    manifest["items"].append(item)
    write_json(path, manifest)


def save_upload(job_id: str, source: Path, filename: str) -> Path:
    """Copy an existing file into a job's upload directory.

    Notes
    -----
    Demo fixtures use this helper because they are already trusted repository
    files. User uploads are validated and randomized before being moved.
    """

    dest = job_dir(job_id) / "uploads" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest


def write_result(result: VerificationResult) -> None:
    """Write one label verification result to the job result directory."""

    payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    write_json(
        job_dir(result.job_id) / "results" / f"{result.item_id}.json",
        payload,
    )


def load_result(job_id: str, item_id: str) -> VerificationResult:
    """Load a single verification result."""

    return VerificationResult(**read_json(job_dir(job_id) / "results" / f"{item_id}.json"))


def list_results(job_id: str) -> list[VerificationResult]:
    """Load all verification results for a job sorted by filename on disk."""

    results_path = job_dir(job_id) / "results"
    results = [
        VerificationResult(**read_json(path))
        for path in sorted(results_path.glob("*.json"))
    ]
    return results


def load_manifest(job_id: str) -> dict:
    """Load a job manifest."""

    return read_json(job_dir(job_id) / "manifest.json")
