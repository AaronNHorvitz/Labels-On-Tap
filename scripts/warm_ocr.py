#!/usr/bin/env python3
"""Warm the local docTR OCR adapter on the deployment host."""

from __future__ import annotations

from app.config import DEMO_FIXTURE_DIR
from app.services.ocr.doctr_engine import DoctrOCREngine


def main() -> None:
    image_path = DEMO_FIXTURE_DIR / "clean_malt_pass.png"
    result = DoctrOCREngine().run(image_path, fixture_id=None)
    print(f"OCR source: {result.source}")
    print(f"OCR confidence: {result.avg_confidence:.2f}")
    print(f"OCR elapsed ms: {result.ocr_ms}")


if __name__ == "__main__":
    main()
