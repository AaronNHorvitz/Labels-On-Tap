from app.services.fixture_loader import DEMO_SCENARIOS, load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def test_all_demo_scenarios_are_declared():
    assert set(DEMO_SCENARIOS) == {"clean", "warning", "abv", "net_contents", "country_origin", "batch"}


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


def test_imported_country_origin_fixture_passes():
    result = verify_label(
        "test-job",
        "imported_country_origin_pass",
        load_application("imported_country_origin_pass"),
        load_fixture_ocr("imported_country_origin_pass"),
    )
    assert result.overall_verdict == "pass"
    assert "COUNTRY_OF_ORIGIN_MATCH" in result.checked_rule_ids
    assert "COUNTRY_OF_ORIGIN_MATCH" not in result.triggered_rule_ids


def test_brand_mismatch_fixture_fails():
    result = verify_label(
        "test-job",
        "brand_mismatch_fail",
        load_application("brand_mismatch_fail"),
        load_fixture_ocr("brand_mismatch_fail"),
    )
    assert result.overall_verdict == "fail"
    assert "FORM_BRAND_MATCHES_LABEL" in result.triggered_rule_ids


def test_imported_missing_country_fixture_needs_review():
    result = verify_label(
        "test-job",
        "imported_missing_country_review",
        load_application("imported_missing_country_review"),
        load_fixture_ocr("imported_missing_country_review"),
    )
    assert result.overall_verdict == "needs_review"
    assert "COUNTRY_OF_ORIGIN_MATCH" in result.triggered_rule_ids


def test_conflicting_country_origin_fixture_fails():
    result = verify_label(
        "test-job",
        "conflicting_country_origin_fail",
        load_application("conflicting_country_origin_fail"),
        load_fixture_ocr("conflicting_country_origin_fail"),
    )
    assert result.overall_verdict == "fail"
    assert "COUNTRY_OF_ORIGIN_MATCH" in result.triggered_rule_ids


def test_warning_missing_block_fixture_needs_review():
    result = verify_label(
        "test-job",
        "warning_missing_block_review",
        load_application("warning_missing_block_review"),
        load_fixture_ocr("warning_missing_block_review"),
    )
    assert result.overall_verdict == "needs_review"
    assert "OCR_LOW_CONFIDENCE" in result.triggered_rule_ids
