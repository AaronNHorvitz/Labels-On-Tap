from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from app.services.rules.registry import verify_label
from app.services.rules.strict_warning import CANONICAL_WARNING


def make_ocr(text: str, confidence: float = 0.98) -> OCRResult:
    return OCRResult(
        filename="origin.png",
        full_text=f"{text}\n{CANONICAL_WARNING}",
        avg_confidence=confidence,
        blocks=[],
        source="test",
    )


def test_imported_missing_country_needs_review():
    result = verify_label(
        "test-job",
        "origin",
        ColaApplication(
            filename="origin.png",
            product_type="wine",
            brand_name="VALLEY RIDGE",
            imported=True,
            country_of_origin="",
        ),
        make_ocr("VALLEY RIDGE RED WINE PRODUCT OF FRANCE"),
    )
    assert result.overall_verdict == "needs_review"
    assert "COUNTRY_OF_ORIGIN_MATCH" in result.triggered_rule_ids


def test_non_imported_country_check_does_not_fail():
    result = verify_label(
        "test-job",
        "origin",
        ColaApplication(
            filename="origin.png",
            product_type="wine",
            brand_name="VALLEY RIDGE",
            imported=False,
        ),
        make_ocr("VALLEY RIDGE RED WINE"),
    )
    country_check = next(item for item in result.checks if item.rule_id == "COUNTRY_OF_ORIGIN_MATCH")
    assert country_check.verdict == "pass"
    assert "COUNTRY_OF_ORIGIN_MATCH" not in result.triggered_rule_ids


def test_imported_conflicting_country_fails():
    result = verify_label(
        "test-job",
        "origin",
        ColaApplication(
            filename="origin.png",
            product_type="wine",
            brand_name="VALLEY RIDGE",
            imported=True,
            country_of_origin="France",
        ),
        make_ocr("VALLEY RIDGE RED WINE PRODUCT OF ITALY"),
    )
    assert result.overall_verdict == "fail"
    assert "COUNTRY_OF_ORIGIN_MATCH" in result.triggered_rule_ids
