#!/usr/bin/env python3
"""
Bootstrap the Labels On Tap research/legal-corpus structure.

This script creates:
- research/legal-corpus/ directory hierarchy
- source-ledger JSON + Markdown
- source-backed criteria JSON + Markdown
- fixture provenance JSON + Markdown
- starter legal/regulatory index files
- report placeholders
- docs placeholders
- data fixture/source-map folders
- a validate_legal_corpus.py script

It is intentionally stdlib-only.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today().isoformat()


def write_text(path: Path, content: str, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"wrote: {path}")


def write_json(path: Path, obj: object, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote: {path}")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str], force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    print(f"wrote: {path}")


def mkdirs() -> None:
    dirs = [
        "research/legal-corpus",
        "research/legal-corpus/excerpts/statutes",
        "research/legal-corpus/excerpts/cfr",
        "research/legal-corpus/excerpts/ttb-guidance",
        "research/legal-corpus/excerpts/cases",
        "research/legal-corpus/excerpts/forms",
        "research/legal-corpus/matrices",
        "research/legal-corpus/forms",
        "research/legal-corpus/reports",
        "research/legal-corpus/snapshots",
        "research/legal-corpus/sources/official",
        "research/legal-corpus/sources/ttb",
        "research/legal-corpus/sources/cases",
        "research/legal-corpus/sources/secondary",
        "research/legal-corpus/sources/internal-research",
        "docs",
        "data/source-maps",
        "data/fixtures/approved-public",
        "data/fixtures/postmarket-public",
        "data/fixtures/synthetic",
        "data/fixtures/demo",
        "data/fixtures/manifests",
        "scripts",
    ]

    for d in dirs:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        gitkeep = path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    print("created directory structure")


def starter_sources() -> list[dict[str, object]]:
    return [
        {
            "source_id": "SRC_27_USC_205",
            "title": "27 U.S.C. § 205 — Federal Alcohol Administration Act labeling authority",
            "source_type": "federal_statute",
            "confidence_tier": "tier_1_official",
            "publisher": "U.S. Code",
            "url": "https://uscode.house.gov/",
            "retrieved_at": TODAY,
            "used_for": ["LABELING_AUTHORITY_CONTEXT", "MISLEADING_LABEL_RISK"],
            "notes": "FAA Act authority for labeling and misleading-statement regulation.",
        },
        {
            "source_id": "SRC_27_USC_215",
            "title": "27 U.S.C. § 215 — Alcoholic beverage health warning statement",
            "source_type": "federal_statute",
            "confidence_tier": "tier_1_official",
            "publisher": "U.S. Code",
            "url": "https://uscode.house.gov/",
            "retrieved_at": TODAY,
            "used_for": ["GOV_WARNING_PRESENT", "GOV_WARNING_EXACT_TEXT"],
            "notes": "Statutory basis for the mandatory government warning.",
        },
        {
            "source_id": "SRC_27_CFR_PART_4",
            "title": "27 CFR Part 4 — Labeling and Advertising of Wine",
            "source_type": "regulation",
            "confidence_tier": "tier_1_official_current_reference",
            "publisher": "eCFR",
            "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4",
            "retrieved_at": TODAY,
            "used_for": ["WINE_RULES", "WINE_APPELLATION_RISK", "WINE_ALCOHOL_TOLERANCE"],
            "notes": "Core wine labeling regulation.",
        },
        {
            "source_id": "SRC_27_CFR_PART_5",
            "title": "27 CFR Part 5 — Labeling and Advertising of Distilled Spirits",
            "source_type": "regulation",
            "confidence_tier": "tier_1_official_current_reference",
            "publisher": "eCFR",
            "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5",
            "retrieved_at": TODAY,
            "used_for": ["SPIRITS_RULES", "SPIRITS_CLASS_TYPE", "SPIRITS_ALCOHOL_CONTENT"],
            "notes": "Core distilled spirits labeling regulation.",
        },
        {
            "source_id": "SRC_27_CFR_PART_7",
            "title": "27 CFR Part 7 — Labeling and Advertising of Malt Beverages",
            "source_type": "regulation",
            "confidence_tier": "tier_1_official_current_reference",
            "publisher": "eCFR",
            "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7",
            "retrieved_at": TODAY,
            "used_for": ["MALT_RULES", "MALT_NET_CONTENTS", "MALT_ALCOHOL_CONTENT"],
            "notes": "Core malt beverage labeling regulation.",
        },
        {
            "source_id": "SRC_27_CFR_PART_13",
            "title": "27 CFR Part 13 — Labeling Proceedings",
            "source_type": "regulation",
            "confidence_tier": "tier_1_official_current_reference",
            "publisher": "eCFR",
            "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-13",
            "retrieved_at": TODAY,
            "used_for": ["PUBLIC_DATA_BOUNDARIES", "COLA_PROCEDURE", "CERTIFICATE_EXEMPTION_CONTEXT"],
            "notes": "COLA procedures and public/confidential data boundary context.",
        },
        {
            "source_id": "SRC_27_CFR_PART_16",
            "title": "27 CFR Part 16 — Alcoholic Beverage Health Warning Statement",
            "source_type": "regulation",
            "confidence_tier": "tier_1_official_current_reference",
            "publisher": "eCFR",
            "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16",
            "retrieved_at": TODAY,
            "used_for": [
                "GOV_WARNING_EXACT_TEXT",
                "GOV_WARNING_HEADER_CAPS",
                "GOV_WARNING_HEADER_BOLD_REVIEW",
                "GOV_WARNING_BODY_NOT_BOLD",
                "GOV_WARNING_LEGIBILITY",
            ],
            "notes": "Primary implementation source for government warning text and formatting.",
        },
        {
            "source_id": "SRC_TTB_FORM_5100_31",
            "title": "TTB Form 5100.31 — Application for and Certification/Exemption of Label/Bottle Approval",
            "source_type": "ttb_form",
            "confidence_tier": "tier_1_official",
            "publisher": "TTB",
            "url": "https://www.ttb.gov/system/files/images/pdfs/forms/f510031.pdf",
            "retrieved_at": TODAY,
            "used_for": [
                "FORM_FIELD_MAPPING",
                "APPLICATION_SCHEMA",
                "FORM_BRAND_MATCHES_LABEL",
                "COUNTRY_OF_ORIGIN_MATCH",
            ],
            "notes": "Primary form schema reference for expected application fields.",
        },
        {
            "source_id": "SRC_TTB_PUBLIC_COLA_REGISTRY",
            "title": "TTB Public COLA Registry",
            "source_type": "ttb_public_registry",
            "confidence_tier": "tier_1_official",
            "publisher": "TTB",
            "url": "https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry",
            "retrieved_at": TODAY,
            "used_for": ["PUBLIC_APPROVED_FIXTURES", "PUBLIC_POSTMARKET_FIXTURES"],
            "notes": "Public source for approved, expired, surrendered, and revoked COLA records.",
        },
        {
            "source_id": "SRC_TTB_IC_2006_01",
            "title": "TTB Industry Circular 2006-01 — Semi-generic wine names and Retsina",
            "source_type": "ttb_industry_circular",
            "confidence_tier": "tier_1_official",
            "publisher": "TTB",
            "url": "https://www.ttb.gov/public-information/industry-circulars/archives/2006/06-01",
            "retrieved_at": TODAY,
            "used_for": ["WINE_SEMI_GENERIC_NAME_DETECTED", "WINE_SEMI_GENERIC_SUPPORT_REQUIRED"],
            "notes": "Source for semi-generic wine name and Retsina handling.",
        },
        {
            "source_id": "SRC_TTB_IC_2007_05",
            "title": "TTB Industry Circular 2007-05 — Absinthe and thujone policy",
            "source_type": "ttb_industry_circular",
            "confidence_tier": "tier_1_official",
            "publisher": "TTB",
            "url": "https://www.ttb.gov/public-information/industry-circulars/archives/2007/07-05",
            "retrieved_at": TODAY,
            "used_for": ["ABSINTHE_TERM_DETECTED", "ABSINTHE_THUJONE_FREE_SUPPORT_REQUIRED"],
            "notes": "Source for absinthe/thujone support and risk checks.",
        },
        {
            "source_id": "SRC_STAKEHOLDER_DISCOVERY",
            "title": "Stakeholder discovery notes and take-home project brief",
            "source_type": "stakeholder_requirement",
            "confidence_tier": "stakeholder_requirement",
            "publisher": "Take-home brief",
            "url": "local_uploaded_project_brief",
            "retrieved_at": TODAY,
            "used_for": ["BATCH_PROGRESS_REQUIRED", "NO_CLOUD_ML_ENDPOINTS", "LATENCY_SLA", "UX_SIMPLICITY"],
            "notes": "Source for workflow, UX, latency, batch, and infrastructure constraints.",
        },
        {
            "source_id": "SRC_REPORT_09_SYNTHETIC_FIXTURES",
            "title": "Data Acquisition and Synthetic Fixture Generation Pipeline",
            "source_type": "internal_research_report",
            "confidence_tier": "tier_3_research_synthesis",
            "publisher": "Project research corpus",
            "url": "research/legal-corpus/reports/09-data-acquisition-synthetic-fixtures.md",
            "retrieved_at": TODAY,
            "used_for": ["SYNTHETIC_NEGATIVE_REQUIRED", "FIXTURE_MUTATION_TRACEABILITY"],
            "notes": "Supports lawful synthetic negative fixture strategy.",
        },
        {
            "source_id": "SRC_REPORT_14_HARDENING",
            "title": "Federal Prototype Hardening, Accessibility, and Evaluator Journey",
            "source_type": "internal_research_report",
            "confidence_tier": "tier_3_research_synthesis",
            "publisher": "Project research corpus",
            "url": "research/legal-corpus/reports/14-federal-hardening-accessibility.md",
            "retrieved_at": TODAY,
            "used_for": ["UPLOAD_EXTENSION_ALLOWLIST", "UPLOAD_MAGIC_BYTE_VALIDATION", "ACCESSIBILITY_BASELINE"],
            "notes": "Supports upload security and federal-style UX hardening.",
        },
    ]


def starter_criteria() -> list[dict[str, object]]:
    return [
        {
            "rule_id": "GOV_WARNING_EXACT_TEXT",
            "name": "Government warning exact text",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "strict_compliance",
            "confidence_tier": "tier_1_official",
            "default_verdict": "fail",
            "source_refs": ["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
            "requirement_summary": "The required government warning must match the canonical statutory wording.",
            "detection_method": "OCR warning-block extraction, whitespace-only normalization, and canonical string comparison.",
            "pass_condition": "Warning block equals canonical text after whitespace normalization.",
            "fail_condition": "Warning missing, altered wording, altered punctuation, or altered required capitalization.",
            "needs_review_condition": "OCR confidence is too low or warning block cannot be isolated.",
            "implemented_status": "planned",
            "app_module": "app/rules/strict_warning.py",
            "fixtures": ["warning_good.png", "warning_missing_machinery_comma.png", "warning_title_case_heading.png"],
            "ui_message": "Government warning text does not match the required wording.",
        },
        {
            "rule_id": "GOV_WARNING_HEADER_CAPS",
            "name": "Government warning heading capitalization",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "strict_compliance",
            "confidence_tier": "tier_1_official",
            "default_verdict": "fail",
            "source_refs": ["SRC_27_CFR_PART_16"],
            "requirement_summary": "The words GOVERNMENT WARNING must appear in capital letters.",
            "detection_method": "Regex/prefix check on isolated warning heading.",
            "pass_condition": "Heading begins with GOVERNMENT WARNING:",
            "fail_condition": "Heading appears as title case, lowercase, or otherwise altered.",
            "needs_review_condition": "OCR ambiguity prevents reliable heading extraction.",
            "implemented_status": "planned",
            "app_module": "app/rules/strict_warning.py",
            "fixtures": ["warning_title_case_heading.png"],
            "ui_message": "Government warning heading is not in the required all-caps form.",
        },
        {
            "rule_id": "GOV_WARNING_HEADER_BOLD_REVIEW",
            "name": "Government warning heading boldness manual review",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "cv_typography",
            "confidence_tier": "tier_1_official",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_27_CFR_PART_16"],
            "requirement_summary": "The GOVERNMENT WARNING heading must appear in bold type.",
            "detection_method": "Manual-review fallback for raster label images.",
            "pass_condition": "Not applicable in MVP.",
            "fail_condition": "",
            "needs_review_condition": "Font-weight cannot be definitively verified from arbitrary raster images.",
            "implemented_status": "implemented",
            "app_module": "app/services/rules/strict_warning.py",
            "fixtures": ["warning_not_bold.png", "warning_low_contrast.png"],
            "ui_message": "Government warning boldness could not be confirmed or appears incorrect.",
        },
        {
            "rule_id": "OCR_LOW_CONFIDENCE",
            "name": "OCR confidence requires human review",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "ocr_quality",
            "confidence_tier": "stakeholder_requirement",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_STAKEHOLDER_DISCOVERY", "SRC_REPORT_14_HARDENING"],
            "requirement_summary": "Low OCR confidence should route to human review rather than unsupported Pass/Fail certainty.",
            "detection_method": "Compare average OCR confidence to configured threshold.",
            "pass_condition": "Average OCR confidence is above threshold.",
            "fail_condition": "",
            "needs_review_condition": "Average OCR confidence is below threshold.",
            "implemented_status": "implemented",
            "app_module": "app/services/rules/registry.py",
            "fixtures": ["low_confidence_blur_review.png"],
            "ui_message": "OCR confidence is low. Human review required.",
        },
        {
            "rule_id": "ALCOHOL_ABV_PROHIBITED",
            "name": "Prohibited ABV abbreviation detected",
            "beverage_types": ["malt_beverage", "distilled_spirits"],
            "category": "strict_compliance",
            "confidence_tier": "tier_1_official",
            "default_verdict": "fail",
            "source_refs": ["SRC_27_CFR_PART_5", "SRC_27_CFR_PART_7"],
            "requirement_summary": "Alcohol content statements should use acceptable alcohol-by-volume wording/abbreviations, not ABV shorthand where prohibited.",
            "detection_method": "Regex scan for ABV or A.B.V. near alcohol percentage statements.",
            "pass_condition": "Acceptable wording such as ALC/VOL or Alcohol by Volume is present and ABV shorthand is absent.",
            "fail_condition": "ABV or A.B.V. appears in the label alcohol statement.",
            "needs_review_condition": "OCR confidence around the alcohol statement is low.",
            "implemented_status": "planned",
            "app_module": "app/rules/alcohol_terms.py",
            "fixtures": ["beer_5_percent_abv.png", "spirits_45_percent_abv.png"],
            "ui_message": "Prohibited alcohol-content abbreviation detected.",
        },
        {
            "rule_id": "MALT_NET_CONTENTS_16OZ_PINT",
            "name": "Malt beverage 16 fl. oz. should be 1 Pint",
            "beverage_types": ["malt_beverage"],
            "category": "strict_compliance",
            "confidence_tier": "tier_1_official",
            "default_verdict": "fail",
            "source_refs": ["SRC_27_CFR_PART_7"],
            "requirement_summary": "Malt beverage net contents should use the required U.S. standard measure form for intermediate volumes.",
            "detection_method": "Regex and volume parser for 16 fl. oz. without 1 Pint.",
            "pass_condition": "Label states 1 Pint where required.",
            "fail_condition": "Label states only 16 fl. oz. or equivalent incorrect form.",
            "needs_review_condition": "OCR detects conflicting or low-confidence net-contents candidates.",
            "implemented_status": "planned",
            "app_module": "app/rules/net_contents.py",
            "fixtures": ["beer_16_fl_oz_only.png", "beer_1_pint_good.png"],
            "ui_message": "Malt beverage net contents may need to be expressed as 1 Pint.",
        },
        {
            "rule_id": "FORM_BRAND_MATCHES_LABEL",
            "name": "Application brand name matches label artwork",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "fuzzy_match",
            "confidence_tier": "stakeholder_requirement",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            "requirement_summary": "The brand name entered in the application should match the brand name on the label artwork.",
            "detection_method": "Normalize application and OCR text, then compute fuzzy similarity against OCR text windows.",
            "pass_condition": "Similarity score is above pass threshold.",
            "fail_condition": "Similarity score is below fail threshold with high OCR confidence.",
            "needs_review_condition": "Similarity score is ambiguous or OCR confidence is low.",
            "implemented_status": "planned",
            "app_module": "app/rules/field_matching.py",
            "fixtures": ["brand_match_good.png", "brand_case_difference.png", "brand_mismatch.png"],
            "ui_message": "Brand name on label does not clearly match application field.",
        },
        {
            "rule_id": "COUNTRY_OF_ORIGIN_MATCH",
            "name": "Country of origin matches imported application field",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "field_matching",
            "confidence_tier": "stakeholder_requirement",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
            "requirement_summary": "Imported products should have label country-of-origin text that matches the application field.",
            "detection_method": "For imported applications, normalize OCR text and compare the expected country with exact/fuzzy matching; detect clear conflicting country names.",
            "pass_condition": "Application is not imported, or expected country appears in high-confidence OCR text.",
            "fail_condition": "A clearly conflicting country appears in high-confidence OCR text.",
            "needs_review_condition": "Imported country field is blank, OCR confidence is low, or expected country cannot be found confidently.",
            "implemented_status": "implemented",
            "app_module": "app/services/rules/registry.py",
            "fixtures": ["imported_country_origin_pass.png"],
            "ui_message": "Country of origin does not clearly match the imported application field.",
        },
        {
            "rule_id": "IMAGE_FORMAT_ALLOWED_TYPES",
            "name": "Allowed label image file types",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "upload_preflight",
            "confidence_tier": "tier_1_official_or_guidance",
            "default_verdict": "fail",
            "source_refs": ["SRC_REPORT_14_HARDENING"],
            "requirement_summary": "The public demo should accept only supported label artwork formats and reject unsafe/unsupported files.",
            "detection_method": "Extension allowlist plus magic-byte validation.",
            "pass_condition": "File is .jpg, .jpeg, or .png and signature matches.",
            "fail_condition": "File is PDF, executable, double-extension, unsupported image type, or signature mismatch.",
            "needs_review_condition": "File metadata is suspicious but not conclusively unsafe.",
            "implemented_status": "planned",
            "app_module": "app/services/security/upload_policy.py",
            "fixtures": ["bad_pdf_upload.pdf", "bad_double_extension.png.php"],
            "ui_message": "Unsupported or unsafe label-image upload.",
        },
        {
            "rule_id": "HEALTH_CLAIM_EXPLICIT",
            "name": "Potential explicit health claim",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "risk_review",
            "confidence_tier": "tier_2_case_or_precedent",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_27_USC_205"],
            "requirement_summary": "Health-benefit or reduced-harm claims can create misleading consumer impressions and require human review.",
            "detection_method": "Keyword/window scan for terms such as liver, DNA, safer, less toxic, protective, detox, or reduces harm.",
            "pass_condition": "No health-risk terms detected near alcohol/product/ingredient identity text.",
            "fail_condition": "",
            "needs_review_condition": "Health-risk terms appear near product identity, ingredients, or alcohol-related language.",
            "implemented_status": "planned",
            "app_module": "app/rules/health_claims.py",
            "fixtures": ["bellion_style_health_claim.png"],
            "ui_message": "Potential health-related claim detected. Human review required.",
        },
        {
            "rule_id": "WINE_SEMI_GENERIC_NAME_DETECTED",
            "name": "Semi-generic wine name detected",
            "beverage_types": ["wine"],
            "category": "risk_review",
            "confidence_tier": "tier_1_official",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_TTB_IC_2006_01"],
            "requirement_summary": "Semi-generic wine names and Retsina require special support/context.",
            "detection_method": "Scan OCR text for semi-generic names such as Champagne, Chablis, Port, Sherry, Burgundy, and Retsina.",
            "pass_condition": "No semi-generic term detected, or support fields explain allowed use.",
            "fail_condition": "",
            "needs_review_condition": "Semi-generic term detected without sufficient support context.",
            "implemented_status": "planned",
            "app_module": "app/rules/wine/semi_generic_names.py",
            "fixtures": ["wine_california_champagne_new_use.png", "wine_angelica_exception.png"],
            "ui_message": "Semi-generic wine term detected. Verify support context.",
        },
        {
            "rule_id": "ABSINTHE_TERM_DETECTED",
            "name": "Absinthe / thujone support context",
            "beverage_types": ["distilled_spirits"],
            "category": "risk_review",
            "confidence_tier": "tier_1_official",
            "default_verdict": "needs_review",
            "source_refs": ["SRC_TTB_IC_2007_05"],
            "requirement_summary": "Absinthe-related terms require thujone-free/supporting context and should not imply hallucinogenic effects.",
            "detection_method": "Scan OCR text for absinthe, absinth, wormwood, thujone, green fairy, or mind-altering terms.",
            "pass_condition": "No absinthe risk terms detected, or manifest support fields are present.",
            "fail_condition": "",
            "needs_review_condition": "Absinthe-related terms detected without support context.",
            "implemented_status": "planned",
            "app_module": "app/rules/spirits/absinthe_thujone.py",
            "fixtures": ["spirits_absinthe_standalone.png", "spirits_absinthe_green_fairy_claim.png"],
            "ui_message": "Absinthe/thujone-related term detected. Verify supporting context.",
        },
        {
            "rule_id": "SYNTHETIC_NEGATIVE_REQUIRED",
            "name": "Synthetic negative fixture strategy",
            "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
            "category": "data_strategy",
            "confidence_tier": "tier_3_research_synthesis",
            "default_verdict": "info",
            "source_refs": ["SRC_REPORT_09_SYNTHETIC_FIXTURES", "SRC_TTB_PUBLIC_COLA_REGISTRY"],
            "requirement_summary": "Because rejected/Needs Correction applications are not generally public, controlled synthetic negative fixtures are required.",
            "detection_method": "Documentation and fixture-provenance validation.",
            "pass_condition": "Every synthetic fixture maps to rule IDs, source refs, and expected verdict.",
            "fail_condition": "",
            "needs_review_condition": "",
            "implemented_status": "planned",
            "app_module": "scripts/generate_synthetic_fixtures.py",
            "fixtures": [],
            "ui_message": "Data strategy note only.",
        },
    ]


def starter_fixtures() -> list[dict[str, object]]:
    return [
        {
            "fixture_id": "warning_missing_machinery_comma",
            "file_path": "data/fixtures/synthetic/warning_missing_machinery_comma.png",
            "source_type": "synthetic_mutation",
            "base_image_source": "synthetic",
            "rule_ids": ["GOV_WARNING_EXACT_TEXT"],
            "source_refs": ["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
            "expected_verdict": "fail",
            "mutation_summary": "Removed required comma after 'machinery' in the government warning.",
        },
        {
            "fixture_id": "beer_16_fl_oz_only",
            "file_path": "data/fixtures/synthetic/beer_16_fl_oz_only.png",
            "source_type": "synthetic_mutation",
            "base_image_source": "synthetic",
            "rule_ids": ["MALT_NET_CONTENTS_16OZ_PINT"],
            "source_refs": ["SRC_27_CFR_PART_7"],
            "expected_verdict": "fail",
            "mutation_summary": "Used 16 fl. oz. instead of 1 Pint for a malt beverage fixture.",
        },
        {
            "fixture_id": "beer_5_percent_abv",
            "file_path": "data/fixtures/synthetic/beer_5_percent_abv.png",
            "source_type": "synthetic_mutation",
            "base_image_source": "synthetic",
            "rule_ids": ["ALCOHOL_ABV_PROHIBITED"],
            "source_refs": ["SRC_27_CFR_PART_7"],
            "expected_verdict": "fail",
            "mutation_summary": "Used ABV shorthand in alcohol-content statement.",
        },
        {
            "fixture_id": "bellion_style_health_claim",
            "file_path": "data/fixtures/synthetic/bellion_style_health_claim.png",
            "source_type": "synthetic_mutation",
            "base_image_source": "synthetic",
            "rule_ids": ["HEALTH_CLAIM_EXPLICIT"],
            "source_refs": ["SRC_27_USC_205"],
            "expected_verdict": "needs_review",
            "mutation_summary": "Injected health-benefit/risk-reduction language near product identity text.",
        },
    ]


def render_source_ledger_md(sources: list[dict[str, object]]) -> str:
    rows = []
    for s in sources:
        used_for = ", ".join(s.get("used_for", []))
        rows.append(
            f"| {s['source_id']} | {s['confidence_tier']} | {s['source_type']} | "
            f"{s['title']} | {used_for} |"
        )

    return dedent(
        f"""
        # Source Ledger

        Generated: {TODAY}

        This ledger tracks statutes, regulations, TTB guidance, court/case sources,
        stakeholder notes, and research reports used by Labels On Tap.

        | Source ID | Tier | Type | Title | Used For |
        |---|---|---|---|---|
        {chr(10).join(rows)}
        """
    )


def render_criteria_md(criteria: list[dict[str, object]]) -> str:
    rows = []
    for r in criteria:
        sources = ", ".join(r.get("source_refs", []))
        fixtures = ", ".join(r.get("fixtures", []))
        rows.append(
            f"| {r['rule_id']} | {r['category']} | {r['default_verdict']} | "
            f"{sources} | {r['implemented_status']} | {fixtures} |"
        )

    return dedent(
        f"""
        # Source-Backed Criteria Matrix

        Generated: {TODAY}

        Every implemented rule should trace to at least one source, one detection method,
        one verdict policy, and eventually one fixture/test.

        | Rule ID | Category | Default Verdict | Sources | Status | Fixtures |
        |---|---|---|---|---|---|
        {chr(10).join(rows)}
        """
    )


def render_fixture_md(fixtures: list[dict[str, object]]) -> str:
    rows = []
    for f in fixtures:
        rows.append(
            f"| {f['fixture_id']} | {', '.join(f['rule_ids'])} | "
            f"{f['expected_verdict']} | {f['source_type']} | {f['mutation_summary']} |"
        )

    return dedent(
        f"""
        # Fixture Provenance

        Generated: {TODAY}

        This file maps demo/test fixtures to rule IDs, source references, and expected verdicts.

        | Fixture | Rule IDs | Expected Verdict | Source Type | Mutation Summary |
        |---|---|---|---|---|
        {chr(10).join(rows)}
        """
    )


def write_static_docs(force: bool) -> None:
    write_text(
        ROOT / "research/legal-corpus/README.md",
        f"""
        # Legal Corpus

        This directory is the structured evidence base for Labels On Tap.

        The intended chain is:

        ```text
        Source → Extracted Requirement → Rule Matrix Row → App Rule → Fixture/Test → UI Explanation
        ```

        ## Contents

        - `source-ledger.json` / `source-ledger.md`: source inventory
        - `matrices/source-backed-criteria.json`: machine-readable rule matrix
        - `matrices/source-backed-criteria.md`: human-readable rule matrix
        - `forms/form-5100-31-field-map.md`: application form field mapping
        - `public-data-boundaries.md`: data acquisition and confidentiality boundaries
        - `reports/`: sanitized research reports
        - `excerpts/`: operative excerpts used for implementation

        ## Policy

        Labels On Tap is a preflight and reviewer-support prototype. It does not issue final legal determinations.
        Deterministic Tier 1 requirements may produce Fail. Subjective, image-limited, Tier 2, or Tier 3 criteria
        should route to Needs Review.
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/source-confidence.md",
        """
        # Source Confidence Policy

        ## Tier 1 — Official authority

        - U.S. Code
        - CFR / eCFR current-reference text
        - TTB.gov guidance
        - TTB forms
        - TTB industry circulars
        - Federal court opinions

        ## Tier 2 — Public legal / industry analysis

        - Law firm summaries
        - Compliance provider reports
        - Public litigation summaries
        - Industry whitepapers

        ## Tier 3 — OSINT / research synthesis / fixture inspiration

        - Forums
        - Publicly posted correction examples
        - Internal research reports
        - Synthetic mutations

        ## Verdict policy

        ```text
        Tier 1 + deterministic requirement → Fail / Pass
        Tier 1 + subjective requirement     → Needs Review
        Tier 2                              → Needs Review
        Tier 3                              → Needs Review or fixture inspiration only
        ```
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/federal-statutes.md",
        """
        # Federal Statutes Index

        ## 27 U.S.C. § 205 — FAA Act labeling authority

        Used for:
        - labeling authority context
        - misleading label risk
        - consumer deception risk

        ## 27 U.S.C. § 215 — Alcoholic beverage health warning

        Used for:
        - government warning presence
        - statutory warning requirement
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/cfr-regulations.md",
        """
        # CFR Regulations Index

        ## 27 CFR Part 4 — Wine

        Used for wine-specific labeling rules, appellation, grape varietal, wine alcohol content, and geographic-origin risk.

        ## 27 CFR Part 5 — Distilled Spirits

        Used for class/type, proof/alcohol content, standards of identity, state of distillation, formula-trigger language, and spirits-specific risk rules.

        ## 27 CFR Part 7 — Malt Beverages

        Used for malt beverage class/type, net contents, alcohol-content terminology, low/no alcohol terminology, and style-name checks.

        ## 27 CFR Part 13 — Labeling Proceedings

        Used for COLA workflow, certificate/exemption context, and public data boundaries.

        ## 27 CFR Part 16 — Alcoholic Beverage Health Warning Statement

        Used for exact warning text, capitalization, boldness, legibility, contrast, and typography checks.
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/ttb-guidance-and-circulars.md",
        """
        # TTB Guidance and Circulars

        ## TTB Form 5100.31

        Primary schema reference for application fields and expected label/application comparison.

        ## Industry Circular 2006-01

        Semi-generic wine names and Retsina support context.

        ## Industry Circular 2007-05

        Absinthe/thujone policy and hallucinogenic-imagery risk context.

        ## COLAs Online and Public COLA Registry Guidance

        Used for workflow, public data boundaries, and fixture strategy.
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/court-cases-and-precedents.md",
        """
        # Court Cases and Precedents

        ## Bellion Spirits / NTX

        Used for health-claim and misleading-impression risk heuristics.

        Build behavior:
        - Generally route to Needs Review.
        - Do not issue final legal determinations.

        ## Copper Cane / Elouan

        Used for geographic-origin and post-approval risk heuristics.

        Build behavior:
        - Route multiple protected geographic terms or inconsistent origin signals to Needs Review.

        ## Commercial speech background cases

        Use as background context only unless mapped to a specific implemented rule.
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/public-data-boundaries.md",
        """
        # Public Data Boundaries

        The deployed Labels On Tap application does not crawl, scrape, enumerate, or access private COLAs Online data.

        Data strategy:

        1. Use public approved COLA records for positive/realistic fixtures.
        2. Use public surrendered/revoked records only as post-market anomaly context.
        3. Use synthetic negative mutations for deterministic failure fixtures.
        4. Use public legal/case-study sources for Needs Review heuristics.
        5. Do not claim access to confidential rejected or Needs Correction application data.
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/forms/form-5100-31-field-map.md",
        """
        # TTB Form 5100.31 Field Map

        | Form Field | App Schema Field | Label OCR Comparison? | Rule IDs | Notes |
        |---|---|---:|---|---|
        | Representative ID | representative_id | No | FORM_REPRESENTATIVE_CONTEXT | Proxy/agent context |
        | Plant Registry / Basic Permit | plant_registry_or_basic_permit | No | FORM_PERMIT_PRESENT | Applicant authority |
        | Source of Product | source_of_product | No | PRODUCT_SOURCE_ROUTING | Domestic/imported routing |
        | Country of Origin | country_of_origin | Yes, for imports | COUNTRY_OF_ORIGIN_MATCH | Import-origin match |
        | Serial Number | serial_number | No | FORM_SERIAL_PRESENT | Applicant tracking |
        | Type of Product | product_type | No | PRODUCT_TYPE_ROUTING | Wine / spirits / malt |
        | Brand Name | brand_name | Yes | FORM_BRAND_MATCHES_LABEL | Fuzzy match |
        | Fanciful Name | fanciful_name | Yes | FORM_FANCIFUL_NAME_MATCHES_LABEL | Fuzzy match |
        | Name and Address | applicant_name / applicant_address | Yes | FORM_NAME_ADDRESS_MATCHES_LABEL | Fuzzy/address match |
        | Formula / SOP | formula_id / statement_of_composition | Conditional | FORMULA_REQUIRED_RISK, SOC_EXACT_MATCH | Formula-trigger rules |
        | Grape Varietal | grape_varietals | Wine only | WINE_VARIETAL_MATCH | Wine-specific |
        | Appellation | appellation_of_origin | Wine only | WINE_APPELLATION_MATCH, GEOGRAPHIC_ORIGIN_RISK | Wine-specific |
        | Type of Application | type_of_application | Contextual | CERTIFICATE_EXEMPTION_CONTEXT | COLA/exemption/distinctive bottle |
        | Translations / Embossed Info | translations / embossed_or_blow_in_information | Conditional | FOREIGN_TEXT_TRANSLATION_REQUIRED | If foreign text present |
        | Label Dimensions | label_width_inches / label_height_inches | Indirect | WARNING_TYPE_SIZE_ESTIMATE | Needed for typography estimates |
        """,
        force,
    )

    write_text(
        ROOT / "research/legal-corpus/excerpts/cfr/27-cfr-part-16-government-warning.md",
        """
        # 27 CFR Part 16 — Government Warning Implementation Excerpt

        Source ID: SRC_27_CFR_PART_16

        ## Canonical warning text

        GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

        ## Implementation notes

        - Normalize whitespace and OCR line breaks only.
        - Do not normalize punctuation.
        - Do not normalize capitalization in `GOVERNMENT WARNING:`.
        - Header capitalization is a separate strict check.
        - Bold detection is a CV heuristic and may return Needs Review.
        """,
        force,
    )

    write_text(
        ROOT / "docs/research-summary.md",
        """
        # Research Summary

        Labels On Tap is built around a source-backed evidence chain:

        ```text
        Law / regulation / guidance / precedent
          → source-backed criterion
          → app rule
          → fixture/test
          → UI explanation
        ```

        Key decisions:

        - Runtime OCR and validation are local-first.
        - Hosted ML endpoints and VLMs are excluded from runtime.
        - The app is a preflight and reviewer-support prototype, not final agency action.
        - Rejected/Needs Correction data is not treated as public fixture data.
        - Synthetic negative fixtures are used for controlled failure tests.
        """,
        force,
    )

    write_text(
        ROOT / "docs/validation-rules.md",
        """
        # Validation Rules

        The validation engine separates rules into:

        1. Strict deterministic compliance checks.
        2. Fuzzy application-vs-label matching.
        3. Numeric/unit normalization.
        4. Image and upload preflight checks.
        5. Risk-based Needs Review heuristics.

        See:

        ```text
        research/legal-corpus/matrices/source-backed-criteria.json
        ```
        """,
        force,
    )

    write_text(
        ROOT / "docs/data-strategy.md",
        """
        # Data Strategy

        Labels On Tap uses:

        1. Public approved COLA labels for realistic positive examples.
        2. Public surrendered/revoked records only as post-market context.
        3. Synthetic negative mutations for controlled failure tests.
        4. Source-backed fixture provenance for every demo/test label.

        The deployed app does not crawl public registries or access private COLAs Online data.
        """,
        force,
    )

    write_text(
        ROOT / "docs/security-and-privacy.md",
        """
        # Security and Privacy

        Public prototype upload controls:

        - extension allowlist
        - magic-byte validation
        - randomized filenames
        - path traversal rejection
        - double-extension rejection
        - size limits
        - safe ZIP extraction
        - cleanup of old jobs
        - no hosted ML endpoints
        - no long-term sensitive data retention

        This is a prototype and does not implement production federal identity, audit logging, or records retention.
        """,
        force,
    )


def write_report_placeholders(force: bool) -> None:
    reports = [
        "01-public-cola-data-strategy.md",
        "02-postmarket-anomaly-strategy.md",
        "03-legal-precedents-risk-triggers.md",
        "04-distilled-spirits-denial-taxonomy.md",
        "05-algorithmic-fatal-flaws-image-preflight.md",
        "06-foia-circulars-semi-generic-absinthe.md",
        "07-ocr-benchmarking-data-ingestion.md",
        "08-deterministic-cfr-rule-matrix-topology.md",
        "09-data-acquisition-synthetic-fixtures.md",
        "10-boot-camp-fatal-flaws.md",
        "11-local-first-ocr-deployment.md",
        "12-needs-correction-workflow.md",
        "13-cpu-ocr-vm-deployment.md",
        "14-federal-hardening-accessibility.md",
        "15-form-5100-31-upstream-journey.md",
    ]

    for name in reports:
        title = name.replace(".md", "").replace("-", " ").title()
        write_text(
            ROOT / "research/legal-corpus/reports" / name,
            f"""
            # {title}

            ## Purpose

            Placeholder for sanitized research synthesis.

            ## Source Confidence Policy

            - Official law/regulation/guidance supports Tier 1 criteria.
            - Public case studies and legal analysis support Needs Review heuristics.
            - OSINT/research findings support fixture design and review triggers unless independently confirmed by official sources.

            ## Findings

            TODO: Paste sanitized findings here.

            ## Rule Matrix Updates

            TODO: List rule IDs created or updated by this report.

            ## Data / Fixture Impact

            TODO: List fixtures or fixture-generation needs.
            """,
            force,
        )


def write_validation_script(force: bool) -> None:
    content = r'''
#!/usr/bin/env python3
"""
Validate legal corpus consistency.

Checks:
- Every criterion source_ref exists in source-ledger.json.
- Tier 2/Tier 3 rules do not default to Fail.
- Every non-info criterion has at least one fixture or is explicitly documented as fixture_pending.
- Fixture provenance references existing rule IDs and source IDs.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "research/legal-corpus"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    errors: list[str] = []

    sources_doc = load_json(CORPUS / "source-ledger.json")
    criteria_doc = load_json(CORPUS / "matrices/source-backed-criteria.json")
    fixtures_doc = load_json(ROOT / "data/source-maps/fixture-provenance.json")

    sources = sources_doc["sources"]
    criteria = criteria_doc["criteria"]
    fixtures = fixtures_doc["fixtures"]

    source_ids = {s["source_id"] for s in sources}
    rule_ids = {r["rule_id"] for r in criteria}

    for rule in criteria:
        rid = rule["rule_id"]

        for ref in rule.get("source_refs", []):
            if ref not in source_ids:
                errors.append(f"{rid}: missing source_ref {ref}")

        tier = rule.get("confidence_tier", "")
        default_verdict = rule.get("default_verdict", "")

        if tier.startswith("tier_2") or tier.startswith("tier_3"):
            if default_verdict == "fail":
                errors.append(f"{rid}: Tier 2/3 rule must not default to Fail")

        if default_verdict not in {"pass", "fail", "needs_review", "info"}:
            errors.append(f"{rid}: invalid default_verdict {default_verdict}")

        if default_verdict != "info" and not rule.get("fixtures"):
            errors.append(f"{rid}: non-info rule has no fixtures")

    for fixture in fixtures:
        fid = fixture["fixture_id"]

        for rid in fixture.get("rule_ids", []):
            if rid not in rule_ids:
                errors.append(f"{fid}: references missing rule_id {rid}")

        for ref in fixture.get("source_refs", []):
            if ref not in source_ids:
                errors.append(f"{fid}: references missing source_ref {ref}")

    if errors:
        print("Legal corpus validation failed:\n")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("Legal corpus validation passed.")


if __name__ == "__main__":
    main()
'''
    write_text(ROOT / "scripts/validate_legal_corpus.py", content, force)


def write_data_files(force: bool) -> None:
    sources = starter_sources()
    criteria = starter_criteria()
    fixtures = starter_fixtures()

    write_json(ROOT / "research/legal-corpus/source-ledger.json", {"generated_at": TODAY, "sources": sources}, force)
    write_text(ROOT / "research/legal-corpus/source-ledger.md", render_source_ledger_md(sources), force)

    write_json(
        ROOT / "research/legal-corpus/matrices/source-backed-criteria.json",
        {"generated_at": TODAY, "criteria": criteria},
        force,
    )
    write_text(
        ROOT / "research/legal-corpus/matrices/source-backed-criteria.md",
        render_criteria_md(criteria),
        force,
    )

    criteria_csv_rows = []
    for r in criteria:
        criteria_csv_rows.append(
            {
                "rule_id": r["rule_id"],
                "name": r["name"],
                "category": r["category"],
                "confidence_tier": r["confidence_tier"],
                "default_verdict": r["default_verdict"],
                "source_refs": ";".join(r.get("source_refs", [])),
                "implemented_status": r["implemented_status"],
                "app_module": r["app_module"],
                "fixtures": ";".join(r.get("fixtures", [])),
            }
        )

    write_csv(
        ROOT / "research/legal-corpus/matrices/source-backed-criteria.csv",
        criteria_csv_rows,
        [
            "rule_id",
            "name",
            "category",
            "confidence_tier",
            "default_verdict",
            "source_refs",
            "implemented_status",
            "app_module",
            "fixtures",
        ],
        force,
    )

    write_json(ROOT / "data/source-maps/fixture-provenance.json", {"generated_at": TODAY, "fixtures": fixtures}, force)
    write_text(ROOT / "data/source-maps/fixture-provenance.md", render_fixture_md(fixtures), force)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite generated files if they already exist")
    args = parser.parse_args()

    mkdirs()
    write_data_files(args.force)
    write_static_docs(args.force)
    write_report_placeholders(args.force)
    write_validation_script(args.force)

    print()
    print("Bootstrap complete.")
    print()
    print("Next steps:")
    print("  1. python scripts/validate_legal_corpus.py")
    print("  2. Fill sanitized research reports in research/legal-corpus/reports/")
    print("  3. Add/update rules in research/legal-corpus/matrices/source-backed-criteria.json")
    print("  4. Add/update fixtures in data/source-maps/fixture-provenance.json")
    print("  5. Keep Tier 2/Tier 3 rules as Needs Review unless backed by official deterministic authority")


if __name__ == "__main__":
    main()
