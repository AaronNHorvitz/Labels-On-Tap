"""Protocol for OCR adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.ocr import OCRResult


class OCREngine(Protocol):
    """Interface implemented by OCR engines.

    Notes
    -----
    The rule engine consumes normalized ``OCRResult`` objects so fixture OCR and
    local docTR can be swapped without changing validation logic.
    """

    def run(self, image_path: Path, fixture_id: str | None = None) -> OCRResult:
        """Run OCR for an image path.

        Parameters
        ----------
        image_path:
            Path to a local image file.
        fixture_id:
            Optional fixture identifier used by deterministic test/demo paths.
        """

        ...
