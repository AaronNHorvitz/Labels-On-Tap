from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
JOBS_DIR = DATA_DIR / "jobs"
DEMO_FIXTURE_DIR = DATA_DIR / "fixtures/demo"
SOURCE_MAP_DIR = DATA_DIR / "source-maps"
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.70"))
