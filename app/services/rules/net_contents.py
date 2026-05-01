from __future__ import annotations

import re


SIXTEEN_OZ_PATTERN = re.compile(r"\b16\s*(?:fl\.?\s*)?(?:oz\.?|ounces?)\b", re.IGNORECASE)
ONE_PINT_PATTERN = re.compile(r"\b1\s*pint\b", re.IGNORECASE)


def has_bad_malt_16oz_statement(text: str) -> bool:
    return bool(SIXTEEN_OZ_PATTERN.search(text)) and not ONE_PINT_PATTERN.search(text)
