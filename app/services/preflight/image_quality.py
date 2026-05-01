"""Image/OCR quality helpers."""

from __future__ import annotations

from app.schemas.ocr import OCRResult


def is_low_confidence(ocr: OCRResult, threshold: float) -> bool:
    """Return whether OCR confidence is below the review threshold.

    Parameters
    ----------
    ocr:
        Normalized OCR result.
    threshold:
        Minimum average confidence for deterministic checks.
    """

    return ocr.avg_confidence < threshold
