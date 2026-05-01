from __future__ import annotations

from pathlib import Path

from app.config import DEMO_FIXTURE_DIR
from app.schemas.ocr import OCRResult
from app.services.fixture_loader import load_fixture_ocr
from app.services.ocr.doctr_engine import DoctrOCREngine


class FixtureOCREngine:
    def __init__(self) -> None:
        self.doctr = DoctrOCREngine()

    def run(self, image_path: Path, fixture_id: str | None = None) -> OCRResult:
        detected_fixture = fixture_id or image_path.stem
        ocr_path = DEMO_FIXTURE_DIR / f"{detected_fixture}.ocr_text.json"
        if ocr_path.exists():
            return load_fixture_ocr(detected_fixture)
        return self.doctr.run(image_path, fixture_id=fixture_id)
