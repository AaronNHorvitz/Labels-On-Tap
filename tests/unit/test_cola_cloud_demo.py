from app.schemas.ocr import OCRResult
from app.services.cola_cloud_demo import ColaCloudPanel, build_comparison_payload, compare_field, expected_fields


def test_compare_field_marks_supported_application_value_pass(tmp_path):
    panel = ColaCloudPanel(
        panel_order=1,
        filename="front.png",
        image_type="front",
        image_path=tmp_path / "front.png",
    )
    ocr = OCRResult(
        filename="front.png",
        full_text="OLD TENNESSEE DISTILLING CO HAPPY HOLIDAY NOG 17% ALC/VOL 750 mL",
        avg_confidence=0.9,
        source="unit-test",
    )

    result = compare_field("alcohol_content", "17% ALC/VOL", [(panel, ocr)])

    assert result["verdict"] == "pass"
    assert result["outcome"] == "matched"
    assert result["score"] >= 90
    assert result["best_panel"] == "front.png"


def test_build_comparison_payload_routes_missing_field_to_review(tmp_path):
    panel = ColaCloudPanel(
        panel_order=1,
        filename="front.png",
        image_type="front",
        image_path=tmp_path / "front.png",
    )
    ocr = OCRResult(
        filename="front.png",
        full_text="SOME OTHER TEXT 750 mL",
        avg_confidence=0.9,
        source="unit-test",
    )
    source = type(
        "Source",
        (),
        {
            "dataset_name": "unit",
            "ttb_id": "123",
            "parsed": {
                "ttb_id": "123",
                "form_fields": {"status": "approved", "source_of_product": "domestic"},
                "application": {
                    "product_type": "distilled_spirits",
                    "brand_name": "EXPECTED BRAND",
                    "class_type": "",
                    "alcohol_content": "",
                    "net_contents": "750 mL",
                    "country_of_origin": None,
                    "imported": False,
                },
            },
        },
    )()

    payload = build_comparison_payload(source=source, panel_ocrs=[(panel, ocr)])
    brand = next(field for field in payload["fields"] if field["field_name"] == "brand_name")
    net_contents = next(field for field in payload["fields"] if field["field_name"] == "net_contents")

    assert payload["overall_verdict"] == "needs_review"
    assert brand["verdict"] == "needs_review"
    assert net_contents["verdict"] == "pass"


def test_expected_fields_skip_permit_number_as_producer_name():
    parsed = {
        "form_fields": {
            "source_of_product": "domestic",
            "applicant_name_address": "DSP-TN-21017",
        },
        "application": {
            "brand_name": "Example Brand",
            "imported": False,
        },
    }

    fields = expected_fields(parsed)

    assert fields["applicant_or_producer"] == ""
