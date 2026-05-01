"""Prototype health-claim keyword helper."""

from __future__ import annotations


HEALTH_TERMS = ("detox", "healthy", "safer", "less toxic", "protective")


def health_claim_terms(text: str) -> list[str]:
    """Return configured health-risk terms found in OCR text."""

    lower = text.lower()
    return [term for term in HEALTH_TERMS if term in lower]
