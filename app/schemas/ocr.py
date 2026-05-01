"""OCR payload schemas shared by docTR and fixture OCR engines."""

from __future__ import annotations

from pydantic import BaseModel


class OCRTextBlock(BaseModel):
    """Recognized OCR text fragment.

    Attributes
    ----------
    text:
        OCR token or line text.
    confidence:
        Engine confidence normalized to ``0.0`` through ``1.0`` when available.
    bbox:
        Optional engine-provided geometry. The prototype stores it opaquely
        because fixture OCR and docTR use different native structures.
    """

    text: str
    confidence: float = 0.0
    bbox: object | None = None


class OCRResult(BaseModel):
    """Normalized OCR result consumed by the rule engine.

    Notes
    -----
    ``source`` is intentionally visible in the UI so reviewers can distinguish
    deterministic fixture ground truth from local docTR output.
    """

    fixture_id: str | None = None
    filename: str
    full_text: str
    avg_confidence: float = 0.0
    blocks: list[OCRTextBlock] = []
    source: str = "unknown"
    preprocessing_ms: int = 0
    ocr_ms: int = 0
    total_ms: int = 0
