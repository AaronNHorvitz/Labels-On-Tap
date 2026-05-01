"""Verification-result schemas rendered by the UI and CSV export."""

from __future__ import annotations

from pydantic import BaseModel


class RuleCheck(BaseModel):
    """A single source-backed rule evaluation.

    Attributes
    ----------
    rule_id:
        Stable identifier that maps to the source-backed criteria matrix.
    verdict:
        One of ``pass``, ``needs_review``, or ``fail``.
    expected, observed:
        Human-readable comparison values displayed on detail pages.
    source_refs:
        Source IDs from the legal/research corpus.
    reviewer_action:
        Plain-language next step for the reviewer when action is needed.
    """

    rule_id: str
    name: str
    category: str
    verdict: str
    expected: str | None = None
    observed: str | None = None
    evidence_text: str | None = None
    source_refs: list[str] = []
    message: str
    reviewer_action: str | None = None
    score: float | None = None
    confidence: float | None = None


class VerificationResult(BaseModel):
    """Aggregated result for one reviewed label image."""

    job_id: str
    item_id: str
    filename: str
    application: dict
    overall_verdict: str
    top_reason: str
    checked_rule_ids: list[str]
    triggered_rule_ids: list[str]
    checks: list[RuleCheck]
    ocr: dict
    processing_ms: int = 0
