from __future__ import annotations

from pydantic import BaseModel


class OCRTextBlock(BaseModel):
    text: str
    confidence: float = 0.0
    bbox: object | None = None


class OCRResult(BaseModel):
    fixture_id: str | None = None
    filename: str
    full_text: str
    avg_confidence: float = 0.0
    blocks: list[OCRTextBlock] = []
    source: str = "unknown"
    preprocessing_ms: int = 0
    ocr_ms: int = 0
    total_ms: int = 0
