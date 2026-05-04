from fastapi.testclient import TestClient

from app.config import JOBS_DIR, ROOT
from app.main import app
from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from app.services.cola_cloud_demo import ColaCloudDemoSource, ColaCloudPanel
from app.services.job_store import add_manifest_item, create_job, load_manifest, load_result, save_upload, write_result
from app.services.rules.registry import verify_label


FIXTURE_DIR = ROOT / "data/fixtures/demo"
DEMO_FIXTURE = FIXTURE_DIR / "clean_malt_pass.png"


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


def test_landing_page_links_to_demo_and_actual_app():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "LOT Demo" in response.text
    assert "LOT Actual" in response.text
    assert 'href="/public-cola-demo"' in response.text
    assert 'href="/app"' in response.text
    assert "labels_on_tap_hero.png" in response.text or "landing-hero" in response.text


def test_actual_app_workspace_keeps_upload_controls():
    client = TestClient(app)
    response = client.get("/app")

    assert response.status_code == 200
    assert "LOT Actual" in response.text
    assert "Data Format Instructions" in response.text
    assert "Example Data" in response.text
    assert "Human Review Required" in response.text
    assert "Auto-Route Clear Decisions" in response.text
    assert "Current Application Field Comparison" in response.text
    assert 'name="application_directory"' in response.text


def test_data_format_page_renders_upload_instructions():
    client = TestClient(app)
    response = client.get("/data-format")

    assert response.status_code == 200
    assert "Data Format" in response.text
    assert "manifest.csv" in response.text
    assert "panel_filenames" in response.text


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
    assert "Application Truth vs Parsed Label Evidence" in response.text
    assert "Actual COLA Application Data" in response.text
    assert "Parsed Label Data" in response.text
    assert "OLD RIVER BREWING" in response.text
    assert 'name="reviewer_decision" value="accept"' in response.text
    assert 'name="reviewer_decision" value="reject"' in response.text
    assert "Open full evidence and reviewer actions" in response.text

    job_id = str(response.url).rstrip("/").split("/")[-1]
    csv_response = client.get(f"/jobs/{job_id}/results.csv")
    assert csv_response.status_code == 200
    assert "filename,raw_verdict,overall_verdict,policy_queue" in csv_response.text
    assert "expected_values,observed_values,evidence_text,reviewer_actions" in csv_response.text
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
    assert "Actual application value" in detail.text
    assert "Real label / OCR evidence" in detail.text
    assert "Evidence text" in detail.text
    assert "Reviewer action:" in detail.text
    assert "Sources:" in detail.text
    assert "Real Label Images And OCR Evidence" in detail.text
    assert "Submitted Label" in detail.text
    assert f"/jobs/{job_id}/uploads/warning_missing_comma_fail.png" in detail.text

    image_response = client.get(f"/jobs/{job_id}/uploads/warning_missing_comma_fail.png")
    assert image_response.status_code == 200


def test_item_detail_shows_warning_crop_when_ocr_boxes_exist():
    client = TestClient(app)
    job_id = create_job("boxed warning unit")
    image_path = save_upload(job_id, DEMO_FIXTURE, "boxed_warning.png")
    ocr = OCRResult(
        fixture_id="boxed_warning",
        filename=image_path.name,
        full_text="GOVERNMENT WARNING: Alcohol content.",
        avg_confidence=0.98,
        blocks=[
            {"text": "GOVERNMENT", "confidence": 0.98, "bbox": [[0.10, 0.62], [0.31, 0.66]]},
            {"text": "WARNING:", "confidence": 0.98, "bbox": [[0.33, 0.62], [0.52, 0.66]]},
        ],
        source="unit boxed OCR",
        total_ms=12,
    )
    application = ColaApplication(
        filename="boxed_warning.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
    )
    result = verify_label(job_id, "boxed_warning", application, ocr)
    write_result(result)
    add_manifest_item(job_id, {"item_id": "boxed_warning", "filename": "boxed_warning.png"})

    detail = client.get(f"/jobs/{job_id}/items/boxed_warning")
    assert detail.status_code == 200
    assert "Detected government warning heading crop" in detail.text
    assert "/jobs/" in detail.text
    assert "GOVERNMENT" in detail.text
    assert "WARNING:" in detail.text

    crop = client.get(f"/jobs/{job_id}/items/boxed_warning/warning-crop.png")
    assert crop.status_code == 200
    assert crop.headers["content-type"] == "image/png"


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


def test_multipanel_upload_combines_label_panel_evidence():
    client = TestClient(app)
    response = client.post(
        "/jobs/multipanel",
        data=single_upload_form(),
        files=[
            ("label_images", ("clean_malt_pass.png", DEMO_FIXTURE.read_bytes(), "image/png")),
            ("label_images", ("clean_malt_pass.png", DEMO_FIXTURE.read_bytes(), "image/png")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "1 / 1" in response.text
    assert "Ready to accept" in response.text

    job_id = str(response.url).rstrip("/").split("/")[-1]
    item_id = load_manifest(job_id)["items"][0]["item_id"]
    detail = client.get(f"/jobs/{job_id}/items/{item_id}")
    assert detail.status_code == 200
    assert "Submitted Label Panels" in detail.text
    assert "[Panel 1:" in detail.text
    assert "[Panel 2:" in detail.text


def test_reviewer_decision_is_persisted_and_exported():
    client = TestClient(app)
    response = client.get("/demo/clean", follow_redirects=True)
    job_id = str(response.url).rstrip("/").split("/")[-1]
    item_id = load_manifest(job_id)["items"][0]["item_id"]

    save = client.post(
        f"/jobs/{job_id}/items/{item_id}/review",
        data={"reviewer_decision": "accept", "reviewer_note": "Looks clean."},
        follow_redirects=True,
    )
    assert save.status_code == 200
    assert "Saved decision:" in save.text
    assert "Looks clean." in save.text

    result = load_result(job_id, item_id)
    assert result.reviewer_decision == "accept"
    assert result.reviewer_note == "Looks clean."
    assert result.reviewed_at

    csv_response = client.get(f"/jobs/{job_id}/results.csv")
    assert "reviewer_decision,reviewer_note,reviewed_at" in csv_response.text
    assert "Looks clean." in csv_response.text


def test_reviewer_dashboard_lists_existing_results():
    client = TestClient(app)
    response = client.get("/demo/warning", follow_redirects=True)
    assert response.status_code == 200
    job_id = str(response.url).rstrip("/").split("/")[-1]
    item_id = load_manifest(job_id)["items"][0]["item_id"]

    dashboard = client.get("/review")
    assert dashboard.status_code == 200
    assert "Reviewer Dashboard" in dashboard.text
    assert "warning_missing_comma_fail.png" in dashboard.text
    assert f"/jobs/{job_id}/items/{item_id}" in dashboard.text
    assert "Ready to reject" in dashboard.text or "Rejection review" in dashboard.text


def test_photo_intake_upload_extracts_candidate_fields():
    client = TestClient(app)
    response = client.post(
        "/photo-intake",
        files={"label_images": ("clean_malt_pass.png", DEMO_FIXTURE.read_bytes(), "image/png")},
        data={"parse_mode": "current", "selected_index": "0"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Photo OCR Intake" in response.text
    assert "Uploaded Photo" in response.text
    assert "Demonstration Only" in response.text
    assert "OLD RIVER BREWING" in response.text
    assert "5% ALC/VOL" in response.text
    assert "fixture ground truth" in response.text


def test_photo_intake_parse_all_supports_navigation():
    client = TestClient(app)
    response = client.post(
        "/photo-intake",
        files=[
            ("label_images", ("clean_malt_pass.png", DEMO_FIXTURE.read_bytes(), "image/png")),
            ("label_images", ("abv_prohibited_fail.png", (FIXTURE_DIR / "abv_prohibited_fail.png").read_bytes(), "image/png")),
        ],
        data={"parse_mode": "all", "selected_index": "0"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Photo 1 of 2" in response.text
    assert "Next Photo" in response.text


def test_cola_cloud_demo_renders_side_by_side_comparison(monkeypatch):
    from app.routes import jobs

    panel = ColaCloudPanel(
        panel_order=1,
        filename="clean_malt_pass.png",
        image_type="front",
        image_path=DEMO_FIXTURE,
    )
    source = ColaCloudDemoSource(
        dataset_name="unit-corpus",
        dataset_root=DEMO_FIXTURE.parent,
        ttb_id="TEST123",
        parsed={
            "source_url": "https://example.test/public-cola",
            "form_fields": {"status": "approved", "source_of_product": "domestic"},
            "application": {
                "fixture_id": "TEST123",
                "filename": "TEST123.json",
                "product_type": "malt_beverage",
                "brand_name": "OLD RIVER BREWING",
                "fanciful_name": "",
                "class_type": "Ale",
                "alcohol_content": "5% ALC/VOL",
                "net_contents": "1 Pint",
                "country_of_origin": None,
                "imported": False,
            },
        },
        panels=[panel],
    )
    ocr = OCRResult(
        fixture_id="TEST123",
        filename="clean_malt_pass.png",
        full_text="OLD RIVER BREWING ALE 5% ALC/VOL NET CONTENTS 1 Pint",
        avg_confidence=0.98,
        source="unit cached OCR",
        total_ms=12,
    )

    monkeypatch.setattr(jobs, "load_cola_cloud_demo_source", lambda ttb_id=None: source)
    monkeypatch.setattr(jobs, "load_cached_conveyor_ocr", lambda image_path: ocr)

    client = TestClient(app)
    response = client.get("/cola-cloud-demo", follow_redirects=True)

    assert response.status_code == 200
    assert "Public COLA Field Comparison" in response.text
    assert "TTB ID TEST123" in response.text
    assert "OLD RIVER BREWING" in response.text
    assert "unit cached OCR" in response.text
    assert "Side-by-Side Field Support" in response.text

    job_id = str(response.url).rstrip("/").split("/")[-1]
    image_response = client.get(f"/cola-cloud-demo/{job_id}/images/clean_malt_pass.png")
    assert image_response.status_code == 200


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
