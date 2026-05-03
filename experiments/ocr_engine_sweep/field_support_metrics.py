#!/usr/bin/env python
"""Compute side-by-side field-support metrics for OCR engine outputs.

The OCR smoke benchmark measures latency and text extraction. This script adds
classification metrics by asking a narrower question:

``Does this OCR text support the application field value?``

Accepted public COLA application fields are treated as positive examples. For
controlled negatives, the script shuffles same-field values from other
applications and scores them against the current application's OCR text.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from app.services.rules.field_matching import fuzzy_score
from scripts.cola_etl.database import connect
from scripts.cola_etl.evaluation import PRIMARY_FIELDS, expected_fields, field_candidates, parse_json, registry_record
from scripts.cola_etl.paths import PARSED_APPLICATIONS_DIR


DEFAULT_RUN_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep" / "paddleocr-333-paddle-320-smoke-30-json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep" / "field-support-metrics"


@dataclass(frozen=True)
class EnginePanel:
    """One OCR panel artifact for an engine."""

    ttb_id: str
    image_path: str
    full_text: str
    total_ms: int
    block_count: int
    text_chars: int


@dataclass(frozen=True)
class ExampleScore:
    """One positive or shuffled-negative field-support classification row."""

    engine: str
    ttb_id: str
    field_name: str
    label: int
    expected: str
    source_ttb_id: str
    score: float
    predicted: int
    outcome: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paddle-run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--doctr-cache-list",
        type=Path,
        default=REPO_ROOT / "data" / "work" / "ocr-engine-sweep" / "doctr-cache-list-30.txt",
    )
    parser.add_argument("--threshold", type=float, default=90.0)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-name", default="paddle-vs-doctr-smoke-30")
    return parser.parse_args()


def ttb_id_from_image_path(image_path: str) -> str:
    """Extract the parent TTB ID from a public COLA image path."""

    return Path(image_path).parent.name


def load_ocr_text(path: Path) -> str:
    """Load normalized OCR full text from a JSON artifact."""

    return json.loads(path.read_text(encoding="utf-8")).get("full_text", "")


def load_doctr_panels(cache_list: Path) -> list[EnginePanel]:
    """Load docTR cached OCR artifacts as engine panels."""

    panels: list[EnginePanel] = []
    for path_text in cache_list.read_text(encoding="utf-8").splitlines():
        if not path_text.strip():
            continue
        path = Path(path_text.strip())
        payload = json.loads(path.read_text(encoding="utf-8"))
        ttb_id = path.parent.name
        panels.append(
            EnginePanel(
                ttb_id=ttb_id,
                image_path=payload.get("filename", path.name),
                full_text=payload.get("full_text", ""),
                total_ms=int(payload.get("total_ms") or 0),
                block_count=len(payload.get("blocks", [])),
                text_chars=len(payload.get("full_text", "")),
            )
        )
    return panels


def load_paddle_panels(run_dir: Path) -> list[EnginePanel]:
    """Load PaddleOCR benchmark rows and normalized OCR JSON artifacts."""

    rows_path = run_dir / "rows.csv"
    panels: list[EnginePanel] = []
    with rows_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "ok":
                continue
            ocr_json_path = REPO_ROOT / row["ocr_json_path"]
            full_text = load_ocr_text(ocr_json_path)
            panels.append(
                EnginePanel(
                    ttb_id=ttb_id_from_image_path(row["image_path"]),
                    image_path=row["image_path"],
                    full_text=full_text,
                    total_ms=int(row["total_ms"]),
                    block_count=int(row["block_count"]),
                    text_chars=int(row["text_chars"]),
                )
            )
    return panels


def aggregate_by_ttb(panels: list[EnginePanel]) -> dict[str, dict]:
    """Aggregate panel OCR text and timing by TTB ID."""

    grouped: dict[str, list[EnginePanel]] = defaultdict(list)
    for panel in panels:
        grouped[panel.ttb_id].append(panel)
    return {
        ttb_id: {
            "text": "\n\n".join(panel.full_text for panel in items if panel.full_text),
            "panel_count": len(items),
            "total_ms": sum(panel.total_ms for panel in items),
            "text_chars": sum(panel.text_chars for panel in items),
            "block_count": sum(panel.block_count for panel in items),
        }
        for ttb_id, items in grouped.items()
    }


def score_field(field_name: str, expected: str, text: str) -> float:
    """Return the best field-candidate fuzzy score against OCR text."""

    candidates = field_candidates(field_name, expected)
    return max((fuzzy_score(candidate, text) for candidate in candidates), default=0.0)


def load_expected_by_ttb(ttb_ids: list[str]) -> dict[str, dict[str, str]]:
    """Load expected application fields for selected TTB IDs."""

    expected: dict[str, dict[str, str]] = {}
    with connect() as connection:
        for ttb_id in ttb_ids:
            parsed_path = PARSED_APPLICATIONS_DIR / f"{ttb_id}.json"
            if not parsed_path.exists():
                continue
            parsed = parse_json(parsed_path)
            registry = registry_record(connection, ttb_id)
            fields = expected_fields(parsed, registry)
            expected[ttb_id] = {
                field_name: value
                for field_name, value in fields.items()
                if field_name in PRIMARY_FIELDS and value
            }
    return expected


def shuffled_negative(
    *,
    rng: random.Random,
    ttb_id: str,
    field_name: str,
    expected_value: str,
    field_pool: dict[str, list[tuple[str, str]]],
) -> tuple[str, str] | None:
    """Return another application's same-field value as a negative example."""

    candidates = [
        (source_ttb_id, value)
        for source_ttb_id, value in field_pool[field_name]
        if source_ttb_id != ttb_id and value.strip().lower() != expected_value.strip().lower()
    ]
    if not candidates:
        return None
    return rng.choice(candidates)


def build_scores(
    *,
    engine_name: str,
    aggregates: dict[str, dict],
    expected_by_ttb: dict[str, dict[str, str]],
    threshold: float,
    seed: int,
) -> list[ExampleScore]:
    """Build positive and shuffled-negative scores for one OCR engine."""

    rng = random.Random(seed)
    field_pool: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ttb_id, fields in expected_by_ttb.items():
        for field_name, value in fields.items():
            field_pool[field_name].append((ttb_id, value))

    scores: list[ExampleScore] = []
    for ttb_id in sorted(aggregates):
        text = aggregates[ttb_id]["text"]
        for field_name, expected_value in expected_by_ttb.get(ttb_id, {}).items():
            positive_score = score_field(field_name, expected_value, text)
            positive_predicted = int(positive_score >= threshold)
            scores.append(
                ExampleScore(
                    engine=engine_name,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=1,
                    expected=expected_value,
                    source_ttb_id=ttb_id,
                    score=round(positive_score, 2),
                    predicted=positive_predicted,
                    outcome="true_positive" if positive_predicted else "false_negative",
                )
            )

            negative = shuffled_negative(
                rng=rng,
                ttb_id=ttb_id,
                field_name=field_name,
                expected_value=expected_value,
                field_pool=field_pool,
            )
            if negative is None:
                continue
            source_ttb_id, negative_value = negative
            negative_score = score_field(field_name, negative_value, text)
            negative_predicted = int(negative_score >= threshold)
            scores.append(
                ExampleScore(
                    engine=engine_name,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=0,
                    expected=negative_value,
                    source_ttb_id=source_ttb_id,
                    score=round(negative_score, 2),
                    predicted=negative_predicted,
                    outcome="false_positive" if negative_predicted else "true_negative",
                )
            )
    return scores


def metrics_for_scores(scores: list[ExampleScore]) -> dict:
    """Compute binary classification metrics."""

    tp = sum(1 for row in scores if row.label == 1 and row.predicted == 1)
    tn = sum(1 for row in scores if row.label == 0 and row.predicted == 0)
    fp = sum(1 for row in scores if row.label == 0 and row.predicted == 1)
    fn = sum(1 for row in scores if row.label == 1 and row.predicted == 0)
    total = tp + tn + fp + fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "examples": total,
        "positives": tp + fn,
        "negatives": tn + fp,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1": round(f1, 4),
        "false_clear_rate": round(fp / (tn + fp), 4) if tn + fp else 0.0,
    }


def metrics_by_field(scores: list[ExampleScore]) -> dict[str, dict]:
    """Compute metrics separately for each field."""

    return {
        field_name: metrics_for_scores([row for row in scores if row.field_name == field_name])
        for field_name in PRIMARY_FIELDS
        if any(row.field_name == field_name for row in scores)
    }


def scores_excluding(scores: list[ExampleScore], excluded_fields: set[str]) -> list[ExampleScore]:
    """Return score rows excluding specified fields."""

    return [row for row in scores if row.field_name not in excluded_fields]


def latency_summary(aggregates: dict[str, dict]) -> dict:
    """Summarize per-application latency from selected panels."""

    latencies = [int(item["total_ms"]) for item in aggregates.values()]
    return {
        "application_count": len(latencies),
        "mean_ms": round(mean(latencies), 2) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
    }


def write_scores(path: Path, scores: list[ExampleScore]) -> None:
    """Write row-level scores as CSV."""

    fieldnames = list(asdict(scores[0]).keys()) if scores else list(ExampleScore.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in scores:
            writer.writerow(asdict(row))


def main() -> None:
    """Compute and write side-by-side metrics."""

    args = parse_args()
    output_dir = args.output_dir / args.run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    doctr_aggregates = aggregate_by_ttb(load_doctr_panels(args.doctr_cache_list))
    paddle_aggregates = aggregate_by_ttb(load_paddle_panels(args.paddle_run_dir))
    common_ttbs = sorted(set(doctr_aggregates) & set(paddle_aggregates))
    expected_by_ttb = load_expected_by_ttb(common_ttbs)

    engine_scores = {
        "doctr": build_scores(
            engine_name="doctr",
            aggregates={ttb_id: doctr_aggregates[ttb_id] for ttb_id in common_ttbs},
            expected_by_ttb=expected_by_ttb,
            threshold=args.threshold,
            seed=args.seed,
        ),
        "paddleocr": build_scores(
            engine_name="paddleocr",
            aggregates={ttb_id: paddle_aggregates[ttb_id] for ttb_id in common_ttbs},
            expected_by_ttb=expected_by_ttb,
            threshold=args.threshold,
            seed=args.seed,
        ),
    }

    summary = {
        "threshold": args.threshold,
        "seed": args.seed,
        "application_count": len(common_ttbs),
        "engines": {
            engine: {
                "overall": metrics_for_scores(scores),
                "overall_excluding_applicant_or_producer": metrics_for_scores(
                    scores_excluding(scores, {"applicant_or_producer"})
                ),
                "by_field": metrics_by_field(scores),
                "latency": latency_summary(doctr_aggregates if engine == "doctr" else paddle_aggregates),
            }
            for engine, scores in engine_scores.items()
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for engine, scores in engine_scores.items():
        write_scores(output_dir / f"{engine}_scores.csv", scores)

    print(json.dumps(summary, indent=2))
    print(f"Wrote field-support metrics to {output_dir}")


if __name__ == "__main__":
    main()
