from app.services.fixture_loader import DEMO_SCENARIOS, load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def test_all_demo_scenarios_are_declared():
    assert set(DEMO_SCENARIOS) == {"clean", "warning", "abv", "net_contents", "batch"}


def test_low_confidence_fixture_needs_review():
    result = verify_label(
        "test-job",
        "low_confidence_blur_review",
        load_application("low_confidence_blur_review"),
        load_fixture_ocr("low_confidence_blur_review"),
    )
    assert result.overall_verdict == "needs_review"
    assert "OCR_LOW_CONFIDENCE" in result.triggered_rule_ids
    assert "GOV_WARNING_HEADER_BOLD_REVIEW" in result.triggered_rule_ids
