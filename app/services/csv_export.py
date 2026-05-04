"""CSV serialization for reviewer-facing job exports."""

from __future__ import annotations

import csv
import io

from app.schemas.results import VerificationResult


def results_to_csv(results: list[VerificationResult]) -> str:
    """Serialize verification results into a compact CSV report.

    Parameters
    ----------
    results:
        Verification results for a single job.

    Returns
    -------
    str
        CSV text suitable for a ``text/csv`` HTTP response.

    Notes
    -----
    Rule ID lists are semicolon-delimited to keep the export single-row-per-
    label and friendly to spreadsheet tools.
    """

    buffer = io.StringIO()
    fieldnames = [
        "filename",
        "raw_verdict",
        "overall_verdict",
        "policy_queue",
        "top_reason",
        "checked_rule_ids",
        "triggered_rule_ids",
        "expected_values",
        "observed_values",
        "evidence_text",
        "reviewer_actions",
        "reviewer_decision",
        "reviewer_note",
        "reviewed_at",
        "ocr_source",
        "ocr_confidence",
        "processing_ms",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for result in results:
        writer.writerow(
            {
                "filename": result.filename,
                "raw_verdict": result.raw_verdict or result.overall_verdict,
                "overall_verdict": result.overall_verdict,
                "policy_queue": result.policy_queue,
                "top_reason": result.top_reason,
                "checked_rule_ids": ";".join(result.checked_rule_ids),
                "triggered_rule_ids": ";".join(result.triggered_rule_ids),
                "expected_values": _join_check_values(result, "expected"),
                "observed_values": _join_check_values(result, "observed"),
                "evidence_text": _join_check_values(result, "evidence_text"),
                "reviewer_actions": _join_check_values(result, "reviewer_action"),
                "reviewer_decision": result.reviewer_decision,
                "reviewer_note": result.reviewer_note,
                "reviewed_at": result.reviewed_at,
                "ocr_source": result.ocr.get("source", ""),
                "ocr_confidence": result.ocr.get("avg_confidence", ""),
                "processing_ms": result.processing_ms,
            }
        )
    return buffer.getvalue()


def _join_check_values(result: VerificationResult, attribute: str) -> str:
    """Join non-empty per-check values for spreadsheet export."""

    values = []
    for check in result.checks:
        value = getattr(check, attribute, None)
        if value:
            values.append(f"{check.rule_id}: {str(value).replace(chr(10), ' ')[:500]}")
    return " | ".join(values)
