"""Demonstration-only OCR field extraction for free-form label photos.

The normal Labels On Tap workflow compares OCR evidence against application
fields. This module handles the narrower demo case where a user uploads a
real-world shelf/bottle photo and wants to see what the OCR layer can extract
before any COLA-style application fields are supplied.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.schemas.ocr import OCRResult
from app.services.rules.strict_warning import CANONICAL_WARNING, extract_warning_block, normalize_whitespace


ABV_RE = re.compile(
    r"\b(?:alcohol\s*)?(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*%?\s*"
    r"(?P<label>alc\.?\s*/?\s*vol\.?|alcohol\s+by\s+volume|abv|a\.?b\.?v\.?|by\s+vol\.?)\b",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*%\b")
PROOF_RE = re.compile(r"\b(?P<proof>\d{2,3}(?:\.\d+)?)\s*proof\b", re.IGNORECASE)
NET_CONTENTS_RE = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|mL|milliliters?|l|liters?|litres?|fl\.?\s*oz\.?|fluid\s+ounces?|oz\.?|pints?|pt\.?|gallons?|gal\.?)\b",
    re.IGNORECASE,
)

CLASS_TERMS = [
    "ale",
    "beer",
    "lager",
    "stout",
    "porter",
    "ipa",
    "wine",
    "red wine",
    "white wine",
    "table wine",
    "sparkling wine",
    "cabernet",
    "chardonnay",
    "merlot",
    "pinot",
    "riesling",
    "bourbon",
    "whiskey",
    "whisky",
    "vodka",
    "gin",
    "rum",
    "tequila",
    "mezcal",
    "brandy",
    "liqueur",
    "hard cider",
]

COUNTRY_NAMES = [
    "argentina",
    "australia",
    "austria",
    "canada",
    "chile",
    "france",
    "germany",
    "ireland",
    "italy",
    "japan",
    "mexico",
    "new zealand",
    "portugal",
    "scotland",
    "south africa",
    "spain",
    "united kingdom",
]

BRAND_EXCLUSION_RE = re.compile(
    r"(government warning|net contents|alc|alcohol|surgeon general|pregnancy|birth defects|contains sulfites)",
    re.IGNORECASE,
)


@dataclass
class ExtractedCandidate:
    """One extracted photo-intake candidate field."""

    field: str
    value: str
    confidence: float
    evidence: str
    method: str


def parse_photo_intake(ocr: OCRResult) -> dict[str, Any]:
    """Parse likely label fields from OCR text.

    Parameters
    ----------
    ocr:
        Normalized OCR result from fixture OCR or the local OCR adapter.

    Returns
    -------
    dict
        Demonstration payload containing candidate fields, warning signals,
        extracted lines, and caveats.

    Notes
    -----
    This parser is intentionally conservative. It helps demonstrate raw OCR
    extraction from phone photos, but it does not verify a COLA submission unless
    application fields are supplied separately.
    """

    lines = extract_text_lines(ocr)
    text = "\n".join(lines).strip() or ocr.full_text
    candidates: list[ExtractedCandidate] = []

    brand = candidate_brand(lines)
    if brand:
        candidates.append(brand)

    product_type = candidate_product_type(text)
    if product_type:
        candidates.append(product_type)

    class_type = candidate_class_type(lines, text)
    if class_type:
        candidates.append(class_type)

    abv = candidate_alcohol_content(text)
    if abv:
        candidates.append(abv)

    net_contents = candidate_net_contents(text)
    if net_contents:
        candidates.append(net_contents)

    origin = candidate_country_origin(text)
    if origin:
        candidates.append(origin)

    warning = warning_signals(text)
    return {
        "filename": ocr.filename,
        "ocr_source": ocr.source,
        "avg_confidence": ocr.avg_confidence,
        "ocr_ms": ocr.ocr_ms,
        "total_ms": ocr.total_ms,
        "candidates": [asdict(candidate) for candidate in candidates],
        "warning": warning,
        "lines": lines[:40],
        "full_text": ocr.full_text,
        "caveats": [
            "Photo intake is an OCR extraction aid, not a COLA verification result.",
            "Verification still requires application fields or a batch manifest.",
            "Candidate fields should be reviewed before being used in the normal verification workflow.",
        ],
    }


def extract_text_lines(ocr: OCRResult) -> list[str]:
    """Return readable OCR lines, using geometry when available."""

    blocks = list(ocr.blocks or [])
    if blocks and all(_block_sort_key(block) is not None for block in blocks):
        sorted_blocks = sorted(blocks, key=lambda block: _block_sort_key(block) or (0.0, 0.0))
        rows: list[list[tuple[float, str]]] = []
        row_y: list[float] = []
        for block in sorted_blocks:
            key = _block_sort_key(block)
            if key is None:
                continue
            y, x = key
            text = _clean_line(block.text)
            if not text:
                continue
            for index, existing_y in enumerate(row_y):
                if abs(y - existing_y) <= 0.015:
                    rows[index].append((x, text))
                    break
            else:
                row_y.append(y)
                rows.append([(x, text)])
        lines = [" ".join(text for _, text in sorted(row)) for row in rows]
        return [_clean_line(line) for line in lines if _clean_line(line)]

    block_lines = [_clean_line(block.text) for block in blocks if _clean_line(block.text)]
    if block_lines:
        return block_lines
    return [_clean_line(line) for line in ocr.full_text.splitlines() if _clean_line(line)]


def candidate_brand(lines: list[str]) -> ExtractedCandidate | None:
    """Infer a likely brand candidate from prominent early OCR lines."""

    for line in lines[:8]:
        if BRAND_EXCLUSION_RE.search(line):
            continue
        if NET_CONTENTS_RE.search(line) or ABV_RE.search(line):
            continue
        if len(line) < 3 or len(line) > 80:
            continue
        if sum(ch.isalpha() for ch in line) < 3:
            continue
        if line.lower() in CLASS_TERMS:
            continue
        return ExtractedCandidate(
            field="brand_name_candidate",
            value=line,
            confidence=0.55,
            evidence=line,
            method="first prominent OCR line after excluding regulatory/numeric text",
        )
    return None


def candidate_product_type(text: str) -> ExtractedCandidate | None:
    """Infer broad product type from obvious beverage terms."""

    lower = text.lower()
    if any(term in lower for term in ["whiskey", "whisky", "vodka", "gin", "rum", "tequila", "mezcal", "bourbon", "brandy"]):
        value = "distilled_spirits"
    elif any(term in lower for term in ["beer", "ale", "lager", "stout", "porter", "ipa"]):
        value = "malt_beverage"
    elif "wine" in lower or any(term in lower for term in ["chardonnay", "cabernet", "merlot", "pinot", "riesling"]):
        value = "wine"
    else:
        return None
    return ExtractedCandidate(
        field="product_type_candidate",
        value=value,
        confidence=0.6,
        evidence=_evidence_window(text, value.replace("_", " ")),
        method="keyword map from OCR text",
    )


def candidate_class_type(lines: list[str], text: str) -> ExtractedCandidate | None:
    """Infer a likely class/type phrase from known beverage terms."""

    for line in lines:
        lower = line.lower()
        if any(term in lower for term in CLASS_TERMS):
            return ExtractedCandidate(
                field="class_type_candidate",
                value=line,
                confidence=0.62,
                evidence=line,
                method="line containing beverage class/type keyword",
            )
    lower_text = text.lower()
    for term in CLASS_TERMS:
        if term in lower_text:
            return ExtractedCandidate(
                field="class_type_candidate",
                value=term.title(),
                confidence=0.45,
                evidence=_evidence_window(text, term),
                method="keyword found in OCR text",
            )
    return None


def candidate_alcohol_content(text: str) -> ExtractedCandidate | None:
    """Extract likely alcohol-content wording."""

    match = ABV_RE.search(text)
    if match:
        return ExtractedCandidate(
            field="alcohol_content_candidate",
            value=normalize_whitespace(match.group(0)),
            confidence=0.82,
            evidence=_evidence_window(text, match.group(0)),
            method="ABV/alcohol-by-volume regex",
        )
    match = PERCENT_RE.search(text)
    if match:
        return ExtractedCandidate(
            field="alcohol_content_candidate",
            value=f"{match.group('value')}%",
            confidence=0.55,
            evidence=_evidence_window(text, match.group(0)),
            method="bare percentage regex",
        )
    proof_match = PROOF_RE.search(text)
    if proof_match:
        proof = float(proof_match.group("proof"))
        return ExtractedCandidate(
            field="alcohol_content_candidate",
            value=f"{proof_match.group('proof')} proof (~{proof / 2:g}% ALC/VOL)",
            confidence=0.65,
            evidence=_evidence_window(text, proof_match.group(0)),
            method="proof regex with approximate ABV conversion",
        )
    return None


def candidate_net_contents(text: str) -> ExtractedCandidate | None:
    """Extract likely net-contents wording."""

    match = NET_CONTENTS_RE.search(text)
    if not match:
        return None
    return ExtractedCandidate(
        field="net_contents_candidate",
        value=normalize_whitespace(match.group(0)),
        confidence=0.75,
        evidence=_evidence_window(text, match.group(0)),
        method="net-contents unit regex",
    )


def candidate_country_origin(text: str) -> ExtractedCandidate | None:
    """Extract a likely country-of-origin candidate."""

    lower = text.lower()
    for country in COUNTRY_NAMES:
        if country in lower:
            return ExtractedCandidate(
                field="country_of_origin_candidate",
                value=country.title(),
                confidence=0.55,
                evidence=_evidence_window(text, country),
                method="country-name keyword scan",
            )
    return None


def warning_signals(text: str) -> dict[str, Any]:
    """Report government-warning signals from free-form OCR text."""

    warning = extract_warning_block(text)
    exact = bool(warning and normalize_whitespace(warning) == CANONICAL_WARNING)
    heading_caps = "GOVERNMENT WARNING:" in text
    return {
        "heading_found": bool(re.search(r"government\s+warning\s*:", text, flags=re.IGNORECASE)),
        "heading_all_caps": heading_caps,
        "canonical_text_exact": exact,
        "evidence": warning or "",
    }


def _clean_line(value: str) -> str:
    return normalize_whitespace(value)


def _block_sort_key(block: Any) -> tuple[float, float] | None:
    bbox = block.bbox
    if not bbox:
        return None
    try:
        x0, y0 = bbox[0]
        return float(y0), float(x0)
    except (TypeError, ValueError, IndexError):
        return None


def _evidence_window(text: str, needle: str, radius: int = 60) -> str:
    lower_text = text.lower()
    lower_needle = needle.lower()
    index = lower_text.find(lower_needle)
    if index < 0:
        return normalize_whitespace(text[: radius * 2])
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return normalize_whitespace(text[start:end])
