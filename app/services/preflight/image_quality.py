from __future__ import annotations

from app.schemas.ocr import OCRResult


def is_low_confidence(ocr: OCRResult, threshold: float) -> bool:
    return ocr.avg_confidence < threshold
