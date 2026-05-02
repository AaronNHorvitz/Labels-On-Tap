"""Evaluate OCR field matching on public COLA application/image bundles.

This module keeps the public COLA evaluation story separate from the
deterministic compliance-rule registry. Accepted public COLAs are positive
ground truth for a narrower claim: the label artwork should contain evidence
that matches the submitted application fields.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Iterable

from app.schemas.ocr import OCRResult
from app.services.ocr.doctr_engine import DoctrOCREngine
from app.services.rules.field_matching import fuzzy_score, normalize_label_text

from .csv_import import normalize_value
from .images import is_valid_image_path
from .paths import PARSED_APPLICATIONS_DIR, PARSED_OCR_DIR, PUBLIC_COLA_WORK_DIR


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
class PublicColaPanel:
    """Downloaded label panel associated with one public COLA application."""

    ttb_id: str
    panel_order: int
    filename: str
    image_type: str
    raw_image_path: Path
    source_url: str


@dataclass(frozen=True)
class PanelOCR:
    """OCR output and provenance for one downloaded label panel."""

    panel: PublicColaPanel
    ocr: OCRResult
    cache_hit: bool


@dataclass(frozen=True)
class FieldEvaluation:
    """One field-level application-to-label comparison."""

    ttb_id: str
    field_name: str
    expected: str
    verdict: str
    outcome: str
    score: float
    best_panel_order: int | None
    best_panel_type: str | None
    best_panel_filename: str | None
    evidence_text: str
    reviewer_action: str


@dataclass(frozen=True)
class ApplicationEvaluation:
    """Application-level evaluation with panel OCR and field results."""

    ttb_id: str
    status: str
    source_of_product: str
    image_count: int
    ocr_image_count: int
    cache_hit_count: int
    total_ocr_ms: int
    overall_verdict: str
    field_results: list[FieldEvaluation]


def clean_ttb_id(value: str | None) -> str:
    """Normalize Excel-style quoted TTB IDs from public CSV exports."""

    return normalize_value(value or "").strip("'")


def parse_json(path: Path) -> dict:
    """Load a parsed public COLA application JSON file."""

    return json.loads(path.read_text(encoding="utf-8"))


def ttb_id_from_parsed(path: Path, parsed: dict) -> str:
    """Return a parsed TTB ID, falling back to the JSON filename stem."""

    return clean_ttb_id(parsed.get("ttb_id") or parsed.get("application", {}).get("fixture_id") or path.stem)


def candidate_ttb_ids(ttb_id: str) -> tuple[str, str, str]:
    """Return common raw/quoted forms used by older local ETL rows."""

    clean = clean_ttb_id(ttb_id)
    return clean, f"'{clean}", f"'{clean}'"


def selected_parsed_paths(
    *,
    ttb_ids: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[Path]:
    """Return parsed public COLA JSON paths for an evaluation run."""

    if ttb_ids:
        paths = []
        for raw_id in ttb_ids:
            ttb_id = clean_ttb_id(raw_id)
            path = PARSED_APPLICATIONS_DIR / f"{ttb_id}.json"
            if path.exists():
                paths.append(path)
        return paths[:limit] if limit else paths

    paths = [
        path
        for path in sorted(PARSED_APPLICATIONS_DIR.glob("*.json"))
        if clean_ttb_id(path.stem) == path.stem
    ]
    return paths[:limit] if limit else paths


def registry_record(connection: sqlite3.Connection, ttb_id: str) -> dict:
    """Load registry search-row metadata for one TTB ID when available."""

    rows = connection.execute(
        """
        SELECT *
        FROM registry_records
        WHERE ttb_id IN (?, ?, ?)
        LIMIT 1
        """,
        candidate_ttb_ids(ttb_id),
    ).fetchall()
    return dict(rows[0]) if rows else {}


def panels_for_application(connection: sqlite3.Connection, ttb_id: str) -> list[PublicColaPanel]:
    """Return downloaded image panels for one application."""

    rows = connection.execute(
        """
        SELECT *
        FROM attachments
        WHERE ttb_id IN (?, ?, ?)
          AND http_status = 200
          AND raw_image_path IS NOT NULL
          AND raw_image_path != ''
        ORDER BY panel_order
        """,
        candidate_ttb_ids(ttb_id),
    ).fetchall()
    panels: list[PublicColaPanel] = []
    for row in rows:
        raw_image_path = resolve_work_path(row["raw_image_path"])
        if not raw_image_path.exists() or not is_valid_image_path(raw_image_path):
            continue
        panels.append(
            PublicColaPanel(
                ttb_id=clean_ttb_id(row["ttb_id"]),
                panel_order=int(row["panel_order"]),
                filename=row["filename"] or raw_image_path.name,
                image_type=row["image_type"] or "",
                raw_image_path=raw_image_path,
                source_url=row["source_url"] or "",
            )
        )
    return panels


def resolve_work_path(value: str | None) -> Path:
    """Resolve host/container paths stored in the local ETL database.

    Notes
    -----
    The SQLite database is intentionally local and gitignored. It may contain
    absolute paths from the host workspace, while Docker/Podman runs mount
    ``data/work`` at ``/app/data/work``. When a stored path contains the
    ``data/work/public-cola`` suffix, remap it to the current process's
    configured public-COLA work directory.
    """

    raw = Path(value or "")
    if raw.exists():
        return raw

    marker = Path("data") / "work" / "public-cola"
    parts = raw.parts
    marker_parts = marker.parts
    marker_len = len(marker_parts)
    for index in range(0, len(parts) - marker_len + 1):
        if parts[index : index + marker_len] == marker_parts:
            relative = Path(*parts[index + marker_len :])
            return PUBLIC_COLA_WORK_DIR / relative
    return raw


def ocr_cache_path(panel: PublicColaPanel) -> Path:
    """Return the stable OCR cache path for one public COLA panel."""

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", panel.raw_image_path.stem).strip("._")
    return PARSED_OCR_DIR / "panels" / panel.ttb_id / f"{panel.panel_order:02d}_{safe_stem}.json"


def load_cached_ocr(path: Path) -> OCRResult | None:
    """Load cached OCR JSON when present and valid."""

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OCRResult(**payload)


def write_cached_ocr(path: Path, ocr: OCRResult) -> None:
    """Persist normalized OCR output under ``data/work``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = ocr.model_dump() if hasattr(ocr, "model_dump") else ocr.dict()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ocr_panel(
    panel: PublicColaPanel,
    *,
    engine: DoctrOCREngine,
    force: bool = False,
    cached_only: bool = False,
) -> PanelOCR | None:
    """Run or load OCR for one panel without making network requests."""

    cache_path = ocr_cache_path(panel)
    if not force:
        cached = load_cached_ocr(cache_path)
        if cached is not None:
            return PanelOCR(panel=panel, ocr=cached, cache_hit=True)
    if cached_only:
        return None

    ocr = engine.run(panel.raw_image_path, fixture_id=panel.ttb_id)
    if not ocr.source.startswith("local docTR unavailable"):
        write_cached_ocr(cache_path, ocr)
    return PanelOCR(panel=panel, ocr=ocr, cache_hit=False)


def aggregate_text(panel_ocrs: list[PanelOCR]) -> str:
    """Join panel OCR text while retaining panel boundaries in the text."""

    chunks: list[str] = []
    for panel_ocr in panel_ocrs:
        text = panel_ocr.ocr.full_text.strip()
        if not text:
            continue
        chunks.append(
            "\n".join(
                [
                    f"[Panel {panel_ocr.panel.panel_order}: {panel_ocr.panel.image_type or 'label'}]",
                    text,
                ]
            )
        )
    return "\n\n".join(chunks)


def expected_fields(parsed: dict, registry: dict) -> dict[str, str]:
    """Derive field expectations from parsed public application data."""

    application = parsed.get("application", {})
    form_fields = parsed.get("form_fields", {})
    source_of_product = form_fields.get("source_of_product", "")
    imported = application.get("imported") or source_of_product.lower() == "imported"
    origin_desc = normalize_value(registry.get("origin_desc", ""))

    applicant_name = first_meaningful_line(form_fields.get("applicant_name_address", ""))
    used_on_label = used_on_label_name(form_fields.get("applicant_name_address", ""))
    applicant_or_producer = used_on_label or applicant_name

    return {
        "brand_name": normalize_value(application.get("brand_name") or form_fields.get("brand_name")),
        "fanciful_name": normalize_value(application.get("fanciful_name") or form_fields.get("fanciful_name")),
        "class_type": normalize_value(application.get("class_type") or form_fields.get("class_type_description")),
        "alcohol_content": normalize_value(application.get("alcohol_content") or form_fields.get("alcohol_content")),
        "net_contents": normalize_value(application.get("net_contents") or form_fields.get("net_contents")),
        "country_of_origin": origin_desc if imported else "",
        "applicant_or_producer": applicant_or_producer,
    }


def first_meaningful_line(value: str) -> str:
    """Return the first non-empty line from a multiline form value."""

    for line in (value or "").splitlines():
        line = normalize_value(line)
        if line:
            return line
    return ""


def used_on_label_name(value: str) -> str:
    """Extract the applicant DBA/name marked as used on the label."""

    match = re.search(r"\n([^\n]+)\s*\(Used on label\)", value or "", re.IGNORECASE)
    return normalize_value(match.group(1)) if match else ""


def field_candidates(field_name: str, expected: str) -> list[str]:
    """Generate tolerant match candidates for one application field."""

    expected = normalize_value(expected)
    if not expected:
        return []

    candidates = [expected]
    if field_name == "alcohol_content":
        number = first_number(expected)
        if number:
            candidates.extend(
                [
                    number,
                    f"{number}%",
                    f"{number} % alcohol",
                    f"{number}% alc",
                    f"{number}% alc/vol",
                    f"{number}% alcohol by volume",
                ]
            )
    elif field_name == "net_contents":
        candidates.extend(net_content_variants(expected))
    elif field_name == "class_type":
        candidates.extend(class_type_variants(expected))
    elif field_name == "country_of_origin":
        candidates.extend([f"Product of {expected}", f"Made in {expected}"])

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def class_type_variants(value: str) -> list[str]:
    """Return practical label-text variants for COLA class/type names.

    Notes
    -----
    Public COLA metadata often stores formal class/type descriptions that are
    more verbose than the label copy. These candidates are OCR-evaluation aids,
    not substitute legal determinations. The compliance layer should still
    route ambiguous class/type evidence to human review.
    """

    text = normalize_label_text(value)
    if not text:
        return []

    variants: list[str] = []
    if text.endswith(" fb"):
        variants.append(text.removesuffix(" fb").strip())
    variants.extend(part.strip() for part in re.split(r"\s+-\s+", text) if part.strip())

    keyword_variants = {
        "straight bourbon whisky": ["straight bourbon whiskey", "bourbon", "whisky", "whiskey"],
        "straight bourbon whiskey": ["bourbon", "whisky", "whiskey"],
        "bourbon": ["bourbon", "whisky", "whiskey"],
        "london dry gin": ["london dry gin", "gin"],
        "gin": ["gin"],
        "vodka": ["vodka"],
        "tequila": ["tequila"],
        "mezcal": ["mezcal"],
        "rum": ["rum"],
        "brandy": ["brandy"],
        "liqueur": ["liqueur", "cordial"],
        "table red wine": ["table wine", "red wine"],
        "table white wine": ["table wine", "white wine"],
        "table wine": ["table wine"],
        "red wine": ["red wine"],
        "white wine": ["white wine"],
        "rose wine": ["rose wine"],
        "sparkling wine": ["sparkling wine"],
        "malt beverage": ["malt beverage", "malt beverages", "beer"],
        "malt beverages": ["malt beverage", "malt beverages", "beer"],
        "beer": ["beer"],
        "ale": ["ale"],
        "porter": ["porter"],
        "stout": ["stout"],
        "hard cider": ["hard cider", "cider"],
    }
    for keyword, additions in keyword_variants.items():
        if keyword in text:
            variants.extend(additions)

    return variants


def first_number(value: str) -> str:
    """Return the first integer/decimal number in a string."""

    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return match.group(0) if match else ""


def net_content_variants(value: str) -> list[str]:
    """Return common net-contents variants for fuzzy OCR matching."""

    text = normalize_label_text(value)
    variants: list[str] = []
    number = first_number(value)
    if not number:
        return variants
    if "milliliter" in text or "ml" in text:
        variants.extend([f"{number} ml", f"{number}ml", f"{number} milliliters", f"{number} milliliter"])
    if "liter" in text or re.search(r"\bl\b", text):
        variants.extend([f"{number} l", f"{number}l", f"{number} liter", f"{number} liters"])
    if "pint" in text:
        variants.extend([f"{number} pint", f"{number} pints"])
    if "fluid ounce" in text or "fl oz" in text or re.search(r"\boz\b", text):
        variants.extend(
            [
                f"{number} fl oz",
                f"{number} fl. oz.",
                f"{number} fluid ounce",
                f"{number} fluid ounces",
                f"{number} oz",
                f"{number}oz",
            ]
        )
    if "gallon" in text or "gal" in text:
        variants.extend([f"{number} gal", f"{number} gallon", f"{number} gallons"])
    return variants


def evaluate_field(
    *,
    ttb_id: str,
    field_name: str,
    expected: str,
    panel_ocrs: list[PanelOCR],
    pass_threshold: float = 90.0,
    review_threshold: float = 75.0,
) -> FieldEvaluation:
    """Evaluate one expected application field against all panel OCR text."""

    candidates = field_candidates(field_name, expected)
    if not candidates:
        return FieldEvaluation(
            ttb_id=ttb_id,
            field_name=field_name,
            expected="",
            verdict="not_applicable",
            outcome="no_expected_value",
            score=0.0,
            best_panel_order=None,
            best_panel_type=None,
            best_panel_filename=None,
            evidence_text="",
            reviewer_action="No application value was available for this field.",
        )

    best_score = 0.0
    best_panel: PublicColaPanel | None = None
    best_text = ""
    for panel_ocr in panel_ocrs:
        text = panel_ocr.ocr.full_text or ""
        for candidate in candidates:
            score = fuzzy_score(candidate, text)
            if score > best_score:
                best_score = score
                best_panel = panel_ocr.panel
                best_text = text

    if best_score >= pass_threshold:
        verdict = "pass"
        outcome = "matched"
        action = "No reviewer action needed for this field."
    elif best_score >= review_threshold:
        verdict = "needs_review"
        outcome = "ambiguous_match"
        action = "Review this field manually; OCR found a partial or ambiguous match."
    else:
        verdict = "needs_review"
        outcome = "not_found"
        action = "Review this field manually; OCR did not find strong label evidence."

    return FieldEvaluation(
        ttb_id=ttb_id,
        field_name=field_name,
        expected=normalize_value(expected),
        verdict=verdict,
        outcome=outcome,
        score=round(best_score, 2),
        best_panel_order=best_panel.panel_order if best_panel else None,
        best_panel_type=best_panel.image_type if best_panel else None,
        best_panel_filename=best_panel.filename if best_panel else None,
        evidence_text=best_text[:500],
        reviewer_action=action,
    )


def evaluate_application(
    *,
    parsed_path: Path,
    connection: sqlite3.Connection,
    engine: DoctrOCREngine,
    force_ocr: bool = False,
    cached_only: bool = False,
) -> ApplicationEvaluation | None:
    """Evaluate one public COLA application across all downloaded panels."""

    parsed = parse_json(parsed_path)
    ttb_id = ttb_id_from_parsed(parsed_path, parsed)
    registry = registry_record(connection, ttb_id)
    panels = panels_for_application(connection, ttb_id)
    if not panels:
        return None

    started = perf_counter()
    panel_ocrs = [
        panel_ocr
        for panel in panels
        if (panel_ocr := ocr_panel(panel, engine=engine, force=force_ocr, cached_only=cached_only))
        is not None
    ]
    if not panel_ocrs:
        return None

    fields = expected_fields(parsed, registry)
    field_results = [
        evaluate_field(
            ttb_id=ttb_id,
            field_name=field_name,
            expected=fields[field_name],
            panel_ocrs=panel_ocrs,
        )
        for field_name in PRIMARY_FIELDS
    ]
    actionable_results = [item for item in field_results if item.verdict != "not_applicable"]
    overall = (
        "pass"
        if actionable_results and all(item.verdict == "pass" for item in actionable_results)
        else "needs_review"
    )
    elapsed_ms = int((perf_counter() - started) * 1000)
    ocr_ms = sum(item.ocr.total_ms for item in panel_ocrs) or elapsed_ms

    form_fields = parsed.get("form_fields", {})
    return ApplicationEvaluation(
        ttb_id=ttb_id,
        status=form_fields.get("status", ""),
        source_of_product=form_fields.get("source_of_product", ""),
        image_count=len(panels),
        ocr_image_count=len(panel_ocrs),
        cache_hit_count=sum(1 for item in panel_ocrs if item.cache_hit),
        total_ocr_ms=ocr_ms,
        overall_verdict=overall,
        field_results=field_results,
    )


def summarize(evaluations: list[ApplicationEvaluation]) -> dict:
    """Aggregate application and field-level evaluation metrics."""

    field_summary: dict[str, dict[str, object]] = {}
    for field_name in PRIMARY_FIELDS:
        results = [
            result
            for evaluation in evaluations
            for result in evaluation.field_results
            if result.field_name == field_name and result.verdict != "not_applicable"
        ]
        matched = sum(1 for result in results if result.verdict == "pass")
        needs_review = sum(1 for result in results if result.verdict == "needs_review")
        scores = [result.score for result in results]
        field_summary[field_name] = {
            "attempted": len(results),
            "matched": matched,
            "needs_review": needs_review,
            "match_rate": round(matched / len(results), 4) if results else None,
            "mean_score": round(mean(scores), 2) if scores else None,
        }

    total_apps = len(evaluations)
    total_images = sum(item.ocr_image_count for item in evaluations)
    total_cache_hits = sum(item.cache_hit_count for item in evaluations)
    latencies = [item.total_ocr_ms for item in evaluations if item.total_ocr_ms is not None]
    return {
        "application_count": total_apps,
        "pass_count": sum(1 for item in evaluations if item.overall_verdict == "pass"),
        "needs_review_count": sum(1 for item in evaluations if item.overall_verdict == "needs_review"),
        "image_count": total_images,
        "cache_hit_count": total_cache_hits,
        "field_summary": field_summary,
        "latency_ms": {
            "mean_per_application": round(mean(latencies), 2) if latencies else None,
            "max_per_application": max(latencies) if latencies else None,
        },
    }


def write_outputs(output_dir: Path, evaluations: list[ApplicationEvaluation]) -> dict:
    """Write JSON and CSV outputs for an evaluation run."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(evaluations)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_dir / "applications.json").write_text(
        json.dumps([application_to_dict(item) for item in evaluations], indent=2) + "\n",
        encoding="utf-8",
    )
    write_field_csv(output_dir / "field_results.csv", evaluations)
    write_application_csv(output_dir / "application_results.csv", evaluations)
    return summary


def application_to_dict(evaluation: ApplicationEvaluation) -> dict:
    """Convert a nested dataclass evaluation to a JSON-serializable dict."""

    payload = asdict(evaluation)
    payload["field_results"] = [asdict(item) for item in evaluation.field_results]
    return payload


def write_field_csv(path: Path, evaluations: list[ApplicationEvaluation]) -> None:
    """Write one row per field comparison."""

    fieldnames = [
        "ttb_id",
        "field_name",
        "expected",
        "verdict",
        "outcome",
        "score",
        "best_panel_order",
        "best_panel_type",
        "best_panel_filename",
        "reviewer_action",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for evaluation in evaluations:
            for result in evaluation.field_results:
                writer.writerow({field: getattr(result, field) for field in fieldnames})


def write_application_csv(path: Path, evaluations: list[ApplicationEvaluation]) -> None:
    """Write one row per application-level evaluation."""

    fieldnames = [
        "ttb_id",
        "status",
        "source_of_product",
        "image_count",
        "ocr_image_count",
        "cache_hit_count",
        "total_ocr_ms",
        "overall_verdict",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for evaluation in evaluations:
            writer.writerow({field: getattr(evaluation, field) for field in fieldnames})
