"""Low-latency boldness classifier for the government-warning heading.

Notes
-----
This service answers one narrow regulatory preflight question: did the OCR
pipeline isolate a ``GOVERNMENT WARNING:`` heading crop that is confidently
bold? The classifier is a real-adapted logistic model exported as JSON so the
web app does not need scikit-learn at runtime.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from app.config import ROOT
from app.schemas.ocr import OCRResult
from app.services.typography.features import FeatureConfig, extract_feature_vector
from app.services.typography.warning_heading import HeadingEvidence, detect_warning_heading_crop


MODEL_PATH = ROOT / "app/models/typography/boldness_logistic_v1.json"


@dataclass(frozen=True)
class BoldnessAssessment:
    """Classifier result for one warning-heading crop.

    Attributes
    ----------
    verdict:
        ``pass`` when boldness is confidently supported; otherwise
        ``needs_review``. The model does not automatically fail ambiguous
        typography evidence.
    probability:
        Logistic probability for the confident-bold class.
    threshold:
        Decision threshold selected from validation false-clear tolerance.
    crop_available:
        Whether OCR geometry supported a crop at all.
    """

    verdict: str
    probability: float | None
    threshold: float | None
    crop_available: bool
    model_name: str
    model_version: str
    matched_text: str = ""
    match_score: float | None = None
    ocr_confidence: float | None = None
    crop_ms: float = 0.0
    classification_ms: float = 0.0
    message: str = ""
    reviewer_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""

        return asdict(self)


def assess_warning_heading_boldness(
    image_path: Path,
    ocr: OCRResult | dict[str, Any],
) -> tuple[BoldnessAssessment, HeadingEvidence | None]:
    """Assess boldness for a warning heading in a label image.

    Parameters
    ----------
    image_path:
        Label image path.
    ocr:
        OCR result containing text blocks and coordinates.

    Returns
    -------
    tuple[BoldnessAssessment, HeadingEvidence | None]
        Structured classifier result plus the normalized crop, when available.
    """

    model = _load_model()
    evidence = detect_warning_heading_crop(image_path, ocr)
    if evidence is None:
        return (
            BoldnessAssessment(
                verdict="needs_review",
                probability=None,
                threshold=model["threshold"],
                crop_available=False,
                model_name=model["model_name"],
                model_version=model["model_version"],
                message="Warning heading could not be isolated from OCR geometry.",
                reviewer_action="Review the warning heading manually or request a clearer image.",
            ),
            None,
        )

    started = perf_counter()
    gray = np.array(evidence.crop.convert("L"))
    features = extract_feature_vector(gray, FeatureConfig())
    probability = _predict_probability(model, features)
    classification_ms = (perf_counter() - started) * 1000
    threshold = float(model["threshold"])

    if probability >= threshold:
        verdict = "pass"
        message = "Government warning heading is confidently classified as bold."
        action = "No typography action needed for the warning heading."
    else:
        verdict = "needs_review"
        message = "Warning heading boldness was not confidently established from the crop."
        action = "Review the warning heading crop before clearing this label."

    return (
        BoldnessAssessment(
            verdict=verdict,
            probability=round(probability, 6),
            threshold=threshold,
            crop_available=True,
            model_name=model["model_name"],
            model_version=model["model_version"],
            matched_text=evidence.matched_text,
            match_score=round(evidence.match_score, 6),
            ocr_confidence=evidence.ocr_confidence,
            crop_ms=round(evidence.crop_ms, 6),
            classification_ms=round(classification_ms, 6),
            message=message,
            reviewer_action=action,
        ),
        evidence,
    )


def _predict_probability(model: dict[str, Any], features: np.ndarray) -> float:
    coefs = np.array(model["coef"], dtype=np.float32)
    z = float(np.dot(features.astype(np.float32), coefs) + float(model["intercept"]))
    z = max(min(z, 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-z))


@lru_cache(maxsize=1)
def _load_model() -> dict[str, Any]:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    expected_len = len(payload["coef"])
    if expected_len != len(payload["feature_names"]):
        raise RuntimeError("Boldness model feature metadata is inconsistent")
    # Touch OpenCV once here so imported workers do not inherit a large thread
    # pool for a 3,480-feature, millisecond-scale classifier.
    cv2.setNumThreads(1)
    return payload
