from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.config import JOBS_DIR
from app.schemas.results import VerificationResult


def create_job(label: str) -> str:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    (job_dir(job_id) / "results").mkdir(exist_ok=True)
    (job_dir(job_id) / "uploads").mkdir(exist_ok=True)
    write_json(job_dir(job_id) / "manifest.json", {"job_id": job_id, "label": label, "items": []})
    return job_id


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def add_manifest_item(job_id: str, item: dict) -> None:
    path = job_dir(job_id) / "manifest.json"
    manifest = read_json(path)
    manifest["items"].append(item)
    write_json(path, manifest)


def save_upload(job_id: str, source: Path, filename: str) -> Path:
    dest = job_dir(job_id) / "uploads" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest


def write_result(result: VerificationResult) -> None:
    payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    write_json(
        job_dir(result.job_id) / "results" / f"{result.item_id}.json",
        payload,
    )


def load_result(job_id: str, item_id: str) -> VerificationResult:
    return VerificationResult(**read_json(job_dir(job_id) / "results" / f"{item_id}.json"))


def list_results(job_id: str) -> list[VerificationResult]:
    results_path = job_dir(job_id) / "results"
    results = [
        VerificationResult(**read_json(path))
        for path in sorted(results_path.glob("*.json"))
    ]
    return results


def load_manifest(job_id: str) -> dict:
    return read_json(job_dir(job_id) / "manifest.json")
