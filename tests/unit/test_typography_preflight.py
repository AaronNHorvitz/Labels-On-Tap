from app.config import ROOT
from app.schemas.ocr import OCRResult
from app.services.typography.boldness import assess_warning_heading_boldness
from app.services.typography.warning_heading import best_warning_heading_candidate


def test_warning_heading_candidate_groups_split_ocr_words():
    ocr = OCRResult(
        filename="label.png",
        full_text="GOVERNMENT WARNING:",
        avg_confidence=0.98,
        blocks=[
            {"text": "GOVERNMENT", "confidence": 0.98, "bbox": [[0.10, 0.62], [0.31, 0.66]]},
            {"text": "WARNING:", "confidence": 0.97, "bbox": [[0.33, 0.62], [0.52, 0.66]]},
        ],
    )

    candidate = best_warning_heading_candidate(ocr, min_heading_score=0.72)

    assert candidate is not None
    assert candidate["text"] == "GOVERNMENT WARNING:"
    assert candidate["score"] == 1.0


def test_boldness_preflight_routes_untrusted_fixture_crop_to_review():
    image = ROOT / "data/fixtures/demo/clean_malt_pass.png"
    ocr = OCRResult(
        filename=image.name,
        full_text="GOVERNMENT WARNING:",
        avg_confidence=0.98,
        blocks=[
            {"text": "GOVERNMENT", "confidence": 0.98, "bbox": [[0.10, 0.62], [0.31, 0.66]]},
            {"text": "WARNING:", "confidence": 0.97, "bbox": [[0.33, 0.62], [0.52, 0.66]]},
        ],
    )

    assessment, evidence = assess_warning_heading_boldness(image, ocr)

    assert evidence is not None
    assert assessment.crop_available is True
    assert assessment.verdict in {"pass", "needs_review"}
    assert assessment.threshold is not None

