"""Fuzzy field-matching helpers."""

from __future__ import annotations

import re
import unicodedata


try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback only when optional dep missing
    fuzz = None


def normalize_label_text(value: str) -> str:
    """Normalize OCR/application text for fuzzy matching.

    Notes
    -----
    This intentionally removes punctuation and case differences because fields
    like brand name should tolerate cosmetic differences such as
    ``OLD RIVER`` versus ``Old River``.
    """

    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.replace("'", "'").replace("'", "'")
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def fuzzy_score(expected: str, observed: str) -> float:
    """Return a fuzzy partial-match score.

    Parameters
    ----------
    expected:
        Application field value.
    observed:
        OCR text or OCR text window.

    Returns
    -------
    float
        Score from ``0`` to ``100``. Uses RapidFuzz when available and a simple
        token-overlap fallback otherwise.
    """

    expected_norm = normalize_label_text(expected)
    observed_norm = normalize_label_text(observed)
    if not expected_norm or not observed_norm:
        return 0.0
    if fuzz is not None:
        return float(fuzz.partial_ratio(expected_norm, observed_norm))

    expected_terms = set(expected_norm.split())
    observed_terms = set(observed_norm.split())
    overlap = expected_terms & observed_terms
    return 100.0 * len(overlap) / max(len(expected_terms), 1)
