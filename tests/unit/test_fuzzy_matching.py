from app.services.fixture_loader import load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def test_brand_case_difference_passes_fuzzy_match():
    result = verify_label(
        "test-job",
        "brand_case_difference_pass",
        load_application("brand_case_difference_pass"),
        load_fixture_ocr("brand_case_difference_pass"),
    )
    assert result.overall_verdict == "pass"
    assert "FORM_BRAND_MATCHES_LABEL" in result.checked_rule_ids
    assert "FORM_BRAND_MATCHES_LABEL" not in result.triggered_rule_ids
