from __future__ import annotations

import json

import pytest

from app.services.manifest_parser import ManifestParseError, parse_manifest


def test_parse_csv_manifest_happy_path():
    content = (
        "filename,fixture_id,product_type,brand_name,class_type,alcohol_content,"
        "net_contents,country_of_origin,imported\n"
        "clean_malt_pass.png,clean_malt_pass,malt_beverage,OLD RIVER BREWING,Ale,"
        "5% ALC/VOL,1 Pint,,false\n"
    ).encode()

    items = parse_manifest("manifest.csv", content)

    assert len(items) == 1
    assert items[0].filename == "clean_malt_pass.png"
    assert items[0].fixture_id == "clean_malt_pass"
    assert items[0].imported is False


def test_parse_json_manifest_happy_path():
    content = json.dumps(
        {
            "items": [
                {
                    "filename": "imported_country_origin_pass.png",
                    "fixture_id": "imported_country_origin_pass",
                    "product_type": "wine",
                    "brand_name": "VALLEY RIDGE",
                    "class_type": "Red Wine",
                    "alcohol_content": "13.5% ALC/VOL",
                    "net_contents": "750 mL",
                    "country_of_origin": "France",
                    "imported": True,
                }
            ]
        }
    ).encode()

    items = parse_manifest("manifest.json", content)

    assert len(items) == 1
    assert items[0].country_of_origin == "France"
    assert items[0].imported is True


def test_parse_manifest_accepts_multi_panel_filenames():
    content = (
        "filename,panel_filenames,product_type,brand_name\n"
        "APP-001,front.png;back.png;neck.png,wine,EXAMPLE WINERY\n"
    ).encode()

    items = parse_manifest("manifest.csv", content)

    assert items[0].filename == "APP-001"
    assert items[0].panel_filenames == ["front.png", "back.png", "neck.png"]


def test_parse_manifest_rejects_missing_required_column():
    with pytest.raises(ManifestParseError, match="missing required columns"):
        parse_manifest("manifest.csv", b"filename,brand_name\nlabel.png,Brand\n")


def test_parse_manifest_rejects_duplicate_filenames():
    content = (
        "filename,product_type,brand_name\n"
        "label.png,malt_beverage,Brand\n"
        "label.png,malt_beverage,Brand\n"
    ).encode()

    with pytest.raises(ManifestParseError, match="duplicate filenames"):
        parse_manifest("manifest.csv", content)


def test_parse_manifest_rejects_invalid_imported_value():
    content = (
        "filename,product_type,brand_name,imported\n"
        "label.png,malt_beverage,Brand,maybe\n"
    ).encode()

    with pytest.raises(ManifestParseError, match="invalid imported value"):
        parse_manifest("manifest.csv", content)
