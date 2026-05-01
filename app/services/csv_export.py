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
        "overall_verdict",
        "top_reason",
        "checked_rule_ids",
        "triggered_rule_ids",
        "ocr_source",
        "ocr_confidence",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for result in results:
        writer.writerow(
            {
                "filename": result.filename,
                "overall_verdict": result.overall_verdict,
                "top_reason": result.top_reason,
                "checked_rule_ids": ";".join(result.checked_rule_ids),
                "triggered_rule_ids": ";".join(result.triggered_rule_ids),
                "ocr_source": result.ocr.get("source", ""),
                "ocr_confidence": result.ocr.get("avg_confidence", ""),
            }
        )
    return buffer.getvalue()
