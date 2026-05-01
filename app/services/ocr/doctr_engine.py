"""Local docTR OCR adapter.

Notes
-----
docTR is optional at import time because the evaluator demos and unit tests use
fixture OCR. When docTR cannot be imported or initialized, the adapter returns a
low-confidence ``OCRResult`` instead of crashing the request.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from app.schemas.ocr import OCRResult


class DoctrOCREngine:
    """Lazy-loading docTR engine wrapper."""

    def __init__(self) -> None:
        """Initialize the wrapper without loading model weights."""

        self._model = None
        self._error: str | None = None

    def _load_model(self):
        """Load and cache the docTR OCR predictor.

        Raises
        ------
        RuntimeError
            Raised when docTR or one of its runtime dependencies is unavailable.

        Notes
        -----
        Model loading is delayed until the first real OCR call so fixture demos
        stay fast and deterministic.
        """

        if self._model is not None:
            return self._model
        if self._error:
            raise RuntimeError(self._error)
        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
        except Exception as exc:  # pragma: no cover - depends on optional OCR install
            self._error = f"docTR unavailable: {exc}"
            raise RuntimeError(self._error) from exc
        self._document_file = DocumentFile
        self._model = ocr_predictor(pretrained=True)
        return self._model

    def run(self, image_path: Path, fixture_id: str | None = None) -> OCRResult:
        """Run local OCR and normalize docTR output.

        Parameters
        ----------
        image_path:
            Image to process.
        fixture_id:
            Optional fixture identifier for traceability.

        Returns
        -------
        OCRResult
            Normalized full text, confidence, blocks, source, and timing data.

        Notes
        -----
        Runtime OCR failures intentionally become low-confidence OCR results.
        The rule engine then routes the item to Needs Review rather than
        failing the whole web request.
        """

        started = perf_counter()
        try:
            model = self._load_model()
            document = self._document_file.from_images(str(image_path))
            result = model(document)
            exported = result.export()
            words: list[dict] = []
            for page in exported.get("pages", []):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        for word in line.get("words", []):
                            words.append(word)
            text = " ".join(word.get("value", "") for word in words).strip()
            confidences = [float(word.get("confidence", 0)) for word in words]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            total_ms = int((perf_counter() - started) * 1000)
            return OCRResult(
                fixture_id=fixture_id,
                filename=image_path.name,
                full_text=text,
                avg_confidence=avg_confidence,
                blocks=[
                    {
                        "text": word.get("value", ""),
                        "confidence": float(word.get("confidence", 0)),
                        "bbox": word.get("geometry"),
                    }
                    for word in words
                ],
                source="local docTR",
                ocr_ms=total_ms,
                total_ms=total_ms,
            )
        except Exception as exc:
            total_ms = int((perf_counter() - started) * 1000)
            return OCRResult(
                fixture_id=fixture_id,
                filename=image_path.name,
                full_text="",
                avg_confidence=0.0,
                blocks=[],
                source=f"local docTR unavailable: {exc}",
                ocr_ms=total_ms,
                total_ms=total_ms,
            )
