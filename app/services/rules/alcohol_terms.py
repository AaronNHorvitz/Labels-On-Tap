from __future__ import annotations

import re


ABV_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*%?\s*(?:A\.?B\.?V\.?|ABV)\b", re.IGNORECASE)


def contains_abv_shorthand(text: str) -> str | None:
    match = ABV_PATTERN.search(text)
    return match.group(0) if match else None
