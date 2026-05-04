"""Runtime configuration and repository path constants.

Notes
-----
Configuration is environment-variable driven so the same container can run in
local development and on the EC2 deployment host. Defaults are conservative for
the take-home prototype and can be overridden through ``.env`` / Docker
environment values.
"""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
JOBS_DIR = DATA_DIR / "jobs"
DEMO_FIXTURE_DIR = DATA_DIR / "fixtures/demo"
SOURCE_MAP_DIR = DATA_DIR / "source-maps"
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.70"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_MANIFEST_BYTES = int(os.getenv("MAX_MANIFEST_BYTES", str(1 * 1024 * 1024)))
MAX_ARCHIVE_BYTES = int(os.getenv("MAX_ARCHIVE_BYTES", str(250 * 1024 * 1024)))
MAX_BATCH_ITEMS = int(os.getenv("MAX_BATCH_ITEMS", "400"))
FIELD_SUPPORT_MODEL_ENABLED = os.getenv("FIELD_SUPPORT_MODEL_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FIELD_SUPPORT_MODEL_DIR = Path(
    os.getenv("FIELD_SUPPORT_MODEL_DIR", ROOT / "models/field_support/distilroberta")
)
FIELD_SUPPORT_THRESHOLD = float(os.getenv("FIELD_SUPPORT_THRESHOLD", "0.53"))
FIELD_SUPPORT_MAX_CANDIDATES = int(os.getenv("FIELD_SUPPORT_MAX_CANDIDATES", "18"))
