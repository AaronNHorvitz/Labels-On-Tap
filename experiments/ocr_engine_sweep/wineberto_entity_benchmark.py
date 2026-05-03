#!/usr/bin/env python
"""Benchmark domain-NER entity extraction as an OCR evidence arbiter.

This experiment tests whether a domain token-classification model can improve
post-OCR field support. It does not replace OCR and it does not make compliance
decisions. It consumes normalized OCR text from docTR, PaddleOCR, and OpenOCR,
extracts named entities, then scores whether those entities support expected
public COLA application fields.

The model is intentionally loaded inside this experiment script instead of the
runtime app. That keeps experimental Transformer dependencies out of the
deployed prototype until a model earns promotion.
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
from time import perf_counter
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from experiments.ocr_engine_sweep.ensemble_field_support_metrics import (
    engine_score_map,
    predict_government_safe,
    supporting_engines,
)
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
from scripts.cola_etl.evaluation import PRIMARY_FIELDS


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep" / "wineberto-entity"
DEFAULT_DOCTR_CACHE = REPO_ROOT / "data/work/ocr-engine-sweep/doctr-cache-list-30.txt"
DEFAULT_ENGINE_RUNS = {
    "paddleocr": REPO_ROOT / "data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json",
    "openocr": REPO_ROOT / "data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30",
}
DEFAULT_MODEL_ID = "panigrah/wineberto-labels"
ENTITY_PRESETS = {
    "wineberto": {
        "brand_name": {"producer", "wine"},
        "fanciful_name": {"wine"},
        "class_type": {"classification", "wine"},
        "alcohol_content": set(),
        "net_contents": set(),
        "country_of_origin": {"country", "region", "subregion"},
        "applicant_or_producer": {"producer"},
    },
    "osa": {
        "brand_name": {"prdc_char"},
        "fanciful_name": {"prdc_char"},
        "class_type": {"prdc_char", "mrkt_char"},
        "alcohol_content": set(),
        "net_contents": set(),
        "country_of_origin": {"mrkt_char"},
        "applicant_or_producer": {"prdc_char"},
    },
}
LOWER_RISK_ENTITY_FIELDS = {"brand_name", "fanciful_name", "class_type", "country_of_origin", "applicant_or_producer"}


@dataclass(frozen=True)
class WinebertoEntity:
    """One grouped domain-NER entity span."""

    ttb_id: str
    text_source: str
    entity_group: str
    word: str
    score: float
    chunk_index: int


@dataclass(frozen=True)
class WinebertoScore:
    """One positive or shuffled-negative field-support row."""

    strategy: str
    ttb_id: str
    field_name: str
    label: int
    expected: str
    source_ttb_id: str
    predicted: int
    outcome: str
    wineberto_score: float
    engine_max_score: float
    engine_support_count: int
    supporting_engines: str
    entity_text: str
    rationale: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-label", default=None)
    parser.add_argument("--model-license", default="unknown")
    parser.add_argument("--entity-preset", choices=sorted(ENTITY_PRESETS), default="wineberto")
    parser.add_argument("--text-source", choices=["combined", "doctr", "paddleocr", "openocr"], default="combined")
    parser.add_argument("--engine-run", action="append", default=[], metavar="ENGINE=RUN_DIR")
    parser.add_argument("--doctr-cache-list", type=Path, default=DEFAULT_DOCTR_CACHE)
    parser.add_argument("--threshold", type=float, default=90.0)
    parser.add_argument("--engine-soft-threshold", type=float, default=75.0)
    parser.add_argument("--high-threshold", type=float, default=97.0)
    parser.add_argument("--entity-min-score", type=float, default=0.45)
    parser.add_argument("--max-words", type=int, default=220)
    parser.add_argument("--overlap-words", type=int, default=30)
    parser.add_argument("--limit-apps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-name", default="wineberto-labels-combined-smoke-30")
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
        runs[engine_name.strip()] = Path(run_dir)
    return runs


def chunk_words(text: str, *, max_words: int, overlap_words: int) -> list[str]:
    """Split OCR text into overlapping word chunks for BERT inference."""

    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]
    chunks = []
    step = max(1, max_words - overlap_words)
    for start in range(0, len(words), step):
        chunk = words[start : start + max_words]
        if chunk:
            chunks.append(" ".join(chunk))
        if start + max_words >= len(words):
            break
    return chunks


def normalize_entity_group(value: str) -> str:
    """Normalize Hugging Face entity labels to a simple lowercase group."""

    group = value.replace("B-", "").replace("I-", "").replace("LABEL_", "").strip().lower()
    return group


def clean_entity_word(value: str) -> str:
    """Normalize WordPiece artifacts in grouped entity text."""

    return " ".join(value.replace("##", "").replace("\n", " ").split())


def load_transformers_pipeline(model_id: str) -> Callable[[str], list[dict]]:
    """Load a Hugging Face token-classification pipeline lazily."""

    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - depends on experiment env
        raise SystemExit(
            "transformers is required for this experiment. Run it in an isolated "
            "Python 3.11 container or venv; do not add it to production requirements yet."
        ) from exc

    try:
        return pipeline(
            "token-classification",
            model=model_id,
            tokenizer=model_id,
            aggregation_strategy="simple",
            device=-1,
        )
    except Exception as exc:  # pragma: no cover - model/network dependent
        raise SystemExit(f"Could not load token-classification model {model_id!r}: {exc}") from exc


def ocr_texts_by_ttb(engine_aggregates: dict[str, dict[str, dict]], text_source: str) -> dict[str, str]:
    """Return the OCR text source to send through the token classifier."""

    common_ttbs = sorted(set.intersection(*(set(aggregates) for aggregates in engine_aggregates.values())))
    texts: dict[str, str] = {}
    for ttb_id in common_ttbs:
        if text_source == "combined":
            texts[ttb_id] = "\n\n".join(
                engine_aggregates[engine][ttb_id]["text"] for engine in sorted(engine_aggregates)
            )
        else:
            texts[ttb_id] = engine_aggregates[text_source][ttb_id]["text"]
    return texts


def extract_entities(
    *,
    ner_pipeline: Callable[[str], list[dict]],
    texts: dict[str, str],
    text_source: str,
    entity_min_score: float,
    max_words: int,
    overlap_words: int,
) -> tuple[list[WinebertoEntity], dict[str, int]]:
    """Run token classification over all selected OCR text and return entities."""

    entities: list[WinebertoEntity] = []
    latencies: dict[str, int] = {}
    for ttb_id, text in texts.items():
        started = perf_counter()
        for chunk_index, chunk in enumerate(chunk_words(text, max_words=max_words, overlap_words=overlap_words)):
            for entity in ner_pipeline(chunk):
                score = float(entity.get("score") or 0.0)
                if score < entity_min_score:
                    continue
                group = normalize_entity_group(str(entity.get("entity_group") or entity.get("entity") or ""))
                word = clean_entity_word(str(entity.get("word") or ""))
                if not group or not word:
                    continue
                entities.append(
                    WinebertoEntity(
                        ttb_id=ttb_id,
                        text_source=text_source,
                        entity_group=group,
                        word=word,
                        score=round(score, 6),
                        chunk_index=chunk_index,
                    )
                )
        latencies[ttb_id] = int((perf_counter() - started) * 1000)
    return entities, latencies


def entity_text_for_field(
    entities: list[WinebertoEntity],
    field_name: str,
    entity_types_by_field: dict[str, set[str]],
) -> str:
    """Return domain-NER entity text relevant to a target application field."""

    allowed_groups = entity_types_by_field.get(field_name, set())
    if not allowed_groups:
        return ""
    words = [entity.word for entity in entities if entity.entity_group in allowed_groups]
    return "\n".join(dict.fromkeys(words))


def build_field_pool(expected_by_ttb: dict[str, dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Build same-field values for shuffled negative examples."""

    field_pool: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ttb_id, fields in expected_by_ttb.items():
        for field_name, value in fields.items():
            field_pool[field_name].append((ttb_id, value))
    return field_pool


def predict_entities_only(wineberto_score: float, *, threshold: float, **_: object) -> tuple[int, str]:
    """Use domain-NER entity support without OCR-engine fallback."""

    return int(wineberto_score >= threshold), "domain-NER entity score >= threshold"


def predict_wineberto_or_government_safe(
    wineberto_score: float,
    *,
    field_name: str,
    engine_scores: dict[str, float],
    threshold: float,
    high_threshold: float,
    engine_soft_threshold: float,
) -> tuple[int, str]:
    """Allow domain NER to supplement the deterministic government-safe ensemble."""

    engine_predicted, engine_reason = predict_government_safe(
        engine_scores,
        threshold=threshold,
        high_threshold=high_threshold,
        field_name=field_name,
    )
    if engine_predicted:
        return 1, f"government-safe ensemble: {engine_reason}"
    if field_name in LOWER_RISK_ENTITY_FIELDS and wineberto_score >= threshold:
        return 1, "domain-NER entity score supports lower-risk text field"
    return 0, "no government-safe ensemble support and no domain-NER lower-risk support"


def predict_wineberto_review_safe(
    wineberto_score: float,
    *,
    field_name: str,
    engine_scores: dict[str, float],
    threshold: float,
    high_threshold: float,
    engine_soft_threshold: float,
) -> tuple[int, str]:
    """Require domain NER plus at least soft OCR evidence for supplemental support."""

    engine_predicted, engine_reason = predict_government_safe(
        engine_scores,
        threshold=threshold,
        high_threshold=high_threshold,
        field_name=field_name,
    )
    if engine_predicted:
        return 1, f"government-safe ensemble: {engine_reason}"
    if field_name in LOWER_RISK_ENTITY_FIELDS and wineberto_score >= threshold:
        if max(engine_scores.values(), default=0.0) >= engine_soft_threshold:
            return 1, "domain-NER support plus soft OCR evidence"
    return 0, "insufficient domain-NER and OCR support"


STRATEGIES = {
    "wineberto_entities_only": predict_entities_only,
    "wineberto_or_government_safe": predict_wineberto_or_government_safe,
    "wineberto_review_safe": predict_wineberto_review_safe,
}


def score_row(
    *,
    strategy: str,
    ttb_id: str,
    field_name: str,
    label: int,
    expected: str,
    source_ttb_id: str,
    wineberto_score: float,
    engine_scores: dict[str, float],
    entity_text: str,
    threshold: float,
    high_threshold: float,
    engine_soft_threshold: float,
) -> WinebertoScore:
    """Score one example with one domain-NER strategy."""

    predicted, rationale = STRATEGIES[strategy](
        wineberto_score,
        field_name=field_name,
        engine_scores=engine_scores,
        threshold=threshold,
        high_threshold=high_threshold,
        engine_soft_threshold=engine_soft_threshold,
    )
    if label == 1 and predicted == 1:
        outcome = "true_positive"
    elif label == 0 and predicted == 0:
        outcome = "true_negative"
    elif label == 0 and predicted == 1:
        outcome = "false_positive"
    else:
        outcome = "false_negative"
    support = supporting_engines(engine_scores, threshold)
    return WinebertoScore(
        strategy=strategy,
        ttb_id=ttb_id,
        field_name=field_name,
        label=label,
        expected=expected,
        source_ttb_id=source_ttb_id,
        predicted=predicted,
        outcome=outcome,
        wineberto_score=round(wineberto_score, 2),
        engine_max_score=round(max(engine_scores.values(), default=0.0), 2),
        engine_support_count=len(support),
        supporting_engines=";".join(support),
        entity_text=entity_text,
        rationale=rationale,
    )


def build_scores(
    *,
    strategy: str,
    common_ttbs: list[str],
    expected_by_ttb: dict[str, dict[str, str]],
    entities_by_ttb: dict[str, list[WinebertoEntity]],
    engine_aggregates: dict[str, dict[str, dict]],
    entity_types_by_field: dict[str, set[str]],
    threshold: float,
    high_threshold: float,
    engine_soft_threshold: float,
    seed: int,
) -> list[WinebertoScore]:
    """Build positive and shuffled-negative field-support rows."""

    rng = random.Random(seed)
    field_pool = build_field_pool(expected_by_ttb)
    rows: list[WinebertoScore] = []
    for ttb_id in common_ttbs:
        ttb_entities = entities_by_ttb.get(ttb_id, [])
        for field_name, expected_value in expected_by_ttb.get(ttb_id, {}).items():
            entity_text = entity_text_for_field(ttb_entities, field_name, entity_types_by_field)
            positive_wineberto_score = score_field(field_name, expected_value, entity_text)
            positive_engine_scores = engine_score_map(
                field_name=field_name,
                expected=expected_value,
                engine_aggregates=engine_aggregates,
                ttb_id=ttb_id,
            )
            rows.append(
                score_row(
                    strategy=strategy,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=1,
                    expected=expected_value,
                    source_ttb_id=ttb_id,
                    wineberto_score=positive_wineberto_score,
                    engine_scores=positive_engine_scores,
                    entity_text=entity_text,
                    threshold=threshold,
                    high_threshold=high_threshold,
                    engine_soft_threshold=engine_soft_threshold,
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
            negative_wineberto_score = score_field(field_name, negative_value, entity_text)
            negative_engine_scores = engine_score_map(
                field_name=field_name,
                expected=negative_value,
                engine_aggregates=engine_aggregates,
                ttb_id=ttb_id,
            )
            rows.append(
                score_row(
                    strategy=strategy,
                    ttb_id=ttb_id,
                    field_name=field_name,
                    label=0,
                    expected=negative_value,
                    source_ttb_id=source_ttb_id,
                    wineberto_score=negative_wineberto_score,
                    engine_scores=negative_engine_scores,
                    entity_text=entity_text,
                    threshold=threshold,
                    high_threshold=high_threshold,
                    engine_soft_threshold=engine_soft_threshold,
                )
            )
    return rows


def latency_summary(latencies: dict[str, int]) -> dict:
    """Summarize token-classifier inference latency by application."""

    values = list(latencies.values())
    return {
        "application_count": len(values),
        "mean_ms": round(mean(values), 2) if values else None,
        "max_ms": max(values) if values else None,
    }


def write_csv(path: Path, rows: list[object], fieldnames: list[str] | None = None) -> None:
    """Write dataclass rows as CSV."""

    if not rows and fieldnames is None:
        return
    columns = fieldnames or list(asdict(rows[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    """Run the domain-NER entity-support benchmark."""

    args = parse_args()
    output_dir = args.output_dir / args.run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    engine_aggregates = {"doctr": aggregate_by_ttb(load_doctr_panels(args.doctr_cache_list))}
    for engine_name, run_dir in parse_engine_runs(args.engine_run).items():
        engine_aggregates[engine_name] = aggregate_by_ttb(load_benchmark_panels(run_dir))

    common_ttbs = sorted(set.intersection(*(set(aggregates) for aggregates in engine_aggregates.values())))
    if args.limit_apps:
        common_ttbs = common_ttbs[: args.limit_apps]
    engine_aggregates = {
        engine: {ttb_id: aggregates[ttb_id] for ttb_id in common_ttbs}
        for engine, aggregates in engine_aggregates.items()
    }
    expected_by_ttb = load_expected_by_ttb(common_ttbs)

    texts = ocr_texts_by_ttb(engine_aggregates, args.text_source)
    ner_pipeline = load_transformers_pipeline(args.model_id)
    entities, latencies = extract_entities(
        ner_pipeline=ner_pipeline,
        texts=texts,
        text_source=args.text_source,
        entity_min_score=args.entity_min_score,
        max_words=args.max_words,
        overlap_words=args.overlap_words,
    )
    entities_by_ttb: dict[str, list[WinebertoEntity]] = defaultdict(list)
    for entity in entities:
        entities_by_ttb[entity.ttb_id].append(entity)

    strategy_scores = {
        strategy: build_scores(
            strategy=strategy,
            common_ttbs=common_ttbs,
            expected_by_ttb=expected_by_ttb,
            entities_by_ttb=entities_by_ttb,
            engine_aggregates=engine_aggregates,
            entity_types_by_field=ENTITY_PRESETS[args.entity_preset],
            threshold=args.threshold,
            high_threshold=args.high_threshold,
            engine_soft_threshold=args.engine_soft_threshold,
            seed=args.seed,
        )
        for strategy in STRATEGIES
    }

    summary = {
        "model_id": args.model_id,
        "model_label": args.model_label or args.model_id,
        "model_license": args.model_license,
        "entity_preset": args.entity_preset,
        "text_source": args.text_source,
        "threshold": args.threshold,
        "high_threshold": args.high_threshold,
        "engine_soft_threshold": args.engine_soft_threshold,
        "entity_min_score": args.entity_min_score,
        "seed": args.seed,
        "application_count": len(common_ttbs),
        "entity_count": len(entities),
        "latency": latency_summary(latencies),
        "strategies": {
            strategy: {
                "overall": metrics_for_scores(scores),
                "overall_excluding_applicant_or_producer": metrics_for_scores(
                    scores_excluding(scores, {"applicant_or_producer"})
                ),
                "by_field": metrics_by_field(scores),
            }
            for strategy, scores in strategy_scores.items()
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_csv(output_dir / "entities.csv", entities, list(WinebertoEntity.__dataclass_fields__))
    for strategy, scores in strategy_scores.items():
        write_csv(output_dir / f"{strategy}_scores.csv", scores, list(WinebertoScore.__dataclass_fields__))

    print(json.dumps(summary, indent=2))
    print(f"Wrote domain-NER entity benchmark to {output_dir}")


if __name__ == "__main__":
    main()
