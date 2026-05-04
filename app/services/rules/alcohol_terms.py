"""Alcohol-content terminology and value-matching helpers."""

from __future__ import annotations

import re


ABV_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*%?\s*(?:A\.?B\.?V\.?|ABV)\b", re.IGNORECASE)
ALCOHOL_PERCENT_PATTERN = re.compile(
    r"\b(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*%?\s*"
    r"(?:alc\.?\s*/?\s*vol\.?|alcohol\s+by\s+volume|by\s+vol\.?|a\.?b\.?v\.?|abv)\b",
    re.IGNORECASE,
)
BARE_PERCENT_PATTERN = re.compile(r"\b(?P<value>\d{1,3}(?:\.\d{1,2})?)\s*%\b")
PROOF_PATTERN = re.compile(r"\b(?P<value>\d{2,3}(?:\.\d+)?)\s*proof\b", re.IGNORECASE)


def contains_abv_shorthand(text: str) -> str | None:
    """Find prohibited ABV shorthand near an alcohol percentage.

    Parameters
    ----------
    text:
        OCR text to scan.

    Returns
    -------
    str | None
        Matched shorthand evidence, or ``None`` when absent.
    """

    match = ABV_PATTERN.search(text)
    return match.group(0) if match else None


def extract_alcohol_values(text: str) -> set[float]:
    """Extract alcohol-by-volume percentages from OCR or application text.

    Parameters
    ----------
    text:
        Text that may contain percent alcohol statements or proof values.

    Returns
    -------
    set[float]
        Alcohol-by-volume percentages. Proof values are converted to ABV by
        dividing by two.
    """

    values: set[float] = set()
    for pattern in (ALCOHOL_PERCENT_PATTERN, BARE_PERCENT_PATTERN):
        for match in pattern.finditer(text):
            value = _safe_float(match.group("value"))
            if value is not None and 0 < value <= 100:
                values.add(round(value, 2))
    for match in PROOF_PATTERN.finditer(text):
        proof = _safe_float(match.group("value"))
        if proof is not None and 0 < proof <= 200:
            values.add(round(proof / 2.0, 2))
    return values


def alcohol_values_match(expected_values: set[float], observed_values: set[float], tolerance: float = 0.05) -> bool:
    """Return whether any expected ABV value appears in observed values."""

    return any(
        abs(expected - observed) <= tolerance
        for expected in expected_values
        for observed in observed_values
    )


def _safe_float(value: str) -> float | None:
    """Parse a numeric string without raising."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
