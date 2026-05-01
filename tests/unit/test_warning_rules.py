from app.services.fixture_loader import load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def verify_fixture(fixture_id: str):
    return verify_label("test-job", fixture_id, load_application(fixture_id), load_fixture_ocr(fixture_id))


def test_clean_malt_passes_warning_checks():
    result = verify_fixture("clean_malt_pass")
    assert result.overall_verdict == "pass"
    assert "GOV_WARNING_EXACT_TEXT" in result.checked_rule_ids
    assert not result.triggered_rule_ids


def test_warning_missing_comma_fails_exact_text():
    result = verify_fixture("warning_missing_comma_fail")
    assert result.overall_verdict == "fail"
    assert "GOV_WARNING_EXACT_TEXT" in result.triggered_rule_ids


def test_warning_title_case_fails_header_caps():
    result = verify_fixture("warning_title_case_fail")
    assert result.overall_verdict == "fail"
    assert "GOV_WARNING_HEADER_CAPS" in result.triggered_rule_ids
