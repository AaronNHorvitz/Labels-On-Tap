"""OCR adapter exports.

Notes
-----
Runtime OCR is intentionally hidden behind a small protocol so deterministic
fixture OCR, local docTR, and future OCR engines can be swapped without changing
the rule layer.
"""

from app.services.ocr.base import OCREngine
from app.services.ocr.fixture_engine import FixtureOCREngine

__all__ = ["OCREngine", "FixtureOCREngine"]
