"""Country-of-origin matching helpers."""

from __future__ import annotations

from app.services.rules.field_matching import fuzzy_score, normalize_label_text


COUNTRY_NAMES = [
    "Argentina",
    "Australia",
    "Austria",
    "Brazil",
    "Canada",
    "Chile",
    "England",
    "France",
    "Germany",
    "Greece",
    "Ireland",
    "Italy",
    "Japan",
    "Mexico",
    "New Zealand",
    "Portugal",
    "Scotland",
    "South Africa",
    "Spain",
    "United States",
]


ALIASES = {
    "United States": ["USA", "U.S.A.", "United States of America"],
}


def country_match_score(expected_country: str, text: str) -> float:
    """Score the expected country against OCR text.

    Parameters
    ----------
    expected_country:
        Country declared in the application.
    text:
        OCR text extracted from the label.

    Returns
    -------
    float
        Fuzzy match score from ``0`` to ``100``.
    """

    candidates = [expected_country, *ALIASES.get(expected_country, [])]
    return max((fuzzy_score(candidate, text) for candidate in candidates if candidate), default=0.0)


def find_conflicting_country(expected_country: str, text: str) -> str | None:
    """Find a clear conflicting country mentioned in OCR text.

    Notes
    -----
    The conflict detector is intentionally conservative and only searches a
    curated country-name list. Missing expected country routes to Needs Review;
    a different detected country can become a Fail when OCR confidence is high.
    """

    normalized_text = f" {normalize_label_text(text)} "
    expected_terms = {
        normalize_label_text(expected_country),
        *(normalize_label_text(alias) for alias in ALIASES.get(expected_country, [])),
    }
    for country in COUNTRY_NAMES:
        country_norm = normalize_label_text(country)
        if country_norm in expected_terms:
            continue
        if f" {country_norm} " in normalized_text:
            return country
    return None
