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
    candidates = [expected_country, *ALIASES.get(expected_country, [])]
    return max((fuzzy_score(candidate, text) for candidate in candidates if candidate), default=0.0)


def find_conflicting_country(expected_country: str, text: str) -> str | None:
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
