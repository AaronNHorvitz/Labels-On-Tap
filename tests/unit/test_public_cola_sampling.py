"""Tests for deterministic public COLA sampling helpers."""

from __future__ import annotations

from datetime import date

from scripts.cola_etl.csv_import import normalize_value
from scripts.cola_etl.sampling import (
    choose_sample_days,
    product_family,
    read_excluded_ttb_ids,
    source_bucket,
)


def test_choose_sample_days_is_deterministic() -> None:
    first = choose_sample_days(
        date(2025, 5, 1),
        date(2025, 7, 31),
        seed=20260502,
        days_per_month=3,
    )
    second = choose_sample_days(
        date(2025, 5, 1),
        date(2025, 7, 31),
        seed=20260502,
        days_per_month=3,
    )

    assert first == second
    assert len(first) == 9
    assert sum(item.role == "primary" for item in first) == 6
    assert sum(item.role == "backup" for item in first) == 3


def test_product_family_heuristics_cover_core_types() -> None:
    assert product_family("STRAIGHT BOURBON WHISKY") == "distilled_spirits"
    assert product_family("TABLE RED WINE") == "wine"
    assert product_family("MALT BEVERAGES SPECIALITIES - FLAVORED") == "malt_beverage"


def test_source_bucket_prefers_import_signal() -> None:
    assert source_bucket("TX-I-22193", "MEXICO") == "imported"
    assert source_bucket("DSP-KY-20176", "KENTUCKY") == "domestic"


def test_normalize_value_strips_excel_style_ttb_prefix_quote() -> None:
    assert normalize_value("'25337001000464") == "25337001000464"
    assert normalize_value("'25337001000464'") == "25337001000464"
    assert normalize_value("CORAZÓN DE REY") == "CORAZÓN DE REY"


def test_read_excluded_ttb_ids_accepts_plain_text(tmp_path) -> None:
    exclude_path = tmp_path / "exclude.txt"
    exclude_path.write_text("'25337001000464'\n26035001000229\n", encoding="utf-8")

    assert read_excluded_ttb_ids(str(exclude_path)) == {
        "25337001000464",
        "26035001000229",
    }
