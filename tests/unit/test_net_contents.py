from app.services.fixture_loader import load_application, load_fixture_ocr
from app.services.rules.registry import verify_label


def test_malt_16_fl_oz_fixture_fails_net_contents_rule():
    result = verify_label(
        "test-job",
        "malt_16_fl_oz_fail",
        load_application("malt_16_fl_oz_fail"),
        load_fixture_ocr("malt_16_fl_oz_fail"),
    )
    assert result.overall_verdict == "fail"
    assert "MALT_NET_CONTENTS_16OZ_PINT" in result.triggered_rule_ids
