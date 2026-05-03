#!/usr/bin/env python
"""Evaluate deterministic OCR ensemble arbitration strategies.

This experiment treats OCR engines as noisy sensors. It does not rewrite OCR
text or make compliance decisions. Instead, it asks a field-level question:

``Do the combined OCR outputs support the expected application field value?``

The script reuses the same public COLA smoke setup as ``field_support_metrics``:
accepted application fields are positives, and controlled negatives are created
by shuffling same-field values from other applications. It then compares several
ensemble strategies against the same accuracy, F1, and false-clear metrics.
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

from experiments.ocr_engine_sweep.field_support_metrics import (
    aggregate_by_ttb,
    load_benchmark_panels,
    load_doctr_panels,
    load_expected_by_ttb,
    metrics_by_field,
    metrics_for_scores,
    score_field,
    scores_excluding,
    shuffled_negative,
)


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep" / "ensemble-field-support"
DEFAULT_ENGINE_RUNS = {
    "paddleocr": REPO_ROOT / "data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json",
    "openocr": REPO_ROOT / "data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30",
}
DEFAULT_DOCTR_CACHE = REPO_ROOT / "data/work/ocr-engine-sweep/doctr-cache-list-30.txt"


@dataclass(frozen=True)
class EnsembleScore:
    """One positive or shuffled-negative field-support ensemble row."""

    strategy: str
    ttb_id: str
    field_name: str
    label: int
    expected: str
    source_ttb_id: str
    predicted: int
    outcome: str
    max_score: float
    support_count: int
    supporting_engines: str
    engine_scores_json: str
    rationale: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-run",
        action="append",
        default=[],
        metavar="ENGINE=RUN_DIR",
        help="OCR benchmark run to include. Defaults to PaddleOCR and OpenOCR; docTR is loaded from cache.",
    )
    parser.add_argument("--doctr-cache-list", type=Path, default=DEFAULT_DOCTR_CACHE)
    parser.add_argument("--threshold", type=float, default=90.0)
    parser.add_argument("--high-threshold", type=float, default=97.0)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-name", default="doctr-paddle-openocr-ensemble-smoke-30")
    return parser.parse_args()


def parse_engine_runs(values: list[str]) -> dict[str, Path]:
    """Return requested engine runs keyed by engine name."""

    if not values:
        return dict(DEFAULT_ENGINE_RUNS)

    runs: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--engine-run must use ENGINE=RUN_DIR format: {value}")
        engine_name, run_dir = value.split("=", 1)
        engine_name = engine_name.strip()
        if not engine_name:
            raise SystemExit(f"--engine-run has an empty engine name: {value}")
        runs[engine_name] = Path(run_dir)
    return runs


def engine_score_map(
    *,
    field_name: str,
    expected: str,
    engine_aggregates: dict[str, dict[str, dict]],
    ttb_id: str,
) -> dict[str, float]:
    """Score one expected field against each engine's aggregated text."""

    return {
        engine: round(score_field(field_name, expected, aggregates[ttb_id]["text"]), 2)
        for engine, aggregates in engine_aggregates.items()
    }


def supporting_engines(scores: dict[str, float], threshold: float) -> list[str]:
    """Return engine names whose score clears the support threshold."""

    return [engine for engine, score in scores.items() if score >= threshold]


def predict_any(scores: dict[str, float], *, threshold: float, high_threshold: float, field_name: str) -> tuple[int, str]:
    """Predict support if any OCR engine supports the field."""

    del high_threshold, field_name
    return int(max(scores.values(), default=0.0) >= threshold), "any engine score >= threshold"


def predict_majority(
    scores: dict[str, float],
    *,
    threshold: float,
    high_threshold: float,
    field_name: str,
) -> tuple[int, str]:
    """Predict support if at least two OCR engines support the field."""

    del high_threshold, field_name
    count = len(supporting_engines(scores, threshold))
    return int(count >= 2), "at least two engines score >= threshold"


def predict_unanimous(
    scores: dict[str, float],
    *,
    threshold: float,
    high_threshold: float,
    field_name: str,
) -> tuple[int, str]:
    """Predict support only if all OCR engines support the field."""

    del high_threshold, field_name
    count = len(supporting_engines(scores, threshold))
    return int(count == len(scores)), "all engines score >= threshold"


def predict_high_or_majority(
    scores: dict[str, float],
    *,
    threshold: float,
    high_threshold: float,
    field_name: str,
) -> tuple[int, str]:
    """Predict support from majority consensus or one very strong engine."""

    del field_name
    count = len(supporting_engines(scores, threshold))
    best = max(scores.values(), default=0.0)
    return int(count >= 2 or best >= high_threshold), "majority support or one high-confidence score"


def predict_safety_weighted(
    scores: dict[str, float],
    *,
    threshold: float,
    high_threshold: float,
    field_name: str,
) -> tuple[int, str]:
    """Predict support with field-specific caution for known false-clear risk.

    PaddleOCR had the strongest F1 in the first smoke, but its alcohol-content
    false-clear rate was higher. This strategy allows a single-engine pass only
    when the best support is very high and not a lone PaddleOCR alcohol-content
    hit. Ambiguous conflicts stay unsupported, which means Needs Review in the
    product posture rather than a false clear.
    """

    support = supporting_engines(scores, threshold)
    best_engine, best_score = max(scores.items(), key=lambda item: item[1])
    if len(support) >= 2:
        return 1, "at least two engines support the field"
    if best_score < high_threshold:
        return 0, "no majority and no high-confidence single-engine support"
    if field_name == "alcohol_content" and best_engine == "paddleocr":
        return 0, "lone PaddleOCR alcohol-content support routed to review"
    return 1, f"single high-confidence support from {best_engine}"


def predict_government_safe(
    scores: dict[str, float],
    *,
    threshold: float,
    high_threshold: float,
    field_name: str,
) -> tuple[int, str]:
    """Predict support with a false-clear constrained field policy.

    The smoke-test failure mode is concentrated in alcohol-content checks: a
    false match on ABV is exactly the kind of error a compliance prototype
    should route to a human reviewer instead of clearing automatically. This
    policy therefore requires unanimous OCR support for alcohol content and
    majority support for other fields, while still allowing one very strong
    single-engine hit for lower-risk identity fields.
    """

    support = supporting_engines(scores, threshold)
    if field_name == "alcohol_content":
        if len(support) == len(scores):
            return 1, "alcohol content requires unanimous OCR support"
        return 0, "non-unanimous alcohol-content support routed to review"
    if len(support) >= 2:
        return 1, "at least two engines support the field"

    best_engine, best_score = max(scores.items(), key=lambda item: item[1])
    low_risk_single_engine_fields = {"brand_name", "fanciful_name", "country_of_origin", "net_contents"}
    if field_name in low_risk_single_engine_fields and best_score >= high_threshold:
        return 1, f"single high-confidence support from {best_engine}"
    return 0, "insufficient consensus for automatic support"


STRATEGIES = {
    "ensemble_any_engine": predict_any,
    "ensemble_majority_vote": predict_majority,
    "ensemble_unanimous": predict_unanimous,
    "ensemble_high_or_majority": predict_high_or_majority,
    "ensemble_safety_weighted": predict_safety_weighted,
    "ensemble_government_safe": predict_government_safe,
}


def build_field_pool(expected_by_ttb: dict[str, dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Build a same-field value pool for shuffled negative examples."""

    field_pool: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ttb_id, fields in expected_by_ttb.items():
        for field_name, value in fields.items():
            field_pool[field_name].append((ttb_id, value))
    return field_pool


def score_one(
    *,
    strategy_name: str,
    ttb_id: str,
    field_name: str,
    label: int,
    expected: str,
    source_ttb_id: str,
    scores: dict[str, float],
    threshold: float,
    high_threshold: float,
) -> EnsembleScore:
    """Score one positive or shuffled-negative example with one strategy."""

    prediction_function = STRATEGIES[strategy_name]
    predicted, rationale = prediction_function(
        scores,
        threshold=threshold,
        high_threshold=high_threshold,
        field_name=field_name,
    )
    if label == 1 and predicted == 1:
        outcome = "true_positive"
    elif label == 0 and predicted == 0:
        outcome = "true_negative"
    elif label == 0 and predicted == 1:
        outcome = "false_positive"
    else:
        outcome = "false_negative"

    support = supporting_engines(scores, threshold)
    return EnsembleScore(
        strategy=strategy_name,
        ttb_id=ttb_id,
        field_name=field_name,
        label=label,
        expected=expected,
        source_ttb_id=source_ttb_id,
        predicted=predicted,
        outcome=outcome,
        max_score=round(max(scores.values(), default=0.0), 2),
        support_count=len(support),
        supporting_engines=";".join(support),
        engine_scores_json=json.dumps(scores, sort_keys=True),
        rationale=rationale,
    )


def build_scores(
    *,
    strategy_name: str,
    engine_aggregates: dict[str, dict[str, dict]],
    expected_by_ttb: dict[str, dict[str, str]],
    threshold: float,
    high_threshold: float,
    seed: int,
) -> list[EnsembleScore]:
    """Build positive and shuffled-negative scores for one ensemble strategy."""

    rng = random.Random(seed)
    field_pool = build_field_pool(expected_by_ttb)
    common_ttbs = sorted(set.intersection(*(set(aggregates) for aggregates in engine_aggregates.values())))
    rows: list[EnsembleScore] = []
    for ttb_id in common_ttbs:
        for field_name, expected_value in expected_by_ttb.get(ttb_id, {}).items():
            positive_scores = engine_score_map(
                field_name=field_name,
                expected=expected_value,
                engine_aggregates=engine_aggregates,
                ttb_id=ttb_id,
            )
            rows.append(
                score_one(
                    strategy_name=strategy_name,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=1,
                    expected=expected_value,
                    source_ttb_id=ttb_id,
                    scores=positive_scores,
                    threshold=threshold,
                    high_threshold=high_threshold,
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
            negative_scores = engine_score_map(
                field_name=field_name,
                expected=negative_value,
                engine_aggregates=engine_aggregates,
                ttb_id=ttb_id,
            )
            rows.append(
                score_one(
                    strategy_name=strategy_name,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=0,
                    expected=negative_value,
                    source_ttb_id=source_ttb_id,
                    scores=negative_scores,
                    threshold=threshold,
                    high_threshold=high_threshold,
                )
            )
    return rows


def latency_summary(engine_aggregates: dict[str, dict[str, dict]]) -> dict:
    """Summarize full sequential ensemble latency across selected engines."""

    common_ttbs = sorted(set.intersection(*(set(aggregates) for aggregates in engine_aggregates.values())))
    latencies = [
        sum(int(aggregates[ttb_id]["total_ms"]) for aggregates in engine_aggregates.values())
        for ttb_id in common_ttbs
    ]
    return {
        "application_count": len(latencies),
        "mean_ms_sequential": round(mean(latencies), 2) if latencies else None,
        "max_ms_sequential": max(latencies) if latencies else None,
        "assumption": "sequential sum of measured OCR engine latencies; parallel execution would be bounded by the slowest engine plus arbiter overhead",
    }


def write_scores(path: Path, rows: list[EnsembleScore]) -> None:
    """Write row-level scores as CSV."""

    fieldnames = list(asdict(rows[0]).keys()) if rows else list(EnsembleScore.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    """Compute deterministic ensemble field-support metrics."""

    args = parse_args()
    output_dir = args.output_dir / args.run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    engine_aggregates = {"doctr": aggregate_by_ttb(load_doctr_panels(args.doctr_cache_list))}
    for engine_name, run_dir in parse_engine_runs(args.engine_run).items():
        engine_aggregates[engine_name] = aggregate_by_ttb(load_benchmark_panels(run_dir))

    common_ttbs = sorted(set.intersection(*(set(aggregates) for aggregates in engine_aggregates.values())))
    expected_by_ttb = load_expected_by_ttb(common_ttbs)

    strategy_scores = {
        strategy_name: build_scores(
            strategy_name=strategy_name,
            engine_aggregates=engine_aggregates,
            expected_by_ttb=expected_by_ttb,
            threshold=args.threshold,
            high_threshold=args.high_threshold,
            seed=args.seed,
        )
        for strategy_name in STRATEGIES
    }

    summary = {
        "threshold": args.threshold,
        "high_threshold": args.high_threshold,
        "seed": args.seed,
        "application_count": len(common_ttbs),
        "engines": sorted(engine_aggregates),
        "latency": latency_summary(engine_aggregates),
        "strategies": {
            strategy_name: {
                "overall": metrics_for_scores(scores),
                "overall_excluding_applicant_or_producer": metrics_for_scores(
                    scores_excluding(scores, {"applicant_or_producer"})
                ),
                "by_field": metrics_by_field(scores),
            }
            for strategy_name, scores in strategy_scores.items()
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for strategy_name, scores in strategy_scores.items():
        write_scores(output_dir / f"{strategy_name}_scores.csv", scores)

    print(json.dumps(summary, indent=2))
    print(f"Wrote ensemble field-support metrics to {output_dir}")


if __name__ == "__main__":
    main()
