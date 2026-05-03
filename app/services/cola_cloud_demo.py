"""Local COLA Cloud-derived public example comparison helpers.

This module powers a demonstration workflow that reads already-downloaded,
gitignored COLA Cloud-derived public records from ``data/work/cola``. It does
not call the COLA Cloud API at runtime and it does not commit raw public data.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import ROOT
from app.schemas.ocr import OCRResult
from app.services.rules.field_matching import fuzzy_score, normalize_label_text


COLA_WORK_DIR = ROOT / "data/work/cola"
OCR_CONVEYOR_DIR = ROOT / "data/work/ocr-conveyor"
PREFERRED_DEMO_TTB_ID = "25120001000657"
PRIMARY_FIELDS = (
    "brand_name",
    "fanciful_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "country_of_origin",
    "applicant_or_producer",
)


@dataclass(frozen=True)
class ColaCloudPanel:
    """One local label panel image for a COLA Cloud-derived public record."""

    panel_order: int
    filename: str
    image_type: str
    image_path: Path
    source_url: str = ""
    stored_filename: str = ""


@dataclass(frozen=True)
class ColaCloudDemoSource:
    """Application fields and local image panels for one demo record."""

    dataset_name: str
    dataset_root: Path
    ttb_id: str
    parsed: dict[str, Any]
    panels: list[ColaCloudPanel]


def load_cola_cloud_demo_source(ttb_id: str | None = None) -> ColaCloudDemoSource | None:
    """Return one local COLA Cloud-derived record suitable for demonstration.

    Parameters
    ----------
    ttb_id:
        Optional specific TTB ID. When omitted, a deterministic preferred record
        is used if available, then the first usable local record is returned.

    Returns
    -------
    ColaCloudDemoSource | None
        Demo source with parsed application JSON and local image paths, or
        ``None`` when the gitignored data corpus is absent.
    """

    if not COLA_WORK_DIR.exists():
        return None

    if ttb_id:
        source = _source_for_ttb_id(ttb_id)
        return source

    preferred = _source_for_ttb_id(PREFERRED_DEMO_TTB_ID)
    if preferred is not None:
        return preferred

    for dataset_root in _dataset_roots():
        applications_dir = dataset_root / "applications"
        for path in sorted(applications_dir.glob("*.json"))[:500]:
            source = _source_from_application_path(dataset_root, path)
            if source is not None and _expected_value_count(source.parsed) >= 3:
                return source
    return None


def build_comparison_payload(
    *,
    source: ColaCloudDemoSource,
    panel_ocrs: list[tuple[ColaCloudPanel, OCRResult]],
) -> dict[str, Any]:
    """Build the side-by-side application-field/OCR-evidence payload."""

    expected = expected_fields(source.parsed)
    field_results = [
        compare_field(field_name, expected[field_name], panel_ocrs)
        for field_name in PRIMARY_FIELDS
    ]
    actionable = [item for item in field_results if item["verdict"] != "not_applicable"]
    overall = "pass" if actionable and all(item["verdict"] == "pass" for item in actionable) else "needs_review"
    return {
        "source_type": "COLA Cloud-derived public data",
        "dataset_name": source.dataset_name,
        "ttb_id": source.ttb_id,
        "source_url": source.parsed.get("source_url", ""),
        "status": source.parsed.get("form_fields", {}).get("status", ""),
        "source_of_product": source.parsed.get("form_fields", {}).get("source_of_product", ""),
        "overall_verdict": overall,
        "application": source.parsed.get("application", {}),
        "form_fields": source.parsed.get("form_fields", {}),
        "fields": field_results,
        "panels": [
            {
                **asdict(panel),
                "image_path": str(panel.image_path),
                "ocr": ocr.model_dump() if hasattr(ocr, "model_dump") else ocr.dict(),
            }
            for panel, ocr in panel_ocrs
        ],
        "caveats": [
            "This demo uses local COLA Cloud-derived public data under data/work/cola.",
            "COLA Cloud is not a runtime dependency; this route reads already-downloaded local files.",
            "The comparison demonstrates application-field-to-label-evidence matching, not a final TTB approval decision.",
        ],
    }


def load_cached_conveyor_ocr(image_path: Path, engine: str = "doctr") -> OCRResult | None:
    """Load cached OCR conveyor output for an image when available."""

    relative = _relative_path(image_path)
    if not OCR_CONVEYOR_DIR.exists():
        return None
    for rows_path in sorted(OCR_CONVEYOR_DIR.glob("*/runs/*/rows.csv"), reverse=True):
        try:
            with rows_path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("engine") != engine or row.get("status") != "ok":
                        continue
                    if row.get("image_path") != relative:
                        continue
                    ocr_json = ROOT / (row.get("ocr_json_path") or "")
                    if ocr_json.exists():
                        payload = json.loads(ocr_json.read_text(encoding="utf-8"))
                        return OCRResult(**payload)
        except OSError:
            continue
    return None


def expected_fields(parsed: dict[str, Any]) -> dict[str, str]:
    """Derive expected application fields from a COLA Cloud application JSON."""

    application = parsed.get("application", {})
    form_fields = parsed.get("form_fields", {})
    imported = bool(application.get("imported")) or form_fields.get("source_of_product", "").lower() == "imported"
    origin = application.get("country_of_origin") or form_fields.get("origin_desc") or ""
    applicant_or_producer = _applicant_or_producer(form_fields.get("applicant_name_address", ""))
    return {
        "brand_name": _clean(application.get("brand_name") or form_fields.get("brand_name")),
        "fanciful_name": _clean(application.get("fanciful_name") or form_fields.get("fanciful_name")),
        "class_type": _clean(application.get("class_type") or form_fields.get("class_type_description")),
        "alcohol_content": _clean(application.get("alcohol_content") or form_fields.get("alcohol_content")),
        "net_contents": _clean(application.get("net_contents") or form_fields.get("net_contents")),
        "country_of_origin": _clean(origin if imported else ""),
        "applicant_or_producer": _clean(applicant_or_producer),
    }


def compare_field(
    field_name: str,
    expected: str,
    panel_ocrs: list[tuple[ColaCloudPanel, OCRResult]],
    pass_threshold: float = 90.0,
    review_threshold: float = 75.0,
) -> dict[str, Any]:
    """Compare one application field against all OCR panel text."""

    variants = field_candidates(field_name, expected)
    if not variants:
        return {
            "field_name": field_name,
            "expected": "",
            "verdict": "not_applicable",
            "outcome": "no_expected_value",
            "score": 0.0,
            "best_panel": "",
            "best_panel_type": "",
            "evidence_text": "",
            "reviewer_action": "No application value was available for this field.",
        }

    best_score = 0.0
    best_panel: ColaCloudPanel | None = None
    best_text = ""
    best_variant = variants[0]
    for panel, ocr in panel_ocrs:
        text = ocr.full_text or ""
        for variant in variants:
            score = fuzzy_score(variant, text)
            if score > best_score:
                best_score = score
                best_panel = panel
                best_text = text
                best_variant = variant

    if best_score >= pass_threshold:
        verdict = "pass"
        outcome = "matched"
        action = "No reviewer action needed for this field."
    elif best_score >= review_threshold:
        verdict = "needs_review"
        outcome = "ambiguous_match"
        action = "Review this field manually; OCR found partial or ambiguous evidence."
    else:
        verdict = "needs_review"
        outcome = "not_found"
        action = "Review this field manually; OCR did not find strong label evidence."

    return {
        "field_name": field_name,
        "expected": expected,
        "verdict": verdict,
        "outcome": outcome,
        "score": round(best_score, 2),
        "best_panel": best_panel.filename if best_panel else "",
        "best_panel_type": best_panel.image_type if best_panel else "",
        "evidence_text": _evidence_window(best_text, best_variant),
        "reviewer_action": action,
    }


def field_candidates(field_name: str, expected: str) -> list[str]:
    """Generate practical OCR match candidates for one expected value."""

    expected = _clean(expected)
    if not expected:
        return []
    candidates = [expected]
    if field_name == "alcohol_content":
        number = _first_number(expected)
        if number:
            candidates.extend(
                [
                    number,
                    f"{number}%",
                    f"{number}% alc/vol",
                    f"{number}% alc vol",
                    f"{number}% alcohol by volume",
                ]
            )
    elif field_name == "net_contents":
        candidates.extend(_net_content_variants(expected))
    elif field_name == "class_type":
        candidates.extend(_class_type_variants(expected))
    elif field_name == "country_of_origin":
        candidates.extend([f"Product of {expected}", f"Made in {expected}", f"Imported from {expected}"])
    return _unique(candidates)


def _source_for_ttb_id(ttb_id: str) -> ColaCloudDemoSource | None:
    for dataset_root in _dataset_roots():
        path = dataset_root / "applications" / f"{ttb_id}.json"
        source = _source_from_application_path(dataset_root, path)
        if source is not None:
            return source
    return None


def _source_from_application_path(dataset_root: Path, path: Path) -> ColaCloudDemoSource | None:
    if not path.exists():
        return None
    parsed = json.loads(path.read_text(encoding="utf-8"))
    ttb_id = str(parsed.get("ttb_id") or parsed.get("application", {}).get("fixture_id") or path.stem)
    image_dir = dataset_root / "images" / ttb_id
    panels: list[ColaCloudPanel] = []
    for index, image_path in enumerate(sorted(image_dir.glob("*")), start=1):
        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        attachment = _attachment_for_image(parsed, image_path.name)
        panels.append(
            ColaCloudPanel(
                panel_order=int(attachment.get("panel_order") or index),
                filename=image_path.name,
                image_type=str(attachment.get("image_type") or f"panel {index}"),
                image_path=image_path,
                source_url=str(attachment.get("source_url") or ""),
            )
        )
    if not panels:
        return None
    return ColaCloudDemoSource(
        dataset_name=dataset_root.name,
        dataset_root=dataset_root,
        ttb_id=ttb_id,
        parsed=parsed,
        panels=sorted(panels, key=lambda panel: panel.panel_order),
    )


def _dataset_roots() -> list[Path]:
    preferred = [
        COLA_WORK_DIR / "official-sample-3000-balanced",
        COLA_WORK_DIR / "official-sample-1500",
        COLA_WORK_DIR / "colacloud-api-detail-probe",
    ]
    roots = [root for root in preferred if (root / "applications").exists() and (root / "images").exists()]
    for root in sorted(COLA_WORK_DIR.glob("*")):
        if root not in roots and (root / "applications").exists() and (root / "images").exists():
            roots.append(root)
    return roots


def _attachment_for_image(parsed: dict[str, Any], image_name: str) -> dict[str, Any]:
    compact = re.sub(r"^\d+_", "", image_name)
    for attachment in parsed.get("attachments", []):
        filename = str(attachment.get("filename") or "")
        if filename == image_name or Path(filename).stem == Path(compact).stem or Path(filename).stem in image_name:
            return attachment
    return {}


def _expected_value_count(parsed: dict[str, Any]) -> int:
    return sum(1 for value in expected_fields(parsed).values() if value)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _first_line(value: str) -> str:
    for line in str(value or "").splitlines():
        line = _clean(line)
        if line:
            return line
    return ""


def _used_on_label_name(value: str) -> str:
    match = re.search(r"\n([^\n]+)\s*\(Used on label\)", value or "", re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _applicant_or_producer(value: str) -> str:
    """Return a label-comparable producer/applicant name when one is present."""

    used_on_label = _used_on_label_name(value)
    if used_on_label:
        return used_on_label
    first_line = _first_line(value)
    if re.fullmatch(r"(?:DSP|BWN|WIN|BR|DSP|VA|CT|OR|TX|CA|NY|TN|KY|WA|FL|MI|MO|IL|OH|PA|NC|SC|GA|AZ|CO|NM|NJ|MD|MA|ME|VT|NH|RI|AK|HI|ID|IN|IA|KS|LA|MN|MS|MT|ND|NE|NV|OK|SD|UT|WI|WV|WY)[-A-Z0-9]*", first_line):
        return ""
    return first_line


def _first_number(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return match.group(0) if match else ""


def _net_content_variants(value: str) -> list[str]:
    text = normalize_label_text(value)
    number = _first_number(value)
    if not number:
        return []
    variants: list[str] = []
    if "ml" in text or "milliliter" in text:
        variants.extend([f"{number} ml", f"{number}ml", f"{number} milliliters"])
    if "liter" in text or re.search(r"\bl\b", text):
        variants.extend([f"{number} l", f"{number}l", f"{number} liter", f"{number} liters"])
    if "oz" in text or "fluid ounce" in text:
        variants.extend([f"{number} fl oz", f"{number} fl. oz.", f"{number} ounces", f"{number} oz"])
    if "pint" in text:
        variants.extend([f"{number} pint", f"{number} pints"])
    return variants


def _class_type_variants(value: str) -> list[str]:
    text = normalize_label_text(value)
    variants = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
    keyword_map = {
        "straight bourbon": ["straight bourbon whiskey", "straight bourbon whisky", "bourbon"],
        "bourbon": ["bourbon", "whiskey", "whisky"],
        "vodka": ["vodka"],
        "gin": ["gin"],
        "tequila": ["tequila"],
        "mezcal": ["mezcal"],
        "rum": ["rum"],
        "table red wine": ["table wine", "red wine"],
        "table white wine": ["table wine", "white wine"],
        "table wine": ["table wine"],
        "malt beverage": ["malt beverage", "beer"],
        "ale": ["ale"],
        "porter": ["porter"],
        "stout": ["stout"],
        "cider": ["cider", "hard cider"],
    }
    for keyword, additions in keyword_map.items():
        if keyword in text:
            variants.extend(additions)
    return variants


def _evidence_window(text: str, needle: str, radius: int = 180) -> str:
    text = _clean(text)
    if not text:
        return ""
    normalized_text = text.lower()
    normalized_needle = _clean(needle).lower()
    index = normalized_text.find(normalized_needle)
    if index < 0:
        return text[: radius * 2]
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end]


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)
