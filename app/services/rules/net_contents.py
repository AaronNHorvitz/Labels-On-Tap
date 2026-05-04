"""Net-contents rule helpers."""

from __future__ import annotations

import re


SIXTEEN_OZ_PATTERN = re.compile(r"\b16\s*(?:fl\.?\s*)?(?:oz\.?|ounces?)\b", re.IGNORECASE)
ONE_PINT_PATTERN = re.compile(r"\b1\s*pint\b", re.IGNORECASE)
NET_CONTENTS_PATTERN = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|mL|milliliters?|millilitres?|l|liters?|litres?|fl\.?\s*oz\.?|fluid\s+ounces?|"
    r"pints?|pt\.?|quarts?|qt\.?|gallons?|gal\.?)\b",
    re.IGNORECASE,
)

UNIT_TO_ML = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "millilitre": 1.0,
    "millilitres": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "fl oz": 29.5735295625,
    "fl. oz": 29.5735295625,
    "fl. oz.": 29.5735295625,
    "fluid ounce": 29.5735295625,
    "fluid ounces": 29.5735295625,
    "oz": 29.5735295625,
    "oz.": 29.5735295625,
    "pint": 473.176473,
    "pints": 473.176473,
    "pt": 473.176473,
    "pt.": 473.176473,
    "quart": 946.352946,
    "quarts": 946.352946,
    "qt": 946.352946,
    "qt.": 946.352946,
    "gallon": 3785.411784,
    "gallons": 3785.411784,
    "gal": 3785.411784,
    "gal.": 3785.411784,
}


def has_bad_malt_16oz_statement(text: str) -> bool:
    """Detect malt beverage ``16 fl. oz.`` wording without ``1 Pint``.

    Parameters
    ----------
    text:
        OCR text extracted from the label.

    Returns
    -------
    bool
        ``True`` when the problematic 16-ounce expression appears without the
        expected pint expression.
    """

    return bool(SIXTEEN_OZ_PATTERN.search(text)) and not ONE_PINT_PATTERN.search(text)


def extract_net_content_values(text: str) -> list[tuple[float, str]]:
    """Extract normalized net-content quantities.

    Parameters
    ----------
    text:
        OCR or application text.

    Returns
    -------
    list[tuple[float, str]]
        Tuples of ``(milliliters, original_evidence)``.
    """

    values: list[tuple[float, str]] = []
    for match in NET_CONTENTS_PATTERN.finditer(text):
        amount = _safe_float(match.group("amount"))
        unit = _normalize_unit(match.group("unit"))
        factor = UNIT_TO_ML.get(unit)
        if amount is None or factor is None:
            continue
        values.append((amount * factor, match.group(0)))
    return values


def net_contents_match(expected_values: list[tuple[float, str]], observed_values: list[tuple[float, str]]) -> bool:
    """Return whether any expected quantity matches observed label evidence.

    Notes
    -----
    A small tolerance handles OCR punctuation/spacing differences and common
    metric/US-customary round trips without pretending that very different
    package sizes are equivalent.
    """

    for expected, _ in expected_values:
        for observed, _ in observed_values:
            tolerance = max(2.0, expected * 0.01)
            if abs(expected - observed) <= tolerance:
                return True
    return False


def _normalize_unit(unit: str) -> str:
    """Normalize unit spelling for lookup."""

    return re.sub(r"\s+", " ", unit.lower().replace(".", ".")).strip()


def _safe_float(value: str) -> float | None:
    """Parse a numeric string without raising."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
