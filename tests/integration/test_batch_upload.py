from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.config import JOBS_DIR, ROOT
from app.main import app
from app.routes import jobs
from app.services.batch_queue import wait_for_completion
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
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "12 / 12" in page.text
    assert "Needs Review" in page.text

    manifest = load_manifest(job_id)
    assert len(manifest["items"]) == 12
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
    job_id = str(response.url).rstrip("/").split("/")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert "12 / 12" in response.text
    assert "warning_missing_comma_fail.png" in response.text


def test_batch_upload_accepts_zip_archive():
    client = TestClient(app)
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("nested/clean_malt_pass.png", (DEMO_DIR / "clean_malt_pass.png").read_bytes())
        archive.writestr("warning_missing_comma_fail.png", (DEMO_DIR / "warning_missing_comma_fail.png").read_bytes())
    manifest = (
        "filename,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents\n"
        "clean_malt_pass.png,clean_malt_pass,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
        "warning_missing_comma_fail.png,warning_missing_comma_fail,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
    ).encode()
    response = client.post(
        "/jobs/batch",
        files=[
            ("manifest_file", ("manifest.csv", manifest, "text/csv")),
            ("image_archive", ("labels.zip", buffer.getvalue(), "application/zip")),
        ],
        follow_redirects=False,
    )
    assert response.status_code == 303
    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"

    page = client.get(f"/jobs/{job_id}")
    assert "2 / 2" in page.text
    assert "Queue status:" in page.text
    assert "Completed" in page.text


def test_batch_upload_accepts_multi_panel_application_rows():
    client = TestClient(app)
    manifest = (
        "filename,panel_filenames,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents\n"
        "APP-001,clean_malt_pass.png;warning_missing_comma_fail.png,app_001,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
    ).encode()
    response = client.post(
        "/jobs/batch",
        files=[
            ("manifest_file", ("manifest.csv", manifest, "text/csv")),
            image_part("clean_malt_pass.png"),
            image_part("warning_missing_comma_fail.png"),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"

    manifest_doc = load_manifest(job_id)
    assert manifest_doc["items"][0]["filename"] == "APP-001"
    assert len(manifest_doc["items"][0]["stored_filenames"]) == 2
    page = client.get(f"/jobs/{job_id}/items/app_001")
    assert page.status_code == 200
    assert "Submitted Label Panels" in page.text
    assert "APP-001" in page.text


def test_application_directory_upload_discovers_manifest_and_nested_images():
    client = TestClient(app)
    manifest = (
        "filename,panel_filenames,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents\n"
        "APP-001,images/APP-001/clean_malt_pass.png;images/APP-001/warning_missing_comma_fail.png,app_001,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
    ).encode()
    response = client.post(
        "/jobs/application-directory",
        files=[
            ("application_directory", ("public-cola-300/manifest.csv", manifest, "text/csv")),
            ("application_directory", ("public-cola-300/README.md", b"ignored helper file", "text/markdown")),
            ("application_directory", ("public-cola-300/public-cola-demo-pack.zip", b"ignored helper file", "application/zip")),
            (
                "application_directory",
                (
                    "public-cola-300/images/APP-001/clean_malt_pass.png",
                    (DEMO_DIR / "clean_malt_pass.png").read_bytes(),
                    "image/png",
                ),
            ),
            (
                "application_directory",
                (
                    "public-cola-300/images/APP-001/warning_missing_comma_fail.png",
                    (DEMO_DIR / "warning_missing_comma_fail.png").read_bytes(),
                    "image/png",
                ),
            ),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"

    manifest_doc = load_manifest(job_id)
    assert manifest_doc["label"] == "directory demo upload (1 applications)"
    assert manifest_doc["items"][0]["original_filenames"] == [
        "images/APP-001/clean_malt_pass.png",
        "images/APP-001/warning_missing_comma_fail.png",
    ]
    page = client.get(f"/jobs/{job_id}/items/app_001")
    assert page.status_code == 200
    assert "Actual COLA Application Data" in page.text
    assert "Real Label Images And OCR Evidence" in page.text


def test_application_directory_upload_can_parse_selected_application_only():
    client = TestClient(app)
    manifest = (
        "filename,panel_filenames,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents\n"
        "APP-001,images/APP-001/clean_malt_pass.png,app_001,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
        "APP-002,images/APP-002/warning_missing_comma_fail.png,app_002,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint\n"
    ).encode()
    response = client.post(
        "/jobs/application-directory",
        data={"parse_scope": "application", "selected_application": "APP-002"},
        files=[
            ("application_directory", ("public-cola-300/manifest.csv", manifest, "text/csv")),
            (
                "application_directory",
                (
                    "public-cola-300/images/APP-001/clean_malt_pass.png",
                    (DEMO_DIR / "clean_malt_pass.png").read_bytes(),
                    "image/png",
                ),
            ),
            (
                "application_directory",
                (
                    "public-cola-300/images/APP-002/warning_missing_comma_fail.png",
                    (DEMO_DIR / "warning_missing_comma_fail.png").read_bytes(),
                    "image/png",
                ),
            ),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"

    manifest_doc = load_manifest(job_id)
    assert manifest_doc["label"] == "single application demo upload (APP-002)"
    assert len(manifest_doc["items"]) == 1
    assert manifest_doc["items"][0]["filename"] == "APP-002"
    page = client.get(f"/jobs/{job_id}")
    assert "1 / 1" in page.text
    assert "Total parse time:" in page.text
    assert "Time per application:" in page.text
    assert "APP-002" in page.text
    assert "APP-001" not in page.text


def test_public_cola_demo_uses_server_side_pack_and_selected_application(monkeypatch, tmp_path):
    demo_root = tmp_path / "public-cola-300"
    image_dir = demo_root / "images" / "APP-002"
    image_dir.mkdir(parents=True)
    (demo_root / "images" / "APP-001").mkdir(parents=True)
    (demo_root / "images" / "APP-001" / "clean_malt_pass.png").write_bytes((DEMO_DIR / "clean_malt_pass.png").read_bytes())
    (image_dir / "warning_missing_comma_fail.png").write_bytes((DEMO_DIR / "warning_missing_comma_fail.png").read_bytes())
    (demo_root / "manifest.csv").write_text(
        "\n".join(
            [
                "filename,panel_filenames,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents",
                "APP-001,images/APP-001/clean_malt_pass.png,app_001,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint",
                "APP-002,images/APP-002/warning_missing_comma_fail.png,app_002,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs, "PUBLIC_COLA_DEMO_DIR", demo_root)
    client = TestClient(app)

    page = client.get("/public-cola-demo")
    assert page.status_code == 200
    assert "Parse This Application" in page.text
    assert "Parse This Directory of Applications" in page.text
    assert "Current Application Field Comparison" in page.text
    assert "Actual" in page.text
    assert "Scraped" in page.text
    assert "Application directory" not in page.text

    response = client.post(
        "/public-cola-demo/parse",
        data={"parse_scope": "application", "selected_application": "APP-002"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    job_id = response.headers["location"].split("job_id=")[-1]
    status = wait_for_completion(job_id, timeout_seconds=5)
    assert status and status["status"] == "completed"
    manifest_doc = load_manifest(job_id)
    assert manifest_doc["label"] == "public COLA demo application APP-002"
    assert len(manifest_doc["items"]) == 1
    assert manifest_doc["items"][0]["filename"] == "APP-002"
    result_page = client.get(f"/public-cola-demo?job_id={job_id}")
    assert "Total parse time:" in result_page.text
    assert "Time per application:" in result_page.text
    comparison = client.get(f"/public-cola-demo/comparison-data/{job_id}")
    assert comparison.status_code == 200
    payload = comparison.json()
    assert payload["queue_status"]["status"] == "completed"
    assert "app_002" in payload["comparison_rows"]
    assert payload["comparison_rows"]["app_002"][0]["label"] == "Brand name"

    reset = client.post("/public-cola-demo/reset", data={"job_id": job_id}, follow_redirects=False)
    assert reset.status_code == 303
    assert not (JOBS_DIR / job_id).exists()


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
