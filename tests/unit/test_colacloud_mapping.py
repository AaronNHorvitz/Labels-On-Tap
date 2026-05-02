"""Tests for COLA Cloud metadata-to-application field mapping."""

from __future__ import annotations

from scripts.pull_colacloud_api_corpus import format_abv, format_net_contents, parsed_payload


def test_colacloud_api_mapping_populates_abv_and_net_contents() -> None:
    record = {
        "ttb_id": "26023001000815",
        "brand_name": "Example Brand",
        "product_name": "Example Lager",
        "product_type": "Malt Beverage",
        "class_name": "MALT BEVERAGES SPECIALITIES - FLAVORED",
        "domestic_or_imported": "Domestic",
        "origin_name": "KENTUCKY",
        "abv": 4.2,
        "volume": 12.0,
        "volume_unit": "fluid ounces",
    }

    payload = parsed_payload(record)

    assert format_abv(record) == "4.2% ALC/VOL"
    assert format_net_contents(record) == "12 fl oz"
    assert payload["application"]["alcohol_content"] == "4.2% ALC/VOL"
    assert payload["application"]["net_contents"] == "12 fl oz"
    assert payload["form_fields"]["alcohol_content"] == "4.2% ALC/VOL"
    assert payload["form_fields"]["net_contents"] == "12 fl oz"


def test_colacloud_api_mapping_formats_integer_values_cleanly() -> None:
    record = {
        "ttb_id": "26112001000564",
        "abv": 50.0,
        "volume": 750.0,
        "volume_unit": "milliliters",
    }

    assert format_abv(record) == "50% ALC/VOL"
    assert format_net_contents(record) == "750 mL"
