from app.services.fixture_loader import load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def test_abv_fixture_fails_abv_rule():
    result = verify_label(
        "test-job",
        "abv_prohibited_fail",
        load_application("abv_prohibited_fail"),
        load_fixture_ocr("abv_prohibited_fail"),
    )
    assert result.overall_verdict == "fail"
    assert "ALCOHOL_ABV_PROHIBITED" in result.triggered_rule_ids
