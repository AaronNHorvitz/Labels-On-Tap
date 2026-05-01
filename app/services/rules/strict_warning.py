"""Government warning extraction and strict comparison helpers."""

from __future__ import annotations

import re


CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health problems."
)


def normalize_whitespace(value: str) -> str:
    """Collapse whitespace without changing punctuation or capitalization."""

    return re.sub(r"\s+", " ", value).strip()


def extract_warning_block(full_text: str) -> str | None:
    """Extract the government warning block from OCR text.

    Notes
    -----
    This deliberately normalizes whitespace only. Punctuation and capitalization
    remain meaningful for strict warning comparison.
    """

    match = re.search(r"(government\s+warning\s*:.*)", full_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return normalize_whitespace(match.group(1))


def warning_heading(full_text: str) -> str | None:
    """Return the warning heading text as it appears in OCR."""

    match = re.search(r"government\s+warning\s*:", full_text, flags=re.IGNORECASE)
    return match.group(0) if match else None
