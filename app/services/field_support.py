"""Optional DistilRoBERTa field-support arbiter.

The deployed rules remain deterministic. This module adds the measured BERT
bridge when a saved model artifact is present. It scores whether OCR evidence
supports one application field value, then returns the best supporting OCR
candidate and probability for the rule layer to use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import (
    FIELD_SUPPORT_MAX_CANDIDATES,
    FIELD_SUPPORT_MODEL_DIR,
    FIELD_SUPPORT_MODEL_ENABLED,
    FIELD_SUPPORT_THRESHOLD,
)
from app.schemas.application import ColaApplication
from app.schemas.ocr import OCRResult
from rapidfuzz import fuzz


@dataclass(frozen=True)
class FieldSupportDecision:
    """One BERT field-support decision."""

    available: bool
    field_name: str
    expected: str
    supported: bool = False
    probability: float = 0.0
    threshold: float = FIELD_SUPPORT_THRESHOLD
    candidate_text: str = ""
    candidate_count: int = 0
    latency_ms: int = 0
    reason: str = ""


class FieldSupportArbiter:
    """Lazy CPU inference wrapper around a saved Transformer classifier."""

    def __init__(
        self,
        model_dir: Path = FIELD_SUPPORT_MODEL_DIR,
        *,
        enabled: bool = FIELD_SUPPORT_MODEL_ENABLED,
        threshold: float = FIELD_SUPPORT_THRESHOLD,
        max_candidates: int = FIELD_SUPPORT_MAX_CANDIDATES,
    ) -> None:
        self.model_dir = model_dir
        self.enabled = enabled
        self.threshold = threshold
        self.max_candidates = max_candidates
        self._loaded = False
        self._available = False
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._load_error = ""

    @property
    def available(self) -> bool:
        """Return whether the model can be used."""

        self._ensure_loaded()
        return self._available

    def score(
        self,
        *,
        field_name: str,
        expected: str,
        ocr: OCRResult,
        application: ColaApplication,
    ) -> FieldSupportDecision:
        """Score OCR evidence for one application field."""

        expected = clean_text(expected)
        if not expected:
            return FieldSupportDecision(
                available=False,
                field_name=field_name,
                expected=expected,
                reason="No expected value provided.",
            )

        self._ensure_loaded()
        if not self._available or self._model is None or self._tokenizer is None:
            return FieldSupportDecision(
                available=False,
                field_name=field_name,
                expected=expected,
                threshold=self.threshold,
                reason=self._load_error or "Field-support model unavailable.",
            )

        candidates = candidate_texts(expected, ocr, max_candidates=self.max_candidates)
        if not candidates:
            return FieldSupportDecision(
                available=True,
                field_name=field_name,
                expected=expected,
                threshold=self.threshold,
                reason="No OCR candidates available.",
            )

        started = perf_counter()
        prompts = [
            pair_prompt(field_name=field_name, expected=expected, candidate=candidate, application=application)
            for candidate in candidates
        ]
        try:
            import torch

            encoded = self._tokenizer(
                prompts,
                max_length=128,
                padding=True,
                truncation=True,
                return_tensors="pt",
            )
            with torch.no_grad():
                output = self._model(**encoded)
                probabilities = torch.softmax(output.logits, dim=-1)[:, 1].detach().cpu().tolist()
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            return FieldSupportDecision(
                available=False,
                field_name=field_name,
                expected=expected,
                threshold=self.threshold,
                reason=f"Field-support inference failed: {exc}",
            )

        best_index, best_probability = max(
            enumerate(float(value) for value in probabilities),
            key=lambda item: item[1],
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        return FieldSupportDecision(
            available=True,
            field_name=field_name,
            expected=expected,
            supported=best_probability >= self.threshold,
            probability=round(best_probability, 6),
            threshold=self.threshold,
            candidate_text=candidates[best_index],
            candidate_count=len(candidates),
            latency_ms=elapsed_ms,
            reason="ok",
        )

    def _ensure_loaded(self) -> None:
        """Load the model once, only when needed."""

        if self._loaded:
            return
        self._loaded = True
        if not self.enabled:
            self._load_error = "FIELD_SUPPORT_MODEL_ENABLED is false."
            return
        if not self.model_dir.exists():
            self._load_error = f"Model directory not found: {self.model_dir}"
            return
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
            self._model.eval()
            self._available = True
        except Exception as exc:  # pragma: no cover - depends on optional package/model artifact
            self._load_error = f"Could not load field-support model: {exc}"


_ARBITER: FieldSupportArbiter | None = None


def get_field_support_arbiter() -> FieldSupportArbiter:
    """Return the process-wide field-support arbiter."""

    global _ARBITER
    if _ARBITER is None:
        _ARBITER = FieldSupportArbiter()
    return _ARBITER


def clean_text(value: object) -> str:
    """Normalize one text value for prompt/candidate construction."""

    return " ".join(str(value or "").split())


def candidate_texts(expected: str, ocr: OCRResult, *, max_candidates: int) -> list[str]:
    """Build likely OCR candidate strings for BERT scoring."""

    raw_blocks = [clean_text(block.text) for block in ocr.blocks if clean_text(block.text)]
    candidates: list[str] = []

    def add(value: str) -> None:
        value = clean_text(value)
        if value and value not in candidates:
            candidates.append(value)

    for block in raw_blocks:
        add(block)
    for width in (2, 3, 5, 8):
        for index in range(0, max(0, len(raw_blocks) - width + 1)):
            add(" ".join(raw_blocks[index : index + width]))
    add(ocr.full_text[:1200])

    candidates.sort(key=lambda candidate: fuzz.partial_ratio(expected.lower(), candidate.lower()), reverse=True)
    return candidates[:max_candidates]


def pair_prompt(
    *,
    field_name: str,
    expected: str,
    candidate: str,
    application: ColaApplication,
) -> str:
    """Build the same text-pair shape used by training."""

    field = field_name.replace("_", " ")
    imported = "true" if application.imported else "false"
    return (
        f"field: {field}\n"
        f"application value: {expected}\n"
        f"candidate evidence: {candidate}\n"
        f"product type: {application.product_type}\n"
        f"origin: {application.country_of_origin or ''}\n"
        f"imported: {imported}\n"
        "panel complexity: runtime"
    )
