#!/usr/bin/env python3
"""
Generate deterministic demo/test fixtures for Labels On Tap.

The generated labels are synthetic by design. They give tests and one-click
demos stable inputs without relying on public registry scraping or confidential
rejected/Needs Correction COLA data.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from textwrap import wrap

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:  # pragma: no cover - exercised only on missing deps
    raise SystemExit(
        "Pillow is required to generate PNG fixtures. Install project "
        "dependencies first, then rerun scripts/bootstrap_project.py."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data/fixtures/demo"
SOURCE_MAP_DIR = ROOT / "data/source-maps"
TODAY = date.today().isoformat()

CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health problems."
)

WARNING_MISSING_COMMA = CANONICAL_WARNING.replace(
    "operate machinery, and may cause", "operate machinery and may cause"
)

WARNING_TITLE_CASE = CANONICAL_WARNING.replace(
    "GOVERNMENT WARNING:", "Government Warning:", 1
)


@dataclass(frozen=True)
class FixtureSpec:
    """Specification for one generated synthetic label fixture.

    Notes
    -----
    Each spec drives four outputs: PNG image, application JSON, OCR text JSON,
    and expected-result JSON. Keeping these in one data structure prevents the
    fixture image and expected verdict from drifting apart.
    """

    fixture_id: str
    filename: str
    product_type: str
    brand_name: str
    label_brand_name: str
    class_type: str
    alcohol_content: str
    label_alcohol_content: str
    net_contents: str
    label_net_contents: str
    warning_text: str
    expected_verdict: str
    checked_rule_ids: list[str]
    triggered_rule_ids: list[str]
    source_refs: list[str]
    mutation_summary: str
    top_reason: str
    blur: bool = False
    ocr_confidence: float | None = None
    country_of_origin: str = ""
    imported: bool = False
    label_country_of_origin: str = ""


FIXTURES: list[FixtureSpec] = [
    FixtureSpec(
        fixture_id="clean_malt_pass",
        filename="clean_malt_pass.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=CANONICAL_WARNING,
        expected_verdict="pass",
        checked_rule_ids=[
            "GOV_WARNING_EXACT_TEXT",
            "GOV_WARNING_HEADER_CAPS",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=[],
        source_refs=[
            "SRC_27_USC_215",
            "SRC_27_CFR_PART_16",
            "SRC_27_CFR_PART_7",
            "SRC_TTB_FORM_5100_31",
            "SRC_STAKEHOLDER_DISCOVERY",
        ],
        mutation_summary="Control fixture with matching application fields and canonical warning text.",
        top_reason="All implemented source-backed checks should pass.",
    ),
    FixtureSpec(
        fixture_id="warning_missing_comma_fail",
        filename="warning_missing_comma_fail.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=WARNING_MISSING_COMMA,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["GOV_WARNING_EXACT_TEXT"],
        source_refs=["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
        mutation_summary="Removed the required comma after 'machinery' in the government warning.",
        top_reason="Government warning text does not match the canonical wording.",
    ),
    FixtureSpec(
        fixture_id="warning_title_case_fail",
        filename="warning_title_case_fail.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=WARNING_TITLE_CASE,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["GOV_WARNING_HEADER_CAPS", "GOV_WARNING_EXACT_TEXT"],
        source_refs=["SRC_27_CFR_PART_16"],
        mutation_summary="Changed the warning heading from all caps to title case.",
        top_reason="Government warning heading is not in the required all-caps form.",
    ),
    FixtureSpec(
        fixture_id="abv_prohibited_fail",
        filename="abv_prohibited_fail.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ABV",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=CANONICAL_WARNING,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["ALCOHOL_ABV_PROHIBITED"],
        source_refs=["SRC_27_CFR_PART_7"],
        mutation_summary="Used ABV shorthand in a malt beverage alcohol-content statement.",
        top_reason="Prohibited alcohol-content abbreviation detected.",
    ),
    FixtureSpec(
        fixture_id="malt_16_fl_oz_fail",
        filename="malt_16_fl_oz_fail.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="16 fl. oz.",
        warning_text=CANONICAL_WARNING,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["MALT_NET_CONTENTS_16OZ_PINT"],
        source_refs=["SRC_27_CFR_PART_7"],
        mutation_summary="Used 16 fl. oz. where the demo application expects 1 Pint.",
        top_reason="Malt beverage net contents should use the required standard-measure form.",
    ),
    FixtureSpec(
        fixture_id="brand_case_difference_pass",
        filename="brand_case_difference_pass.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="Old River Brewing",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=CANONICAL_WARNING,
        expected_verdict="pass",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=[],
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        mutation_summary="Changed brand casing to validate fuzzy matching tolerance.",
        top_reason="Brand casing differs but should still be treated as the same brand.",
    ),
    FixtureSpec(
        fixture_id="low_confidence_blur_review",
        filename="low_confidence_blur_review.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=CANONICAL_WARNING,
        expected_verdict="needs_review",
        checked_rule_ids=["OCR_LOW_CONFIDENCE", "GOV_WARNING_HEADER_BOLD_REVIEW", "COUNTRY_OF_ORIGIN_MATCH"],
        triggered_rule_ids=["OCR_LOW_CONFIDENCE", "GOV_WARNING_HEADER_BOLD_REVIEW"],
        source_refs=["SRC_27_CFR_PART_16", "SRC_REPORT_14_HARDENING"],
        mutation_summary="Applied blur to create an OCR/typography confidence review fixture.",
        top_reason="Image quality should route the warning typography check to human review.",
        blur=True,
    ),
    FixtureSpec(
        fixture_id="brand_mismatch_fail",
        filename="brand_mismatch_fail.png",
        product_type="malt_beverage",
        brand_name="PHANTOM CELLARS",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text=CANONICAL_WARNING,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["FORM_BRAND_MATCHES_LABEL"],
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        mutation_summary="Application brand intentionally does not appear in the label OCR text.",
        top_reason="Brand name on label does not clearly match application field.",
    ),
    FixtureSpec(
        fixture_id="imported_missing_country_review",
        filename="imported_missing_country_review.png",
        product_type="wine",
        brand_name="VALLEY RIDGE",
        label_brand_name="VALLEY RIDGE",
        class_type="Red Wine",
        alcohol_content="13.5% ALC/VOL",
        label_alcohol_content="13.5% ALC/VOL",
        net_contents="750 mL",
        label_net_contents="750 mL",
        warning_text=CANONICAL_WARNING,
        expected_verdict="needs_review",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["COUNTRY_OF_ORIGIN_MATCH"],
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        mutation_summary="Imported application omits the expected country-of-origin field.",
        top_reason="Imported product is missing a country-of-origin application field.",
        imported=True,
        label_country_of_origin="France",
    ),
    FixtureSpec(
        fixture_id="conflicting_country_origin_fail",
        filename="conflicting_country_origin_fail.png",
        product_type="wine",
        brand_name="VALLEY RIDGE",
        label_brand_name="VALLEY RIDGE",
        class_type="Red Wine",
        alcohol_content="13.5% ALC/VOL",
        label_alcohol_content="13.5% ALC/VOL",
        net_contents="750 mL",
        label_net_contents="750 mL",
        warning_text=CANONICAL_WARNING,
        expected_verdict="fail",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=["COUNTRY_OF_ORIGIN_MATCH"],
        source_refs=["SRC_TTB_FORM_5100_31", "SRC_STAKEHOLDER_DISCOVERY"],
        mutation_summary="Application expects France, but label OCR contains a conflicting Italy origin statement.",
        top_reason="A conflicting country-of-origin statement appears on the label.",
        country_of_origin="France",
        imported=True,
        label_country_of_origin="Italy",
    ),
    FixtureSpec(
        fixture_id="warning_missing_block_review",
        filename="warning_missing_block_review.png",
        product_type="malt_beverage",
        brand_name="OLD RIVER BREWING",
        label_brand_name="OLD RIVER BREWING",
        class_type="Ale",
        alcohol_content="5% ALC/VOL",
        label_alcohol_content="5% ALC/VOL",
        net_contents="1 Pint",
        label_net_contents="1 Pint",
        warning_text="",
        expected_verdict="needs_review",
        checked_rule_ids=["OCR_LOW_CONFIDENCE", "GOV_WARNING_HEADER_BOLD_REVIEW", "COUNTRY_OF_ORIGIN_MATCH"],
        triggered_rule_ids=["OCR_LOW_CONFIDENCE", "GOV_WARNING_HEADER_BOLD_REVIEW"],
        source_refs=["SRC_27_CFR_PART_16", "SRC_REPORT_14_HARDENING"],
        mutation_summary="Warning block omitted and fixture OCR confidence lowered to force human review.",
        top_reason="Warning block cannot be machine-verified from low-confidence OCR.",
        ocr_confidence=0.66,
    ),
    FixtureSpec(
        fixture_id="imported_country_origin_pass",
        filename="imported_country_origin_pass.png",
        product_type="wine",
        brand_name="VALLEY RIDGE",
        label_brand_name="VALLEY RIDGE",
        class_type="Red Wine",
        alcohol_content="13.5% ALC/VOL",
        label_alcohol_content="13.5% ALC/VOL",
        net_contents="750 mL",
        label_net_contents="750 mL",
        warning_text=CANONICAL_WARNING,
        expected_verdict="pass",
        checked_rule_ids=[
            "GOV_WARNING_HEADER_CAPS",
            "GOV_WARNING_EXACT_TEXT",
            "ALCOHOL_ABV_PROHIBITED",
            "MALT_NET_CONTENTS_16OZ_PINT",
            "FORM_BRAND_MATCHES_LABEL",
            "COUNTRY_OF_ORIGIN_MATCH",
        ],
        triggered_rule_ids=[],
        source_refs=[
            "SRC_27_USC_215",
            "SRC_27_CFR_PART_16",
            "SRC_27_CFR_PART_4",
            "SRC_TTB_FORM_5100_31",
            "SRC_STAKEHOLDER_DISCOVERY",
        ],
        mutation_summary="Imported wine fixture with matching country-of-origin label text.",
        top_reason="Imported product country-of-origin statement should match the application field.",
        country_of_origin="France",
        imported=True,
        label_country_of_origin="France",
    ),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a local font with fallback to Pillow's default font."""

    candidates = [
        "/usr/share/fonts/google-noto/NotoSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/google-droid-sans-fonts/DroidSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/google-droid-sans-fonts/DroidSans.ttf",
        "/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Bold.otf"
        if bold
        else "/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Regular.otf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, fill: str) -> int:
    """Draw centered text and return the next vertical position."""

    bbox = draw.textbbox((0, 0), text, font=fnt)
    width = bbox[2] - bbox[0]
    x = (1200 - width) // 2
    draw.text((x, y), text, font=fnt, fill=fill)
    return y + (bbox[3] - bbox[1])


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_chars: int,
    fnt,
    fill: str,
    line_gap: int = 8,
) -> int:
    """Draw wrapped text at a fixed starting coordinate.

    Parameters
    ----------
    draw:
        Pillow drawing context.
    text:
        Text to wrap and draw.
    x, y:
        Starting coordinate.
    max_chars:
        Approximate wrap width in characters.
    fnt:
        Pillow font.
    fill:
        Text color.
    line_gap:
        Pixel gap between wrapped lines.
    """

    line_height = draw.textbbox((0, 0), "Ag", font=fnt)[3] + line_gap
    for line in wrap(text, width=max_chars):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def label_text(spec: FixtureSpec) -> str:
    """Build deterministic OCR ground-truth text for a fixture."""

    lines = [
        spec.label_brand_name,
        spec.class_type.upper(),
        spec.label_alcohol_content,
        f"NET CONTENTS {spec.label_net_contents}",
    ]
    if spec.imported and spec.label_country_of_origin:
        lines.append(f"PRODUCT OF {spec.label_country_of_origin.upper()}")
    if spec.warning_text:
        lines.append(spec.warning_text)
    return "\n".join(lines)


def render_label(spec: FixtureSpec, path: Path) -> None:
    """Render a synthetic label PNG for a fixture.

    Notes
    -----
    The image is intentionally simple and readable. The point is deterministic
    rule coverage, not photorealistic label art.
    """

    image = Image.new("RGB", (1200, 1800), "#f8f5ee")
    draw = ImageDraw.Draw(image)

    ink = "#1b1b19"
    muted = "#5f574d"
    accent = "#8a1f11"

    draw.rectangle((56, 56, 1144, 1744), outline=ink, width=8)
    draw.rectangle((90, 90, 1110, 1710), outline="#c9b99d", width=3)

    y = 170
    y = draw_centered(draw, spec.label_brand_name, y, font(76, bold=True), ink) + 24
    y = draw_centered(draw, spec.class_type.upper(), y, font(36), muted) + 80

    draw.line((220, y, 980, y), fill="#c9b99d", width=3)
    y += 80

    y = draw_centered(draw, spec.label_alcohol_content, y, font(48, bold=True), accent) + 34
    y = draw_centered(
        draw,
        f"NET CONTENTS {spec.label_net_contents}",
        y,
        font(42, bold=True),
        ink,
    ) + 70

    if spec.imported and spec.label_country_of_origin:
        y = draw_centered(
            draw,
            f"PRODUCT OF {spec.label_country_of_origin.upper()}",
            y,
            font(36, bold=True),
            accent,
        ) + 150
    else:
        y += 160

    draw.text((150, y), "PRODUCED AND PACKED BY", font=font(28), fill=muted)
    y += 42
    draw.text((150, y), "OLD RIVER BREWING COMPANY", font=font(34, bold=True), fill=ink)
    y += 44
    draw.text((150, y), "ST. LOUIS, MISSOURI", font=font(30), fill=ink)

    warning_y = 1280
    if spec.warning_text:
        draw.rectangle((116, warning_y - 34, 1084, 1625), outline=ink, width=3)
        heading, body = spec.warning_text.split(":", 1)
        heading_text = f"{heading}:"
        draw.text((150, warning_y), heading_text, font=font(30, bold=True), fill=ink)
        draw_wrapped(draw, body.strip(), 150, warning_y + 48, 78, font(27), ink)
    else:
        draw.rectangle((116, warning_y - 34, 1084, 1495), outline="#c9b99d", width=2)
        draw.text((150, warning_y), "LABEL AREA RESERVED FOR REQUIRED STATEMENTS", font=font(30), fill=muted)

    if spec.blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=3.0))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def application_payload(spec: FixtureSpec) -> dict[str, object]:
    """Return the Form 5100.31-style application payload for a fixture."""

    return {
        "fixture_id": spec.fixture_id,
        "filename": spec.filename,
        "product_type": spec.product_type,
        "brand_name": spec.brand_name,
        "fanciful_name": "",
        "class_type": spec.class_type,
        "alcohol_content": spec.alcohol_content,
        "net_contents": spec.net_contents,
        "country_of_origin": spec.country_of_origin,
        "imported": spec.imported,
        "formula_id": "",
        "statement_of_composition": "",
    }


def expected_payload(spec: FixtureSpec) -> dict[str, object]:
    """Return expected verdict metadata for a fixture."""

    return {
        "fixture_id": spec.fixture_id,
        "filename": spec.filename,
        "overall_verdict": spec.expected_verdict,
        "checked_rule_ids": spec.checked_rule_ids,
        "triggered_rule_ids": spec.triggered_rule_ids,
        "top_reason": spec.top_reason,
    }


def ocr_text_payload(spec: FixtureSpec) -> dict[str, object]:
    """Return OCR ground-truth payload for fixture OCR fallback."""

    confidence = spec.ocr_confidence if spec.ocr_confidence is not None else 0.42 if spec.blur else 0.98
    return {
        "fixture_id": spec.fixture_id,
        "filename": spec.filename,
        "full_text": label_text(spec),
        "avg_confidence": confidence,
        "blocks": [
            {"text": line, "confidence": confidence, "bbox": None}
            for line in label_text(spec).splitlines()
            if line.strip()
        ],
    }


def provenance_payload(spec: FixtureSpec) -> dict[str, object]:
    """Return source/provenance metadata for a generated fixture."""

    return {
        "fixture_id": spec.fixture_id,
        "file_path": f"data/fixtures/demo/{spec.filename}",
        "source_type": "synthetic_generation",
        "base_image_source": "synthetic",
        "rule_ids": spec.checked_rule_ids,
        "source_refs": spec.source_refs,
        "expected_verdict": spec.expected_verdict,
        "mutation_summary": spec.mutation_summary,
    }


def write_json(path: Path, payload: object, force: bool) -> None:
    """Write fixture JSON, optionally preserving existing files."""

    if path.exists() and not force:
        print(f"skip existing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote: {path}")


def write_image(spec: FixtureSpec, force: bool) -> None:
    """Write one fixture PNG."""

    path = DEMO_DIR / spec.filename
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return
    render_label(spec, path)
    print(f"wrote: {path}")


def write_manifest_csv(force: bool) -> None:
    """Write the generated CSV batch manifest."""

    path = DEMO_DIR / "batch_manifest.csv"
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return

    fieldnames = [
        "filename",
        "fixture_id",
        "product_type",
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "country_of_origin",
        "imported",
        "expected_verdict",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for spec in FIXTURES:
            app = application_payload(spec)
            writer.writerow(
                {
                    "filename": spec.filename,
                    "fixture_id": spec.fixture_id,
                    "product_type": spec.product_type,
                    "brand_name": app["brand_name"],
                    "class_type": app["class_type"],
                    "alcohol_content": app["alcohol_content"],
                    "net_contents": app["net_contents"],
                    "country_of_origin": app["country_of_origin"],
                    "imported": str(app["imported"]).lower(),
                    "expected_verdict": spec.expected_verdict,
                }
            )
    print(f"wrote: {path}")


def write_manifest_json(force: bool) -> None:
    """Write the generated JSON batch manifest."""

    payload = {
        "generated_at": TODAY,
        "items": [
            {
                **application_payload(spec),
                "expected": expected_payload(spec),
            }
            for spec in FIXTURES
        ],
    }
    write_json(DEMO_DIR / "batch_manifest.json", payload, force)


def merge_fixture_provenance(force: bool) -> None:
    """Merge generated fixture provenance into the source-map file."""

    path = SOURCE_MAP_DIR / "fixture-provenance.json"
    existing: list[dict[str, object]] = []
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        existing = doc.get("fixtures", [])

    generated = [provenance_payload(spec) for spec in FIXTURES]
    by_id = {fixture["fixture_id"]: fixture for fixture in existing}
    for fixture in generated:
        by_id[fixture["fixture_id"]] = fixture

    merged_fixtures = list(by_id.values())
    if path.exists() and not force and existing == merged_fixtures:
        print(f"skip existing: {path}")
        return

    payload = {
        "generated_at": TODAY,
        "fixtures": merged_fixtures,
    }
    write_json(path, payload, force=True)
    write_fixture_provenance_md(payload["fixtures"], force=True)


def write_fixture_provenance_md(fixtures: list[dict[str, object]], force: bool) -> None:
    """Write a Markdown table of fixture provenance."""

    rows = []
    for fixture in fixtures:
        rows.append(
            "| {fixture_id} | {rules} | {verdict} | {source_type} | {summary} |".format(
                fixture_id=fixture["fixture_id"],
                rules=", ".join(fixture.get("rule_ids", [])),
                verdict=fixture.get("expected_verdict", ""),
                source_type=fixture.get("source_type", ""),
                summary=fixture.get("mutation_summary", ""),
            )
        )

    content = "\n".join(
        [
            "# Fixture Provenance",
            "",
            f"Generated: {TODAY}",
            "",
            "This file maps demo/test fixtures to rule IDs, source references, and expected verdicts.",
            "",
            "| Fixture | Rule IDs | Expected Verdict | Source Type | Mutation Summary |",
            "|---|---|---|---|---|",
            *rows,
            "",
        ]
    )
    path = SOURCE_MAP_DIR / "fixture-provenance.md"
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"wrote: {path}")


def write_expected_results(force: bool) -> None:
    """Write expected result source map for all generated fixtures."""

    expected = {
        spec.fixture_id: expected_payload(spec)
        for spec in FIXTURES
    }
    write_json(SOURCE_MAP_DIR / "expected-results.json", {"generated_at": TODAY, "fixtures": expected}, force)


def write_fixture_files(force: bool) -> None:
    """Write all generated fixture artifacts."""

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for spec in FIXTURES:
        write_image(spec, force)
        write_json(DEMO_DIR / f"{spec.fixture_id}.application.json", application_payload(spec), force)
        write_json(DEMO_DIR / f"{spec.fixture_id}.expected.json", expected_payload(spec), force)
        write_json(DEMO_DIR / f"{spec.fixture_id}.ocr_text.json", ocr_text_payload(spec), force)

    write_manifest_csv(force)
    write_manifest_json(force)
    write_expected_results(force)
    merge_fixture_provenance(force)


def main() -> None:
    """Parse CLI arguments and generate fixture artifacts."""

    parser = argparse.ArgumentParser(description="Generate deterministic demo label fixtures.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    args = parser.parse_args()

    write_fixture_files(force=args.force)
    print("Demo fixture generation complete.")


if __name__ == "__main__":
    main()
