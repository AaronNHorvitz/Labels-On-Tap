"""Fixture OCR adapter with local docTR fallback."""

from __future__ import annotations

from pathlib import Path

from app.config import DEMO_FIXTURE_DIR
from app.schemas.ocr import OCRResult
from app.services.fixture_loader import load_fixture_ocr
from app.services.ocr.doctr_engine import DoctrOCREngine


class FixtureOCREngine:
    """Load deterministic OCR text for known fixtures before using docTR.

    Notes
    -----
    The fixture path is not pretending to be real OCR. It marks the source as
    ``fixture ground truth`` so the UI and tests can distinguish deterministic
    demo data from local docTR output.
    """

    def __init__(self) -> None:
        """Initialize the fallback docTR adapter."""

        self.doctr = DoctrOCREngine()

    def run(self, image_path: Path, fixture_id: str | None = None) -> OCRResult:
        """Return fixture OCR ground truth or run local docTR.

        Parameters
        ----------
        image_path:
            Image path to process when no fixture OCR sidecar exists.
        fixture_id:
            Optional fixture identifier. When omitted, the image stem is used.

        Returns
        -------
        OCRResult
            Fixture ground-truth OCR or normalized local docTR output.
        """

        detected_fixture = fixture_id or image_path.stem
        ocr_path = DEMO_FIXTURE_DIR / f"{detected_fixture}.ocr_text.json"
        if ocr_path.exists():
            return load_fixture_ocr(detected_fixture)
        return self.doctr.run(image_path, fixture_id=fixture_id)
