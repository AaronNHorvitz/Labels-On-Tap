from __future__ import annotations

from time import perf_counter

from app.config import OCR_CONFIDENCE_THRESHOLD
from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from app.schemas.results import RuleCheck, VerificationResult
from app.services.rules.alcohol_terms import contains_abv_shorthand
from app.services.rules.country_origin import country_match_score, find_conflicting_country
from app.services.rules.field_matching import fuzzy_score
from app.services.rules.net_contents import has_bad_malt_16oz_statement
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
) -> VerificationResult:
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
            check(
                "GOV_WARNING_HEADER_BOLD_REVIEW",
                "Government warning heading boldness manual review",
                "cv_typography",
                "needs_review",
                "Manual typography verification required. This prototype verifies warning text and capitalization but does not make a definitive font-weight determination from raster images.",
                expected="Bold GOVERNMENT WARNING heading",
                observed="Raster image typography not machine-certified",
                evidence_text=warning_heading(text) or "",
                source_refs=["SRC_27_CFR_PART_16"],
                reviewer_action="Confirm the warning heading is bold during human review.",
                confidence=ocr.avg_confidence,
            )
        )
    else:
        warning = extract_warning_block(text)
        checks.append(check_warning_caps(text))
        checks.append(check_warning_exact(warning))
        checks.append(check_abv(text))
        checks.append(check_malt_net_contents(application, text))
        checks.append(check_brand(application, text, ocr.avg_confidence))
    checks.append(check_country_origin(application, text, ocr.avg_confidence))

    overall = overall_verdict(checks)
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
        top_reason=top_reason,
        checked_rule_ids=checked,
        triggered_rule_ids=triggered,
        checks=checks,
        ocr=ocr_payload,
        processing_ms=elapsed,
    )


def check_warning_exact(warning: str | None) -> RuleCheck:
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


def check_abv(text: str) -> RuleCheck:
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


def check_brand(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
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


def check_country_origin(application: ColaApplication, text: str, confidence: float) -> RuleCheck:
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
    if any(item.verdict == "fail" for item in checks):
        return "fail"
    if any(item.verdict == "needs_review" for item in checks):
        return "needs_review"
    return "pass"
