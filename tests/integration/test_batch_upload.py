from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import JOBS_DIR, ROOT
from app.main import app
from app.services.job_store import load_manifest


DEMO_DIR = ROOT / "data/fixtures/demo"


def image_part(filename: str) -> tuple[str, tuple[str, bytes, str]]:
    return (
        "label_images",
        (filename, (DEMO_DIR / filename).read_bytes(), "image/png"),
    )


def batch_image_parts() -> list[tuple[str, tuple[str, bytes, str]]]:
    with (DEMO_DIR / "batch_manifest.csv").open(encoding="utf-8", newline="") as f:
        return [image_part(row["filename"]) for row in csv.DictReader(f)]


def test_batch_upload_accepts_csv_manifest_and_multiple_images():
    client = TestClient(app)
    files = [
        ("manifest_file", ("batch_manifest.csv", (DEMO_DIR / "batch_manifest.csv").read_bytes(), "text/csv")),
        *batch_image_parts(),
    ]

    response = client.post("/jobs/batch", files=files, follow_redirects=False)
    assert response.status_code == 303

    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "8 / 8" in page.text
    assert "Needs Review" in page.text

    manifest = load_manifest(job_id)
    assert len(manifest["items"]) == 8
    first = manifest["items"][0]
    assert first["filename"] == "clean_malt_pass.png"
    assert first["stored_filename"] != "clean_malt_pass.png"
    assert (JOBS_DIR / job_id / "uploads" / first["stored_filename"]).exists()


def test_batch_upload_accepts_json_manifest():
    client = TestClient(app)
    files = [
        ("manifest_file", ("batch_manifest.json", (DEMO_DIR / "batch_manifest.json").read_bytes(), "application/json")),
        *batch_image_parts(),
    ]

    response = client.post("/jobs/batch", files=files, follow_redirects=True)
    assert response.status_code == 200
    assert "8 / 8" in response.text
    assert "warning_missing_comma_fail.png" in response.text


def test_batch_upload_rejects_malformed_csv():
    client = TestClient(app)
    files = [
        ("manifest_file", ("bad.csv", b"filename\nclean_malt_pass.png\n", "text/csv")),
        image_part("clean_malt_pass.png"),
    ]

    response = client.post("/jobs/batch", files=files)
    assert response.status_code == 400
    assert "missing required columns" in response.text


def test_batch_upload_rejects_missing_image():
    client = TestClient(app)
    manifest = (
        "filename,fixture_id,product_type,brand_name\n"
        "warning_missing_comma_fail.png,warning_missing_comma_fail,malt_beverage,OLD RIVER BREWING\n"
    ).encode()
    files = [
        ("manifest_file", ("manifest.csv", manifest, "text/csv")),
        image_part("clean_malt_pass.png"),
    ]

    response = client.post("/jobs/batch", files=files)
    assert response.status_code == 400
    assert "missing images" in response.text


def test_batch_upload_rejects_unreferenced_image():
    client = TestClient(app)
    manifest = (
        "filename,fixture_id,product_type,brand_name\n"
        "clean_malt_pass.png,clean_malt_pass,malt_beverage,OLD RIVER BREWING\n"
    ).encode()
    files = [
        ("manifest_file", ("manifest.csv", manifest, "text/csv")),
        image_part("clean_malt_pass.png"),
        image_part("warning_missing_comma_fail.png"),
    ]

    response = client.post("/jobs/batch", files=files)
    assert response.status_code == 400
    assert "not referenced" in response.text
