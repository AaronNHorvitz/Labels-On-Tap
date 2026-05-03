#!/usr/bin/env python
"""Train and evaluate a Transformer field-support pair classifier.

This experiment consumes the gitignored manifests produced by
``scripts/build_field_support_dataset.py``. It trains only on the train split,
tunes the decision threshold on validation, and evaluates the locked holdout
with the chosen threshold.

The current pair dataset is a weak-supervision bridge:

* positive candidate text comes from the same accepted public COLA field,
* negative candidate text is a same-field value shuffled from another
  application in the same split,
* OCR evidence is attached in a later stage.

That means this experiment tests whether a BERT-family arbiter can learn
field-support semantics and conservative thresholds on the new 6,000-record
corpus. It is not yet a full OCR-quality claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_DATASET_DIR = REPO_ROOT / "data/work/cola/field-support-datasets/field-support-v1"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data/work/field-support-models"


@dataclass(frozen=True)
class PairExample:
    """One field-support pair example."""

    pair_id: str
    split: str
    ttb_id: str
    field_name: str
    label: int
    target_expected: str
    candidate_text: str
    source_ttb_id: str
    product_type: str
    origin_bucket: str
    image_bucket: str
    imported: str


@dataclass(frozen=True)
class Metrics:
    """Binary classification metrics for one split or subgroup."""

    accuracy: float
    precision: float
    recall: float
    specificity: float
    f1: float
    false_clear_rate: float
    tp: int
    tn: int
    fp: int
    fn: int
    examples: int


class PairDataset:
    """Tiny PyTorch dataset over tokenized pair texts."""

    def __init__(self, encodings: dict[str, list[list[int]]], labels: list[int]) -> None:
        self.encodings = encodings
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> dict[str, Any]:
        import torch

        item = {
            key: torch.tensor(values[index], dtype=torch.long)
            for key, values in self.encodings.items()
        }
        item["labels"] = torch.tensor(self.labels[index], dtype=torch.long)
        return item


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--model-id", default="distilroberta-base")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--false-clear-tolerance", type=float, default=0.005)
    parser.add_argument("--threshold-step", type=float, default=0.01)
    parser.add_argument("--max-train-rows", type=int, default=None)
    parser.add_argument("--max-validation-rows", type=int, default=None)
    parser.add_argument("--max-holdout-rows", type=int, default=None)
    parser.add_argument("--latency-rows", type=int, default=1000)
    parser.add_argument(
        "--cpu-latency-rows",
        type=int,
        default=0,
        help="After training/evaluation, also benchmark this many holdout pairs on CPU.",
    )
    parser.add_argument("--save-model", action="store_true")
    return parser.parse_args()


def clean_text(value: object) -> str:
    """Return one-line text suitable for a model prompt."""

    if value is None:
        return ""
    return " ".join(str(value).split())


def load_rows(path: Path) -> list[dict[str, str]]:
    """Load CSV rows."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def example_from_row(row: dict[str, str]) -> PairExample:
    """Convert one CSV row to a typed example."""

    target_expected = row.get("target_expected") or row.get("expected") or ""
    candidate_text = row.get("candidate_text") or row.get("expected") or ""
    return PairExample(
        pair_id=clean_text(row.get("pair_id")),
        split=clean_text(row.get("split")),
        ttb_id=clean_text(row.get("ttb_id")),
        field_name=clean_text(row.get("field_name")),
        label=int(row.get("label") or 0),
        target_expected=clean_text(target_expected),
        candidate_text=clean_text(candidate_text),
        source_ttb_id=clean_text(row.get("source_ttb_id")),
        product_type=clean_text(row.get("product_type")),
        origin_bucket=clean_text(row.get("origin_bucket")),
        image_bucket=clean_text(row.get("image_bucket")),
        imported=clean_text(row.get("imported")),
    )


def load_examples(dataset_dir: Path, split: str, limit: int | None, seed: int) -> list[PairExample]:
    """Load pair examples for one split, optionally with deterministic subsampling."""

    rows = [example_from_row(row) for row in load_rows(dataset_dir / f"{split}_field_pairs.csv")]
    if limit is not None and limit < len(rows):
        rng = random.Random(seed)
        rows = rng.sample(rows, limit)
        rows.sort(key=lambda item: item.pair_id)
    return rows


def pair_text(example: PairExample) -> str:
    """Build the text-pair prompt seen by the classifier."""

    field = example.field_name.replace("_", " ")
    return (
        f"field: {field}\n"
        f"application value: {example.target_expected}\n"
        f"candidate evidence: {example.candidate_text}\n"
        f"product type: {example.product_type}\n"
        f"origin: {example.origin_bucket}\n"
        f"imported: {example.imported}\n"
        f"panel complexity: {example.image_bucket}"
    )


def set_reproducible_seed(seed: int) -> None:
    """Set Python, NumPy, and PyTorch random seeds."""

    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def tokenize_examples(tokenizer: Any, examples: list[PairExample], max_length: int) -> PairDataset:
    """Tokenize examples for model training or inference."""

    texts = [pair_text(example) for example in examples]
    labels = [example.label for example in examples]
    encodings = tokenizer(
        texts,
        max_length=max_length,
        padding="max_length",
        truncation=True,
    )
    return PairDataset(encodings, labels)


def safe_divide(numerator: int | float, denominator: int | float) -> float:
    """Divide and return 0.0 for empty denominators."""

    return float(numerator / denominator) if denominator else 0.0


def metrics_from_predictions(labels: list[int], probabilities: list[float], threshold: float) -> Metrics:
    """Compute binary metrics for one probability threshold."""

    tp = tn = fp = fn = 0
    for label, probability in zip(labels, probabilities, strict=True):
        predicted = int(probability >= threshold)
        if label == 1 and predicted == 1:
            tp += 1
        elif label == 0 and predicted == 0:
            tn += 1
        elif label == 0 and predicted == 1:
            fp += 1
        elif label == 1 and predicted == 0:
            fn += 1
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    specificity = safe_divide(tn, tn + fp)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    return Metrics(
        accuracy=round(safe_divide(tp + tn, tp + tn + fp + fn), 6),
        precision=round(precision, 6),
        recall=round(recall, 6),
        specificity=round(specificity, 6),
        f1=round(f1, 6),
        false_clear_rate=round(safe_divide(fp, fp + tn), 6),
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        examples=tp + tn + fp + fn,
    )


def threshold_candidates(step: float) -> list[float]:
    """Return probability thresholds from 0.01 through 0.99."""

    count = int(math.floor(0.98 / step))
    values = [round(0.01 + index * step, 4) for index in range(count + 1)]
    return [value for value in values if 0.0 < value < 1.0]


def tune_threshold(
    labels: list[int],
    probabilities: list[float],
    *,
    false_clear_tolerance: float,
    step: float,
) -> tuple[float, Metrics, str]:
    """Tune threshold on validation under a false-clear cap."""

    scored = [
        (threshold, metrics_from_predictions(labels, probabilities, threshold))
        for threshold in threshold_candidates(step)
    ]
    eligible = [
        item
        for item in scored
        if item[1].false_clear_rate <= false_clear_tolerance
    ]
    if eligible:
        threshold, metrics = max(
            eligible,
            key=lambda item: (item[1].f1, item[1].recall, item[1].specificity, item[0]),
        )
        return threshold, metrics, "false_clear_constrained_max_f1"
    threshold, metrics = max(
        scored,
        key=lambda item: (-item[1].false_clear_rate, item[1].f1, item[1].recall, item[0]),
    )
    return threshold, metrics, "lowest_false_clear_fallback"


def batch_iterable(items: list[Any], batch_size: int) -> list[list[Any]]:
    """Chunk a list into batches."""

    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def predict_probabilities(
    *,
    model: Any,
    dataset: PairDataset,
    device: Any,
    batch_size: int,
) -> tuple[list[float], list[int], list[float]]:
    """Run inference and return positive probabilities, labels, and batch latencies."""

    import torch
    from torch.utils.data import DataLoader

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    probabilities: list[float] = []
    labels: list[int] = []
    latencies: list[float] = []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            started = perf_counter()
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(**batch)
            probs = torch.softmax(output.logits, dim=-1)[:, 1].detach().cpu().tolist()
            probabilities.extend(float(prob) for prob in probs)
            labels.extend(int(label) for label in batch["labels"].detach().cpu().tolist())
            elapsed_ms = (perf_counter() - started) * 1000
            latencies.extend([elapsed_ms / max(1, len(probs))] * len(probs))
    return probabilities, labels, latencies


def benchmark_cpu_latency(
    *,
    model: Any,
    tokenizer: Any,
    examples: list[PairExample],
    max_length: int,
    batch_size: int,
) -> dict[str, float]:
    """Benchmark trained model inference on CPU for deployment planning."""

    if not examples:
        return latency_summary([])
    import torch

    cpu = torch.device("cpu")
    model.to(cpu)
    dataset = tokenize_examples(tokenizer, examples, max_length)
    _, _, latencies = predict_probabilities(
        model=model,
        dataset=dataset,
        device=cpu,
        batch_size=batch_size,
    )
    return latency_summary(latencies)


def train_one_epoch(
    *,
    model: Any,
    dataset: PairDataset,
    device: Any,
    batch_size: int,
    optimizer: Any,
) -> float:
    """Train for one epoch and return mean loss."""

    from torch.utils.data import DataLoader

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    losses: list[float] = []
    model.train()
    for batch in loader:
        batch = {key: value.to(device) for key, value in batch.items()}
        optimizer.zero_grad(set_to_none=True)
        output = model(**batch)
        output.loss.backward()
        optimizer.step()
        losses.append(float(output.loss.detach().cpu()))
    return mean(losses) if losses else 0.0


def latency_summary(latencies: list[float]) -> dict[str, float]:
    """Return latency summary in milliseconds per pair example."""

    if not latencies:
        return {"mean_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {
        "mean_ms": round(mean(ordered), 4),
        "median_ms": round(median(ordered), 4),
        "p95_ms": round(ordered[p95_index], 4),
        "max_ms": round(max(ordered), 4),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_predictions(
    path: Path,
    examples: list[PairExample],
    probabilities: list[float],
    threshold: float,
) -> None:
    """Write split predictions as CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pair_id",
        "split",
        "ttb_id",
        "field_name",
        "label",
        "probability",
        "prediction",
        "target_expected",
        "candidate_text",
        "source_ttb_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for example, probability in zip(examples, probabilities, strict=True):
            writer.writerow(
                {
                    "pair_id": example.pair_id,
                    "split": example.split,
                    "ttb_id": example.ttb_id,
                    "field_name": example.field_name,
                    "label": example.label,
                    "probability": round(probability, 8),
                    "prediction": int(probability >= threshold),
                    "target_expected": example.target_expected,
                    "candidate_text": example.candidate_text,
                    "source_ttb_id": example.source_ttb_id,
                }
            )


def field_metrics(
    examples: list[PairExample],
    labels: list[int],
    probabilities: list[float],
    threshold: float,
) -> dict[str, dict[str, Any]]:
    """Compute metrics by field name."""

    grouped: dict[str, tuple[list[int], list[float]]] = {}
    for example, label, probability in zip(examples, labels, probabilities, strict=True):
        if example.field_name not in grouped:
            grouped[example.field_name] = ([], [])
        grouped[example.field_name][0].append(label)
        grouped[example.field_name][1].append(probability)
    return {
        field_name: asdict(metrics_from_predictions(field_labels, field_probs, threshold))
        for field_name, (field_labels, field_probs) in sorted(grouped.items())
    }


def main() -> None:
    """Train, tune, and evaluate the requested Transformer classifier."""

    args = parse_args()
    args.dataset_dir = args.dataset_dir if args.dataset_dir.is_absolute() else REPO_ROOT / args.dataset_dir
    args.output_root = args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root
    run_name = args.run_name or args.model_id.replace("/", "__")
    output_dir = args.output_root / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    set_reproducible_seed(args.seed)

    import torch
    from torch.optim import AdamW
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but torch.cuda.is_available() is false.")
    device = torch.device(args.device)

    train_examples = load_examples(args.dataset_dir, "train", args.max_train_rows, args.seed + 1)
    validation_examples = load_examples(args.dataset_dir, "validation", args.max_validation_rows, args.seed + 2)
    holdout_examples = load_examples(args.dataset_dir, "holdout", args.max_holdout_rows, args.seed + 3)

    print(f"Model: {args.model_id}")
    print(f"Device: {device}")
    print(f"Train examples: {len(train_examples)}")
    print(f"Validation examples: {len(validation_examples)}")
    print(f"Holdout examples: {len(holdout_examples)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_id, num_labels=2)
    model.to(device)

    train_dataset = tokenize_examples(tokenizer, train_examples, args.max_length)
    validation_dataset = tokenize_examples(tokenizer, validation_examples, args.max_length)
    holdout_dataset = tokenize_examples(tokenizer, holdout_examples, args.max_length)

    optimizer = AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    training_log: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        started = perf_counter()
        loss = train_one_epoch(
            model=model,
            dataset=train_dataset,
            device=device,
            batch_size=args.batch_size,
            optimizer=optimizer,
        )
        elapsed = perf_counter() - started
        print(f"epoch {epoch}/{args.epochs}: loss={loss:.6f} elapsed={elapsed:.1f}s")
        training_log.append({"epoch": epoch, "loss": round(loss, 6), "elapsed_seconds": round(elapsed, 3)})

    validation_probabilities, validation_labels, validation_latencies = predict_probabilities(
        model=model,
        dataset=validation_dataset,
        device=device,
        batch_size=args.eval_batch_size,
    )
    threshold, validation_metrics, threshold_policy = tune_threshold(
        validation_labels,
        validation_probabilities,
        false_clear_tolerance=args.false_clear_tolerance,
        step=args.threshold_step,
    )
    print(f"threshold={threshold:.4f} policy={threshold_policy}")
    print(f"validation={validation_metrics}")

    train_probabilities, train_labels, train_latencies = predict_probabilities(
        model=model,
        dataset=train_dataset,
        device=device,
        batch_size=args.eval_batch_size,
    )
    holdout_probabilities, holdout_labels, holdout_latencies = predict_probabilities(
        model=model,
        dataset=holdout_dataset,
        device=device,
        batch_size=args.eval_batch_size,
    )

    split_metrics = {
        "train": asdict(metrics_from_predictions(train_labels, train_probabilities, threshold)),
        "validation": asdict(metrics_from_predictions(validation_labels, validation_probabilities, threshold)),
        "holdout": asdict(metrics_from_predictions(holdout_labels, holdout_probabilities, threshold)),
    }
    per_field = {
        "train": field_metrics(train_examples, train_labels, train_probabilities, threshold),
        "validation": field_metrics(validation_examples, validation_labels, validation_probabilities, threshold),
        "holdout": field_metrics(holdout_examples, holdout_labels, holdout_probabilities, threshold),
    }
    latency_rows = max(0, min(args.latency_rows, len(holdout_latencies)))
    latencies_for_summary = holdout_latencies[:latency_rows] if latency_rows else []
    cpu_latency_rows = max(0, min(args.cpu_latency_rows, len(holdout_examples)))
    cpu_latency = {}
    if cpu_latency_rows:
        cpu_latency = benchmark_cpu_latency(
            model=model,
            tokenizer=tokenizer,
            examples=holdout_examples[:cpu_latency_rows],
            max_length=args.max_length,
            batch_size=args.eval_batch_size,
        )

    summary = {
        "model_id": args.model_id,
        "run_name": run_name,
        "dataset_dir": str(args.dataset_dir.relative_to(REPO_ROOT)),
        "device": str(device),
        "seed": args.seed,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "learning_rate": args.learning_rate,
        "max_length": args.max_length,
        "threshold": threshold,
        "threshold_policy": threshold_policy,
        "false_clear_tolerance": args.false_clear_tolerance,
        "training_log": training_log,
        "split_metrics": split_metrics,
        "per_field_metrics": per_field,
        "latency_ms_per_pair": latency_summary(latencies_for_summary),
        "cpu_latency_ms_per_pair": cpu_latency,
        "notes": [
            "This run trains on weak field-pair supervision from accepted public COLA application fields.",
            "It does not yet include OCR candidate evidence; attach OCR outputs before making an OCR-quality claim.",
            "Holdout metrics use the locked 3,000-application cohort from the current split.",
        ],
    }
    write_json(output_dir / "metrics.json", summary)
    write_predictions(output_dir / "train_predictions.csv", train_examples, train_probabilities, threshold)
    write_predictions(output_dir / "validation_predictions.csv", validation_examples, validation_probabilities, threshold)
    write_predictions(output_dir / "holdout_predictions.csv", holdout_examples, holdout_probabilities, threshold)

    if args.save_model:
        model_dir = output_dir / "model"
        model.save_pretrained(model_dir)
        tokenizer.save_pretrained(model_dir)

    print(f"Wrote outputs to {output_dir.relative_to(REPO_ROOT)}")
    print(json.dumps(split_metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
