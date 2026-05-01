from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.ocr import OCRResult


class OCREngine(Protocol):
    def run(self, image_path: Path, fixture_id: str | None = None) -> OCRResult:
        ...
