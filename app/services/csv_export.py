from __future__ import annotations

import csv
import io

from app.schemas.results import VerificationResult


def results_to_csv(results: list[VerificationResult]) -> str:
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
