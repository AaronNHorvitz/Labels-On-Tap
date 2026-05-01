#!/usr/bin/env python3
"""Warm the local docTR OCR adapter on the deployment host.

Notes
-----
The one-click demos use fixture OCR. This command is only for checking and
pre-warming real local docTR OCR on the EC2 host after Docker deployment.
"""

from __future__ import annotations

from app.config import DEMO_FIXTURE_DIR
from app.services.ocr.doctr_engine import DoctrOCREngine


def main() -> None:
    """Run one docTR OCR pass against the clean fixture image."""

    image_path = DEMO_FIXTURE_DIR / "clean_malt_pass.png"
    result = DoctrOCREngine().run(image_path, fixture_id=None)
    print(f"OCR source: {result.source}")
    print(f"OCR confidence: {result.avg_confidence:.2f}")
    print(f"OCR elapsed ms: {result.ocr_ms}")


if __name__ == "__main__":
    main()
