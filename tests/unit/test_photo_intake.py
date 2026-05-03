from app.schemas.ocr import OCRResult
from app.services.photo_intake import parse_photo_intake


def test_photo_intake_extracts_common_label_candidates():
    ocr = OCRResult(
        filename="store-photo.png",
        full_text=(
            "VALLEY RIDGE\n"
            "Cabernet Sauvignon\n"
            "13.5% ALC/VOL\n"
            "750 mL\n"
            "Product of France\n"
            "GOVERNMENT WARNING: sample warning text"
        ),
        avg_confidence=0.91,
        source="unit-test",
        blocks=[],
    )

    parsed = parse_photo_intake(ocr)
    candidates = {candidate["field"]: candidate["value"] for candidate in parsed["candidates"]}

    assert candidates["brand_name_candidate"] == "VALLEY RIDGE"
    assert candidates["product_type_candidate"] == "wine"
    assert candidates["class_type_candidate"] == "Cabernet Sauvignon"
    assert candidates["alcohol_content_candidate"] == "13.5% ALC/VOL"
    assert candidates["net_contents_candidate"] == "750 mL"
    assert candidates["country_of_origin_candidate"] == "France"
    assert parsed["warning"]["heading_found"] is True
    assert parsed["warning"]["heading_all_caps"] is True
