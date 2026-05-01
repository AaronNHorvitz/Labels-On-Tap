from __future__ import annotations

from pydantic import BaseModel


class RuleCheck(BaseModel):
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
