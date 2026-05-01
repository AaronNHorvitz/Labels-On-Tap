"""Alcohol terminology rule helpers."""

from __future__ import annotations

import re


ABV_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*%?\s*(?:A\.?B\.?V\.?|ABV)\b", re.IGNORECASE)


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
