"""Source-backed rule registry and verdict aggregation.

Notes
-----
The registry keeps implemented checks deterministic and auditable. Each helper
returns a ``RuleCheck`` with source references, evidence, expected/observed
values, and reviewer action text that can be shown directly in the UI.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.config import OCR_CONFIDENCE_THRESHOLD
from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from app.schemas.results import RuleCheck, VerificationResult
from app.services.rules.alcohol_terms import alcohol_values_match, contains_abv_shorthand, extract_alcohol_values
from app.services.rules.country_origin import country_match_score, find_conflicting_country
from app.services.rules.field_matching import fuzzy_score
from app.services.rules.net_contents import extract_net_content_values, has_bad_malt_16oz_statement, net_contents_match
from app.services.rules.strict_warning import (
    CANONICAL_WARNING,
    extract_warning_block,
    normalize_whitespace,
    warning_heading,
)


def check(
    rule_id: str,
    name: str,
    category: str,
    verdict: str,
    message: str,
    expected: str | None = None,
    observed: str | None = None,
    evidence_text: str | None = None,
    source_refs: list[str] | None = None,
    reviewer_action: str | None = None,
    score: float | None = None,
    confidence: float | None = None,
) -> RuleCheck:
    """Build a normalized rule-check object.

    Parameters
    ----------
    rule_id, name, category:
        Stable rule metadata used by UI, tests, and source maps.
    verdict:
        ``pass``, ``needs_review``, or ``fail``.
    message:
        Reviewer-facing explanation.

    Returns
    -------
    RuleCheck
        Structured rule result.
    """

    return RuleCheck(
        rule_id=rule_id,
        name=name,
        category=category,
        verdict=verdict,
        expected=expected,
        observed=observed,
        evidence_text=evidence_text,
        source_refs=source_refs or [],
        message=message,
        reviewer_action=reviewer_action,
        score=score,
        confidence=confidence,
    )


def verify_label(
    job_id: str,
    item_id: str,
    application: ColaApplication,
    ocr: OCRResult,
    typography: dict[str, Any] | None = None,
    review_unknown_government_warning: bool = False,
    require_review_before_rejection: bool = False,
    require_review_before_acceptance: bool = False,
) -> VerificationResult:
    """Run all implemented checks for one label.

    Parameters
    ----------
    job_id:
        Filesystem job identifier.
    item_id:
        Per-job item identifier.
    application:
        Structured application fields.
    ocr:
        Normalized OCR output from fixture OCR or local docTR.
    typography:
        Optional warning-heading typography assessment. When present, the rule
        engine can clear confident boldness evidence or route it to review.

    Returns
    -------
    VerificationResult
        Aggregated label verdict, checked/triggered rule IDs, rule checks, OCR
        payload, and timing.

    Notes
    -----
    Low OCR confidence suppresses deterministic text-failure checks and routes
    the item to Needs Review. This avoids unsupported false failures from poor
    image evidence.
    """

    started = perf_counter()
    checks: list[RuleCheck] = []
    text = ocr.full_text or ""
    low_confidence = ocr.avg_confidence < OCR_CONFIDENCE_THRESHOLD

    if low_confidence:
        checks.append(
            check(
                "OCR_LOW_CONFIDENCE",
                "OCR confidence requires human review",
                "ocr_quality",
                "needs_review",
                "OCR confidence is below the threshold for deterministic review.",
                expected=f">= {OCR_CONFIDENCE_THRESHOLD:.2f}",
                observed=f"{ocr.avg_confidence:.2f}",
                evidence_text=text[:500],
                source_refs=["SRC_STAKEHOLDER_DISCOVERY", "SRC_REPORT_14_HARDENING"],
                reviewer_action="Review the label image manually or request a clearer image.",
                confidence=ocr.avg_confidence,
            )
        )
        checks.append(
            check_warning_boldness(typography, text, ocr.avg_confidence)
        )
    else:
        warning = extract_warning_block(text)
        checks.append(check_warning_caps(text))
        checks.append(check_warning_exact(warning))
        if typography is not None:
            checks.append(check_warning_boldness(typography, text, ocr.avg_confidence))
        checks.append(check_abv(text))
        checks.append(check_alcohol_content_match(application, text, ocr.avg_confidence))
        checks.append(check_malt_net_contents(application, text))
        checks.append(check_net_contents_match(application, text, ocr.avg_confidence))
        checks.append(check_brand(application, text, ocr.avg_confidence))
        checks.append(check_optional_fuzzy_field(
            "FORM_FANCIFUL_NAME_MATCHES_LABEL",
            "Application fanciful name matches label artwork",
            "fuzzy_match",
            "Fanciful name",
            application.fanciful_name,
            text,
            ocr.avg_confidence,
        ))
        checks.append(check_optional_fuzzy_field(
            "FORM_CLASS_TYPE_MATCHES_LABEL",
            "Application class/type matches label artwork",
            "fuzzy_match",
            "Class/type designation",
            application.class_type,
            text,
            ocr.avg_confidence,
        ))
        checks.append(check_optional_fuzzy_field(
            "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL",
            "Bottler/producer name and address match label artwork",
            "fuzzy_match",
            "Bottler/producer name and address",
            application.bottler_producer_name_address,
            text,
            ocr.avg_confidence,
        ))
    checks.append(check_country_origin(application, text, ocr.avg_confidence))

    overall = overall_verdict(checks)
    policy_queue = policy_queue_for_checks(
        checks,
        overall,
        review_unknown_government_warning=review_unknown_government_warning,
        require_review_before_rejection=require_review_before_rejection,
        require_review_before_acceptance=require_review_before_acceptance,
    )
    triggered = [item.rule_id for item in checks if item.verdict in {"fail", "needs_review"}]
    checked = [item.rule_id for item in checks]
    top_reason = next(
        (item.message for item in checks if item.verdict == "fail"),
        next((item.message for item in checks if item.verdict == "needs_review"), "All implemented checks passed."),
    )
    elapsed = int((perf_counter() - started) * 1000) + ocr.total_ms
    ocr_payload = ocr.model_dump() if hasattr(ocr, "model_dump") else ocr.dict()
    app_payload = application.model_dump() if hasattr(application, "model_dump") else application.dict()

    return VerificationResult(
        job_id=job_id,
        item_id=item_id,
        filename=application.filename,
        application=app_payload,
        overall_verdict=overall,
        raw_verdict=overall,
        policy_queue=policy_queue,
        top_reason=top_reason,
        checked_rule_ids=checked,
        triggered_rule_ids=triggered,
        checks=checks,
        ocr=ocr_payload,
        processing_ms=elapsed,
    )


def check_warning_exact(warning: str | None) -> RuleCheck:
    """Check government warning text against the canonical wording.

    Notes
    -----
    Only whitespace is normalized. Punctuation and capitalization remain
    material for this strict check.
    """

    if not warning:
        return check(
            "GOV_WARNING_EXACT_TEXT",
            "Government warning exact text",
            "strict_compliance",
            "needs_review",
            "Government warning block could not be isolated reliably.",
            expected=CANONICAL_WARNING,
            observed=None,
            source_refs=["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
            reviewer_action="Review the label warning manually.",
        )
    expected = normalize_whitespace(CANONICAL_WARNING)
    observed = normalize_whitespace(warning)
    verdict = "pass" if observed == expected else "fail"
    return check(
        "GOV_WARNING_EXACT_TEXT",
        "Government warning exact text",
        "strict_compliance",
        verdict,
        "Government warning text matches the required wording."
        if verdict == "pass"
        else "Government warning text does not match the canonical wording.",
        expected=expected,
        observed=observed,
        evidence_text=observed,
        source_refs=["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
        reviewer_action=None if verdict == "pass" else "Correct the warning text and punctuation.",
    )


def check_warning_caps(text: str) -> RuleCheck:
    """Check that the warning heading is exactly ``GOVERNMENT WARNING:``."""

    heading = warning_heading(text)
    verdict = "pass" if heading == "GOVERNMENT WARNING:" else "fail"
    return check(
        "GOV_WARNING_HEADER_CAPS",
        "Government warning heading capitalization",
        "strict_compliance",
        verdict,
        "Government warning heading is all caps."
        if verdict == "pass"
        else "Government warning heading is not in the required all-caps form.",
        expected="GOVERNMENT WARNING:",
        observed=heading,
        evidence_text=heading,
        source_refs=["SRC_27_CFR_PART_16"],
        reviewer_action=None if verdict == "pass" else "Change the warning heading to GOVERNMENT WARNING:",
    )


def check_warning_boldness(
    typography: dict[str, Any] | None,
    text: str,
    confidence: float,
) -> RuleCheck:
    """Check whether the warning heading is confidently bold.

    Notes
    -----
    The typography model is a low-latency preflight. It clears strong bold
    evidence and routes uncertain crops to Needs Review; it does not issue an
    automatic fail from one raster crop.
    """

    if typography and typography.get("verdict") == "pass":
        probability = typography.get("probability")
        threshold = typography.get("threshold")
        return check(
            "GOV_WARNING_HEADER_BOLD_REVIEW",
            "Government warning heading boldness",
            "cv_typography",
            "pass",
            "Government warning heading is confidently classified as bold.",
            expected="Bold GOVERNMENT WARNING heading",
            observed=f"bold_probability={probability}; threshold={threshold}",
            evidence_text=typography.get("matched_text") or warning_heading(text) or "",
            source_refs=["SRC_27_CFR_PART_16"],
            reviewer_action=None,
            score=probability,
            confidence=confidence,
        )

    observed = "Raster image typography not machine-certified"
    if typography:
        observed = (
            f"bold_probability={typography.get('probability')}; "
            f"threshold={typography.get('threshold')}; "
            f"crop_available={typography.get('crop_available')}"
        )
    return check(
        "GOV_WARNING_HEADER_BOLD_REVIEW",
        "Government warning heading boldness manual review",
        "cv_typography",
        "needs_review",
        "Manual typography verification required. The warning heading was not confidently cleared as bold.",
        expected="Bold GOVERNMENT WARNING heading",
        observed=observed,
        evidence_text=(typography or {}).get("matched_text") or warning_heading(text) or "",
        source_refs=["SRC_27_CFR_PART_16"],
        reviewer_action="Confirm the warning heading is bold before clearing this application.",
        score=(typography or {}).get("probability"),
        confidence=confidence,
    )


def check_abv(text: str) -> RuleCheck:
    """Fail when prohibited ABV shorthand appears near an alcohol percentage."""

    observed = contains_abv_shorthand(text)
    verdict = "fail" if observed else "pass"
    return check(
        "ALCOHOL_ABV_PROHIBITED",
        "Prohibited ABV abbreviation detected",
        "strict_compliance",
        verdict,
        "Alcohol-content shorthand ABV detected."
        if verdict == "fail"
        else "No prohibited ABV shorthand detected.",
        expected="Use ALC/VOL or Alcohol by Volume wording where applicable.",
        observed=observed,
        evidence_text=observed,
        source_refs=["SRC_27_CFR_PART_7"],
        reviewer_action=None if verdict == "pass" else "Replace ABV shorthand with acceptable alcohol-content wording.",
    )


def check_malt_net_contents(application: ColaApplication, text: str) -> RuleCheck:
    """Apply the malt beverage 16-ounce net-contents check."""

    applies = application.product_type == "malt_beverage"
    bad_statement = has_bad_malt_16oz_statement(text) if applies else False
    verdict = "fail" if bad_statement else "pass"
    return check(
        "MALT_NET_CONTENTS_16OZ_PINT",
        "Malt beverage 16 fl. oz. should be 1 Pint",
        "strict_compliance",
        verdict,
        "Malt beverage net contents use 16 fl. oz. where 1 Pint is expected."
        if verdict == "fail"
        else "No malt 16 fl. oz. net-contents issue detected.",
        expected="1 Pint",
        observed="16 fl. oz." if bad_statement else application.net_contents,
        evidence_text=text,
        source_refs=["SRC_27_CFR_PART_7"],
        reviewer_action=None if verdict == "pass" else "Express the net contents as 1 Pint.",
    )


def check_alcohol_content_match(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
    """Compare application alcohol content against OCR label evidence."""

    expected_text = (application.alcohol_content or "").strip()
    if not expected_text:
        return check(
            "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
            "Application alcohol content matches label artwork",
            "numeric_match",
            "pass",
            "Alcohol-content comparison skipped because no application value was provided.",
            expected="Application alcohol content when provided",
            observed="No application alcohol content",
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            confidence=confidence,
        )

    expected_values = extract_alcohol_values(expected_text)
    observed_values = extract_alcohol_values(text)
    if not expected_values:
        return check(
            "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
            "Application alcohol content matches label artwork",
            "numeric_match",
            "needs_review",
            "Application alcohol content could not be parsed for automated comparison.",
            expected=expected_text,
            observed="No parseable application alcohol value",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Review the alcohol-content application field and label manually.",
            confidence=confidence,
        )
    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return check(
            "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
            "Application alcohol content matches label artwork",
            "numeric_match",
            "needs_review",
            "OCR confidence is too low to verify the alcohol-content statement.",
            expected=expected_text,
            observed=f"OCR confidence {confidence:.2f}",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Review the alcohol-content statement manually.",
            confidence=confidence,
        )
    if alcohol_values_match(expected_values, observed_values):
        return check(
            "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
            "Application alcohol content matches label artwork",
            "numeric_match",
            "pass",
            "Alcohol-content value appears to match the application field.",
            expected=expected_text,
            observed=", ".join(f"{value:g}% ABV" for value in sorted(observed_values)),
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            confidence=confidence,
        )
    if observed_values:
        return check(
            "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
            "Application alcohol content matches label artwork",
            "numeric_match",
            "fail",
            "Alcohol-content value on the label does not match the application field.",
            expected=expected_text,
            observed=", ".join(f"{value:g}% ABV" for value in sorted(observed_values)),
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Correct the application alcohol content or the label artwork.",
            confidence=confidence,
        )
    return check(
        "FORM_ALCOHOL_CONTENT_MATCHES_LABEL",
        "Application alcohol content matches label artwork",
        "numeric_match",
        "needs_review",
        "No clear alcohol-content value was found in OCR text.",
        expected=expected_text,
        observed="No label alcohol-content value found",
        evidence_text=text,
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        reviewer_action="Review the label alcohol-content statement manually.",
        confidence=confidence,
    )


def check_net_contents_match(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
    """Compare application net contents against OCR label evidence."""

    expected_text = (application.net_contents or "").strip()
    if not expected_text:
        return check(
            "FORM_NET_CONTENTS_MATCHES_LABEL",
            "Application net contents match label artwork",
            "numeric_match",
            "pass",
            "Net-contents comparison skipped because no application value was provided.",
            expected="Application net contents when provided",
            observed="No application net contents",
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            confidence=confidence,
        )
    expected_values = extract_net_content_values(expected_text)
    observed_values = extract_net_content_values(text)
    if not expected_values:
        return check(
            "FORM_NET_CONTENTS_MATCHES_LABEL",
            "Application net contents match label artwork",
            "numeric_match",
            "needs_review",
            "Application net contents could not be parsed for automated comparison.",
            expected=expected_text,
            observed="No parseable application net contents",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Review the net-contents application field and label manually.",
            confidence=confidence,
        )
    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return check(
            "FORM_NET_CONTENTS_MATCHES_LABEL",
            "Application net contents match label artwork",
            "numeric_match",
            "needs_review",
            "OCR confidence is too low to verify the net-contents statement.",
            expected=expected_text,
            observed=f"OCR confidence {confidence:.2f}",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Review the net-contents statement manually.",
            confidence=confidence,
        )
    if net_contents_match(expected_values, observed_values):
        return check(
            "FORM_NET_CONTENTS_MATCHES_LABEL",
            "Application net contents match label artwork",
            "numeric_match",
            "pass",
            "Net-contents value appears to match the application field.",
            expected=expected_text,
            observed=", ".join(evidence for _, evidence in observed_values),
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            confidence=confidence,
        )
    if observed_values:
        return check(
            "FORM_NET_CONTENTS_MATCHES_LABEL",
            "Application net contents match label artwork",
            "numeric_match",
            "fail",
            "Net-contents value on the label does not match the application field.",
            expected=expected_text,
            observed=", ".join(evidence for _, evidence in observed_values),
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Correct the application net contents or the label artwork.",
            confidence=confidence,
        )
    return check(
        "FORM_NET_CONTENTS_MATCHES_LABEL",
        "Application net contents match label artwork",
        "numeric_match",
        "needs_review",
        "No clear net-contents value was found in OCR text.",
        expected=expected_text,
        observed="No label net-contents value found",
        evidence_text=text,
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        reviewer_action="Review the label net-contents statement manually.",
        confidence=confidence,
    )


def check_brand(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
    """Fuzzy-match application brand name against OCR text.

    Notes
    -----
    Strong fuzzy matches pass, ambiguous matches route to Needs Review, and
    clear mismatches fail when OCR confidence is adequate.
    """

    score = fuzzy_score(application.brand_name, text)
    if score >= 90:
        verdict = "pass"
        message = "Brand name appears to match the application field."
        action = None
    elif score >= 75 or confidence < OCR_CONFIDENCE_THRESHOLD:
        verdict = "needs_review"
        message = "Brand name match is ambiguous."
        action = "Review the brand field and label artwork manually."
    else:
        verdict = "fail"
        message = "Brand name on label does not clearly match application field."
        action = "Correct the application field or label artwork."
    return check(
        "FORM_BRAND_MATCHES_LABEL",
        "Application brand name matches label artwork",
        "fuzzy_match",
        verdict,
        message,
        expected=application.brand_name,
        observed="OCR text window",
        evidence_text=text,
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        reviewer_action=action,
        score=score,
        confidence=confidence,
    )


def check_optional_fuzzy_field(
    rule_id: str,
    name: str,
    category: str,
    field_label: str,
    expected: str,
    text: str,
    confidence: float,
) -> RuleCheck:
    """Fuzzy-match an optional application field against OCR text."""

    expected = (expected or "").strip()
    if not expected:
        return check(
            rule_id,
            name,
            category,
            "pass",
            f"{field_label} comparison skipped because no application value was provided.",
            expected=f"{field_label} when provided",
            observed=f"No application {field_label.lower()}",
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            confidence=confidence,
        )

    score = fuzzy_score(expected, text)
    if score >= 90:
        verdict = "pass"
        message = f"{field_label} appears to match the application field."
        action = None
    elif score >= 75 or confidence < OCR_CONFIDENCE_THRESHOLD:
        verdict = "needs_review"
        message = f"{field_label} match is ambiguous."
        action = f"Review the {field_label.lower()} field and label artwork manually."
    else:
        verdict = "fail"
        message = f"{field_label} on label does not clearly match application field."
        action = f"Correct the application {field_label.lower()} or label artwork."
    return check(
        rule_id,
        name,
        category,
        verdict,
        message,
        expected=expected,
        observed="OCR text window",
        evidence_text=text,
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        reviewer_action=action,
        score=score,
        confidence=confidence,
    )


def check_country_origin(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
    """Evaluate imported-product country-of-origin consistency.

    Notes
    -----
    Domestic/non-imported labels pass this check as non-applicable. Imported
    labels pass on a strong expected-country match, need review when data or OCR
    is insufficient, and fail only when a conflicting country is detected with
    adequate confidence.
    """

    if not application.imported:
        return check(
            "COUNTRY_OF_ORIGIN_MATCH",
            "Country of origin matches imported application field",
            "field_matching",
            "pass",
            "Country-of-origin check skipped because the application is not marked imported.",
            expected="Imported product origin statement when imported is true",
            observed="Application marked domestic/not imported",
            evidence_text=None,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action=None,
            confidence=confidence,
        )

    expected = (application.country_of_origin or "").strip()
    if not expected:
        return check(
            "COUNTRY_OF_ORIGIN_MATCH",
            "Country of origin matches imported application field",
            "field_matching",
            "needs_review",
            "Imported product is missing a country-of-origin application field.",
            expected="Declared country of origin",
            observed="Blank application country_of_origin",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Enter the expected country of origin or review the label manually.",
            confidence=confidence,
        )

    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return check(
            "COUNTRY_OF_ORIGIN_MATCH",
            "Country of origin matches imported application field",
            "field_matching",
            "needs_review",
            "OCR confidence is too low to verify the country-of-origin statement.",
            expected=expected,
            observed=f"OCR confidence {confidence:.2f}",
            evidence_text=text[:500],
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Review the country-of-origin statement manually.",
            confidence=confidence,
        )

    score = country_match_score(expected, text)
    if score >= 90:
        return check(
            "COUNTRY_OF_ORIGIN_MATCH",
            "Country of origin matches imported application field",
            "field_matching",
            "pass",
            "Country-of-origin statement appears to match the application field.",
            expected=expected,
            observed="Country found in OCR text",
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            score=score,
            confidence=confidence,
        )

    conflict = find_conflicting_country(expected, text)
    if conflict:
        return check(
            "COUNTRY_OF_ORIGIN_MATCH",
            "Country of origin matches imported application field",
            "field_matching",
            "fail",
            "A conflicting country-of-origin statement appears on the label.",
            expected=expected,
            observed=conflict,
            evidence_text=text,
            source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            reviewer_action="Correct the label origin statement or the application country-of-origin field.",
            score=score,
            confidence=confidence,
        )

    return check(
        "COUNTRY_OF_ORIGIN_MATCH",
        "Country of origin matches imported application field",
        "field_matching",
        "needs_review",
        "Expected country of origin was not found with enough confidence.",
        expected=expected,
        observed="No clear country-of-origin match in OCR text",
        evidence_text=text,
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        reviewer_action="Review the imported product origin statement manually.",
        score=score,
        confidence=confidence,
    )


def overall_verdict(checks: list[RuleCheck]) -> str:
    """Collapse rule-check verdicts into the final item verdict."""

    if any(item.verdict == "fail" for item in checks):
        return "fail"
    if any(item.verdict == "needs_review" for item in checks):
        return "needs_review"
    return "pass"


def policy_queue_for_checks(
    checks: list[RuleCheck],
    raw_verdict: str,
    *,
    review_unknown_government_warning: bool = False,
    require_review_before_rejection: bool = False,
    require_review_before_acceptance: bool = False,
) -> str:
    """Map a raw verdict into the default reviewer workflow queue.

    Notes
    -----
    The defaults preserve Sarah's high-volume batch value: clear passes and
    clear fails are ready for action, while ordinary uncertainty goes to manual
    evidence review. Unknown mandatory warning evidence is special. If the
    warning-review gate is off, it routes to the rejection path because the
    applicant must provide readable evidence of the mandatory warning.
    """

    warning_unknown = any(
        check.verdict == "needs_review"
        and check.rule_id in {
            "GOV_WARNING_EXACT_TEXT",
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_HEADER_BOLD_REVIEW",
        }
        for check in checks
    )
    if warning_unknown:
        if review_unknown_government_warning:
            return "manual_evidence_review"
        return "rejection_review" if require_review_before_rejection else "ready_to_reject"

    if raw_verdict == "pass":
        return "acceptance_review" if require_review_before_acceptance else "ready_to_accept"
    if raw_verdict == "fail":
        return "rejection_review" if require_review_before_rejection else "ready_to_reject"
    return "manual_evidence_review"
