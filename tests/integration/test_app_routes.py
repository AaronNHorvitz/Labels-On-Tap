from fastapi.testclient import TestClient

from app.config import JOBS_DIR, ROOT
from app.main import app
from app.services.job_store import load_manifest, load_result


DEMO_FIXTURE = ROOT / "data/fixtures/demo/clean_malt_pass.png"


def single_upload_form() -> dict[str, str]:
    return {
        "brand_name": "OLD RIVER BREWING",
        "product_type": "malt_beverage",
        "class_type": "Ale",
        "alcohol_content": "5% ALC/VOL",
        "net_contents": "1 Pint",
        "imported": "false",
        "country_of_origin": "",
    }


def test_health_route():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_clean_demo_route_renders_pass_result():
    client = TestClient(app)
    response = client.get("/demo/clean", follow_redirects=True)
    assert response.status_code == 200
    assert "Review Results" in response.text
    assert "Pass" in response.text
    assert "fixture ground truth" in response.text


def test_batch_demo_route_renders_counts_and_csv():
    client = TestClient(app)
    response = client.get("/demo/batch", follow_redirects=True)
    assert response.status_code == 200
    assert "12 / 12" in response.text
    assert "Needs Review" in response.text

    job_id = str(response.url).rstrip("/").split("/")[-1]
    csv_response = client.get(f"/jobs/{job_id}/results.csv")
    assert csv_response.status_code == 200
    assert "filename,overall_verdict" in csv_response.text
    assert "clean_malt_pass.png,pass" in csv_response.text
    assert "low_confidence_blur_review.png,needs_review" in csv_response.text
    assert "brand_mismatch_fail.png,fail" in csv_response.text


def test_item_detail_page_shows_rule_evidence_and_actions():
    client = TestClient(app)
    response = client.get("/demo/warning", follow_redirects=True)
    assert response.status_code == 200

    job_id = str(response.url).rstrip("/").split("/")[-1]
    item_id = load_manifest(job_id)["items"][0]["item_id"]
    detail = client.get(f"/jobs/{job_id}/items/{item_id}")

    assert detail.status_code == 200
    assert "GOV_WARNING_EXACT_TEXT" in detail.text
    assert "Expected:" in detail.text
    assert "Observed:" in detail.text
    assert "Evidence text" in detail.text
    assert "Reviewer action:" in detail.text
    assert "Sources:" in detail.text


def test_single_upload_randomizes_storage_and_preserves_original_filename():
    client = TestClient(app)
    image_bytes = DEMO_FIXTURE.read_bytes()
    response = client.post(
        "/jobs",
        data=single_upload_form(),
        files={"label_image": ("clean_malt_pass.png", image_bytes, "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    job_id = response.headers["location"].rstrip("/").split("/")[-1]
    manifest = load_manifest(job_id)
    item = manifest["items"][0]
    result = load_result(job_id, item["item_id"])

    assert item["original_filename"] == "clean_malt_pass.png"
    assert item["filename"] == "clean_malt_pass.png"
    assert item["stored_filename"] != "clean_malt_pass.png"
    assert item["stored_filename"].endswith(".png")
    assert (JOBS_DIR / job_id / "uploads" / item["stored_filename"]).exists()
    assert not (JOBS_DIR / job_id / "uploads" / "clean_malt_pass.png").exists()
    assert result.filename == "clean_malt_pass.png"
    assert result.ocr["source"] == "fixture ground truth"


def test_single_upload_rejects_bad_signature():
    client = TestClient(app)
    response = client.post(
        "/jobs",
        data=single_upload_form(),
        files={"label_image": ("label.png", b"not a png", "image/png")},
    )

    assert response.status_code == 400
    assert "signature" in response.text


def test_upload_error_renders_html_for_browser_accept_header():
    client = TestClient(app)
    response = client.post(
        "/jobs",
        data=single_upload_form(),
        files={"label_image": ("label.png", b"not a png", "image/png")},
        headers={"accept": "text/html"},
    )

    assert response.status_code == 400
    assert "Upload Problem" in response.text
    assert "signature" in response.text


def test_single_upload_rejects_corrupt_png_after_signature_check():
    client = TestClient(app)
    response = client.post(
        "/jobs",
        data=single_upload_form(),
        files={"label_image": ("label.png", b"\x89PNG\r\n\x1a\nnot-a-real-png", "image/png")},
    )

    assert response.status_code == 400
    assert "readable JPG/PNG image" in response.text


def test_single_upload_rejects_oversize(monkeypatch):
    from app.routes import jobs

    monkeypatch.setattr(jobs, "MAX_UPLOAD_BYTES", 8)
    client = TestClient(app)
    response = client.post(
        "/jobs",
        data=single_upload_form(),
        files={"label_image": ("clean_malt_pass.png", DEMO_FIXTURE.read_bytes(), "image/png")},
    )

    assert response.status_code == 413
    assert "maximum size" in response.text
