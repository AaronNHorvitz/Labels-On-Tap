from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from app.services.rules.registry import verify_label
from app.services.rules.strict_warning import CANONICAL_WARNING


def make_ocr(text: str, confidence: float = 0.98) -> OCRResult:
    return OCRResult(
        filename="field-match.png",
        full_text=f"{text}\n{CANONICAL_WARNING}",
        avg_confidence=confidence,
        blocks=[],
        source="unit OCR",
    )


def base_application(**overrides) -> ColaApplication:
    payload = {
        "filename": "field-match.png",
        "product_type": "distilled_spirits",
        "brand_name": "OLD TOM DISTILLERY",
        "fanciful_name": "BARREL RESERVE",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "bottler_producer_name_address": "Old Tom Distillery Louisville Kentucky",
    }
    payload.update(overrides)
    return ColaApplication(**payload)


def test_core_application_fields_pass_when_label_supports_them():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 90 Proof 750 mL Produced and bottled by Old Tom Distillery Louisville Kentucky"
        ),
    )

    assert result.overall_verdict == "pass"
    for rule_id in {
        "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
        "FORM_NET_CONTENTS_MATCHES_LABEL",
        "FORM_FANCIFUL_NAME_MATCHES_LABEL",
        "FORM_CLASS_TYPE_MATCHES_LABEL",
        "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL",
    }:
        check = next(item for item in result.checks if item.rule_id == rule_id)
        assert check.verdict == "pass"


def test_alcohol_content_mismatch_fails_when_label_has_conflicting_value():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(alcohol_content="45% Alc./Vol."),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "40% Alc./Vol. 750 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
    )

    assert result.overall_verdict == "fail"
    assert "FORM_ALCOHOL_CONTENT_MATCHES_LABEL" in result.triggered_rule_ids


def test_net_contents_mismatch_fails_when_label_has_conflicting_value():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(net_contents="750 mL"),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 700 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
    )

    assert result.overall_verdict == "fail"
    assert "FORM_NET_CONTENTS_MATCHES_LABEL" in result.triggered_rule_ids


def test_fuzzy_class_and_bottler_mismatches_fail_when_ocr_is_clear():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(
            class_type="Kentucky Straight Bourbon Whiskey",
            bottler_producer_name_address="Old Tom Distillery Louisville Kentucky",
        ),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Vodka 45% Alc./Vol. 750 mL "
            "Produced by River Road Spirits Nashville Tennessee"
        ),
    )

    assert result.overall_verdict == "fail"
    assert "FORM_CLASS_TYPE_MATCHES_LABEL" in result.triggered_rule_ids
    assert "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL" in result.triggered_rule_ids


def test_optional_blank_fields_are_checked_but_do_not_fail():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(
            fanciful_name="",
            class_type="",
            bottler_producer_name_address="",
        ),
        make_ocr("OLD TOM DISTILLERY 45% Alc./Vol. 750 mL"),
    )

    assert "FORM_FANCIFUL_NAME_MATCHES_LABEL" in result.checked_rule_ids
    assert "FORM_CLASS_TYPE_MATCHES_LABEL" in result.checked_rule_ids
    assert "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL" in result.checked_rule_ids
    assert "FORM_FANCIFUL_NAME_MATCHES_LABEL" not in result.triggered_rule_ids
    assert "FORM_CLASS_TYPE_MATCHES_LABEL" not in result.triggered_rule_ids
    assert "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL" not in result.triggered_rule_ids


def test_fanciful_name_mismatch_fails_when_ocr_is_clear():
    result = verify_label(
        "test-job",
        "field-match",
        base_application(fanciful_name="BARREL RESERVE"),
        make_ocr(
            "OLD TOM DISTILLERY SINGLE BARREL Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 750 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
    )

    assert result.overall_verdict == "fail"
    assert "FORM_FANCIFUL_NAME_MATCHES_LABEL" in result.triggered_rule_ids


def test_policy_queue_routes_pass_fail_and_review_defaults():
    passing = verify_label(
        "test-job",
        "field-match",
        base_application(),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 750 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
    )
    failing = verify_label(
        "test-job",
        "field-match",
        base_application(alcohol_content="45% Alc./Vol."),
        make_ocr("OLD TOM DISTILLERY 40% Alc./Vol. 750 mL"),
    )
    needs_review = verify_label(
        "test-job",
        "field-match",
        base_application(imported=True, country_of_origin="France"),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 750 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
    )

    assert passing.policy_queue == "ready_to_accept"
    assert failing.policy_queue == "ready_to_reject"
    assert needs_review.policy_queue == "manual_evidence_review"


def test_policy_queue_respects_review_toggles():
    passing = verify_label(
        "test-job",
        "field-match",
        base_application(),
        make_ocr(
            "OLD TOM DISTILLERY BARREL RESERVE Kentucky Straight Bourbon Whiskey "
            "45% Alc./Vol. 750 mL Produced by Old Tom Distillery Louisville Kentucky"
        ),
        require_review_before_acceptance=True,
    )
    failing = verify_label(
        "test-job",
        "field-match",
        base_application(alcohol_content="45% Alc./Vol."),
        make_ocr("OLD TOM DISTILLERY 40% Alc./Vol. 750 mL"),
        require_review_before_rejection=True,
    )
    warning_unknown = verify_label(
        "test-job",
        "field-match",
        base_application(),
        make_ocr("OLD TOM DISTILLERY 45% Alc./Vol. 750 mL", confidence=0.4),
        review_unknown_government_warning=True,
    )

    assert passing.policy_queue == "acceptance_review"
    assert failing.policy_queue == "rejection_review"
    assert warning_unknown.policy_queue == "manual_evidence_review"
