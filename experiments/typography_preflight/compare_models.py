"""Compare CPU typography classifiers on the corrected audit-v5 label policy.

This script trains side-by-side SVM, XGBoost, and CatBoost models for the
government-warning typography preflight. It uses synthetic crops generated with
the strict audit-v5 semantics:

* generated bold fonts are bold,
* generated non-bold fonts are not bold,
* degraded/unreadable crops are the only ``needs_review_unclear`` examples.

The experiment is CPU-only and writes generated features, sample crops, models,
and reports under gitignored ``data/work/typography-preflight/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import joblib
import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

from experiments.typography_preflight.build_audit_dataset import (
    FONT_WEIGHT_LABELS,
    HEADER_TEXT_LABELS,
    QUALITY_LABELS,
    FontRecord,
    apply_quality_recipe,
    choose_source_text,
    discover_fonts,
    render_heading,
)
from experiments.typography_preflight.features import (
    FeatureConfig,
    extract_feature_vector,
    feature_names,
    limit_cv2_threads,
)


try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - environment guard
    XGBClassifier = None

try:
    from catboost import CatBoostClassifier
except Exception:  # pragma: no cover - environment guard
    CatBoostClassifier = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/model-comparison-v1"
DEFAULT_FONT_ROOT = Path("/usr/share/fonts")

VISUAL_CLASSES = ("clearly_bold", "clearly_not_bold", "needs_review_unclear")
HEADER_CLASSES = ("correct", "incorrect", "needs_review_unclear")


@dataclass(frozen=True)
class SampleMeta:
    """Metadata for one generated comparison crop."""

    split: str
    sample_id: str
    font_weight_label: str
    header_text_label: str
    quality_label: str
    visual_font_decision_label: str
    header_decision_label: str
    source_text: str
    font_path: str
    font_family: str
    font_style: str
    font_size: int
    saved_crop: str


def main() -> None:
    """Generate features, train all requested models, and write reports."""

    args = parse_args()
    configure_cpu(args.threads)
    rng = random.Random(args.seed)
    np.random.seed(args.seed)
    limit_cv2_threads()

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["features", "manifests", "metrics", "models", "sample_crops"]:
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    fonts = discover_fonts(args.font_root)
    splits = split_font_pools(fonts, seed=args.seed)
    write_json(
        output_dir / "manifests/font_splits.json",
        {
            split: {
                label: {
                    "font_count": len(records),
                    "families": sorted({record.family for record in records}),
                    "fonts": [asdict(record) for record in records],
                }
                for label, records in pools.items()
            }
            for split, pools in splits.items()
        },
    )

    config = FeatureConfig()
    datasets = {
        "train": load_or_generate_split("train", args.train_samples, splits["train"], output_dir, config, args, rng),
        "validation": load_or_generate_split(
            "validation", args.validation_samples, splits["validation"], output_dir, config, args, rng
        ),
        "test": load_or_generate_split("test", args.test_samples, splits["test"], output_dir, config, args, rng),
    }

    write_json(output_dir / "manifests/feature_names.json", feature_names(config))

    tasks = {
        "visual_font_decision_label": VISUAL_CLASSES,
        "header_decision_label": HEADER_CLASSES,
    }
    results: list[dict[str, Any]] = []
    print(
        f"Generated/loaded splits: train={len(datasets['train'][0])}, "
        f"validation={len(datasets['validation'][0])}, test={len(datasets['test'][0])}",
        flush=True,
    )
    for task_name, class_names in tasks.items():
        print(f"Training task: {task_name}", flush=True)
        labels_by_split = {
            split: encode_labels([getattr(meta, task_name) for meta in metadata], class_names)
            for split, (_, metadata) in datasets.items()
        }
        for model_name in args.models:
            print(f"  model: {model_name}", flush=True)
            model = build_model(model_name, args, len(class_names))
            started = time.perf_counter()
            model.fit(datasets["train"][0], labels_by_split["train"])
            train_ms = (time.perf_counter() - started) * 1000
            validation_pred = predict_labels(model, datasets["validation"][0])
            test_pred = predict_labels(model, datasets["test"][0])
            validation_metrics = compute_multiclass_metrics(labels_by_split["validation"], validation_pred, class_names)
            test_metrics = compute_multiclass_metrics(labels_by_split["test"], test_pred, class_names)
            latency = measure_latency(model, datasets["test"][0], args.latency_rows)
            result = {
                "task": task_name,
                "model": model_name,
                "class_names": list(class_names),
                "train_ms": train_ms,
                "validation": validation_metrics,
                "test": test_metrics,
                "latency": latency,
            }
            results.append(result)
            write_confusion_csv(
                output_dir / f"metrics/{task_name}__{model_name}__test_confusion.csv",
                labels_by_split["test"],
                test_pred,
                class_names,
            )
            joblib.dump(
                {
                    "model": model,
                    "task": task_name,
                    "class_names": class_names,
                    "feature_config": asdict(config),
                    "feature_names": feature_names(config),
                    "metrics": result,
                },
                output_dir / f"models/{task_name}__{model_name}.joblib",
            )

    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seed": args.seed,
        "counts": {split: int(len(features)) for split, (features, _) in datasets.items()},
        "label_policy": {
            "font_weight_label": list(FONT_WEIGHT_LABELS),
            "header_text_label": list(HEADER_TEXT_LABELS),
            "quality_label": list(QUALITY_LABELS),
            "visual_font_decision_label": list(VISUAL_CLASSES),
            "header_decision_label": list(HEADER_CLASSES),
            "notes": [
                "No source borderline font class exists.",
                "Medium, semibold, demibold, light, thin, book, and regular fonts are non-bold.",
                "needs_review_unclear is reserved for unreadable/degraded crops.",
            ],
        },
        "results": results,
    }
    write_json(output_dir / "metrics/summary.json", summary)
    write_markdown_report(output_dir / "metrics/report.md", summary)
    print(json.dumps(summary, indent=2))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--font-root", type=Path, default=DEFAULT_FONT_ROOT)
    parser.add_argument("--train-samples", type=int, default=12_000)
    parser.add_argument("--validation-samples", type=int, default=3_000)
    parser.add_argument("--test-samples", type=int, default=3_000)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--sample-crop-limit", type=int, default=180)
    parser.add_argument("--tree-iterations", type=int, default=120)
    parser.add_argument("--svm-max-iter", type=int, default=2_000)
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--models", nargs="+", default=["svm", "xgboost", "catboost"])
    return parser.parse_args()


def configure_cpu(threads: int) -> None:
    """Keep this experiment CPU-only and polite to other jobs."""

    # Do not set CUDA_VISIBLE_DEVICES here. XGBoost 3.x can raise a CUDA driver
    # discovery error when CUDA is explicitly hidden, even with device="cpu".
    # The model config below pins XGBoost/CatBoost to CPU.
    for name in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        os.environ.setdefault(name, str(max(1, threads)))


def split_font_pools(fonts: dict[str, list[FontRecord]], *, seed: int) -> dict[str, dict[str, list[FontRecord]]]:
    """Split font pools by family within each strict weight class."""

    result: dict[str, dict[str, list[FontRecord]]] = {
        "train": {label: [] for label in FONT_WEIGHT_LABELS},
        "validation": {label: [] for label in FONT_WEIGHT_LABELS},
        "test": {label: [] for label in FONT_WEIGHT_LABELS},
    }
    rng = random.Random(seed)
    for label in FONT_WEIGHT_LABELS:
        by_family: dict[str, list[FontRecord]] = {}
        for record in fonts[label]:
            by_family.setdefault(record.family, []).append(record)
        families = sorted(by_family)
        rng.shuffle(families)
        train_cut = max(1, int(len(families) * 0.70))
        validation_cut = max(train_cut + 1, int(len(families) * 0.85))
        buckets = {
            "train": families[:train_cut],
            "validation": families[train_cut:validation_cut],
            "test": families[validation_cut:],
        }
        if not buckets["test"]:
            buckets["test"] = buckets["validation"][-1:] or buckets["train"][-1:]
        if not buckets["validation"]:
            buckets["validation"] = buckets["train"][-1:]
        for split, split_families in buckets.items():
            result[split][label] = [record for family in split_families for record in by_family[family]]
            if not result[split][label]:
                result[split][label] = list(fonts[label])
    return result


def load_or_generate_split(
    split: str,
    count: int,
    font_pools: dict[str, list[FontRecord]],
    output_dir: Path,
    config: FeatureConfig,
    args: argparse.Namespace,
    rng: random.Random,
) -> tuple[np.ndarray, list[SampleMeta]]:
    """Load cached feature split or generate a fresh one."""

    feature_path = output_dir / f"features/{split}.npz"
    manifest_path = output_dir / f"manifests/{split}_manifest.csv"
    if args.reuse_features and feature_path.exists() and manifest_path.exists():
        loaded = np.load(feature_path, allow_pickle=False)
        metadata = read_manifest(manifest_path)
        return loaded["features"].astype(np.float32), metadata

    features: list[np.ndarray] = []
    metadata: list[SampleMeta] = []
    combos = [(fw, ht, q) for fw in FONT_WEIGHT_LABELS for ht in HEADER_TEXT_LABELS for q in QUALITY_LABELS]
    split_rng = random.Random(f"{args.seed}:{split}")
    sample_dir = output_dir / "sample_crops" / split
    sample_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(count):
        font_weight_label, header_text_label, quality_label = combos[idx % len(combos)]
        if idx % len(combos) == 0:
            split_rng.shuffle(combos)
        font = split_rng.choice(font_pools[font_weight_label])
        source_text = choose_source_text(header_text_label, quality_label, split_rng)
        font_size = split_rng.randint(24, 46)
        image = render_heading(source_text, font, font_size)
        image = apply_quality_recipe(image, quality_label, split_rng)
        gray = np.array(image, dtype=np.uint8)
        vector = extract_feature_vector(gray, config)
        sample_id = f"{split}_{idx:06d}"
        saved_crop = ""
        if idx < args.sample_crop_limit:
            crop_path = sample_dir / f"{sample_id}__fw-{font_weight_label}__text-{header_text_label}__quality-{quality_label}.png"
            cv2.imwrite(str(crop_path), gray)
            saved_crop = str(crop_path.relative_to(output_dir))
        metadata.append(
            SampleMeta(
                split=split,
                sample_id=sample_id,
                font_weight_label=font_weight_label,
                header_text_label=header_text_label,
                quality_label=quality_label,
                visual_font_decision_label=visual_font_decision(font_weight_label, quality_label),
                header_decision_label=header_decision(header_text_label, quality_label),
                source_text=source_text,
                font_path=font.path,
                font_family=font.family,
                font_style=font.style,
                font_size=font_size,
                saved_crop=saved_crop,
            )
        )
        features.append(vector)

    feature_array = np.vstack(features).astype(np.float32)
    np.savez_compressed(feature_path, features=feature_array)
    write_manifest(manifest_path, metadata)
    return feature_array, metadata


def visual_font_decision(font_weight_label: str, quality_label: str) -> str:
    """Return the strict audit-v5 visual-font target."""

    if quality_label == "degraded":
        return "needs_review_unclear"
    if font_weight_label == "bold":
        return "clearly_bold"
    return "clearly_not_bold"


def header_decision(header_text_label: str, quality_label: str) -> str:
    """Return the strict audit-v5 header-text target."""

    if quality_label == "degraded":
        return "needs_review_unclear"
    return header_text_label


def build_model(name: str, args: argparse.Namespace, class_count: int) -> Any:
    """Build one classifier by name."""

    if name == "svm":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    SGDClassifier(
                        loss="hinge",
                        penalty="l2",
                        alpha=0.0001,
                        class_weight="balanced",
                        max_iter=args.svm_max_iter,
                        tol=1e-3,
                        n_jobs=1,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    if name == "xgboost":
        if XGBClassifier is None:
            raise SystemExit("xgboost is not installed in this Python environment.")
        return XGBClassifier(
            objective="multi:softprob",
            num_class=class_count,
            n_estimators=args.tree_iterations,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="mlogloss",
            tree_method="hist",
            device="cpu",
            n_jobs=max(1, args.threads),
            random_state=args.seed,
        )
    if name == "catboost":
        if CatBoostClassifier is None:
            raise SystemExit("catboost is not installed in this Python environment.")
        return CatBoostClassifier(
            iterations=args.tree_iterations,
            depth=6,
            learning_rate=0.08,
            loss_function="MultiClass",
            random_seed=args.seed,
            thread_count=max(1, args.threads),
            verbose=False,
            allow_writing_files=False,
        )
    raise SystemExit(f"Unknown model: {name}")


def encode_labels(labels: list[str], class_names: Iterable[str]) -> np.ndarray:
    """Encode string labels using a stable class order."""

    mapping = {name: idx for idx, name in enumerate(class_names)}
    return np.array([mapping[label] for label in labels], dtype=np.int64)


def compute_multiclass_metrics(y_true: np.ndarray, y_pred: np.ndarray, class_names: tuple[str, ...]) -> dict[str, Any]:
    """Compute model and government-safety metrics."""

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(range(len(class_names))),
        zero_division=0,
    )
    macro = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    weighted = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
    positive_class = 0
    false_clear_mask = y_true != positive_class
    false_clear_rate = float(((y_pred == positive_class) & false_clear_mask).sum() / max(false_clear_mask.sum(), 1))
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
        "false_clear_rate": false_clear_rate,
        "per_class": {
            class_name: {
                "precision": float(precision[idx]),
                "recall": float(recall[idx]),
                "f1": float(f1[idx]),
                "support": int(support[idx]),
            }
            for idx, class_name in enumerate(class_names)
        },
        "confusion": confusion_matrix(y_true, y_pred, labels=list(range(len(class_names)))).astype(int).tolist(),
        "examples": int(len(y_true)),
    }


def predict_labels(model: Any, features: np.ndarray) -> np.ndarray:
    """Return model predictions as a one-dimensional integer array."""

    return np.asarray(model.predict(features)).astype(np.int64).reshape(-1)


def measure_latency(model: Any, features: np.ndarray, rows: int) -> dict[str, float | int]:
    """Measure batch and per-row CPU prediction latency."""

    sample = features[: min(rows, len(features))]
    started = time.perf_counter()
    _ = predict_labels(model, sample)
    batch_ms = (time.perf_counter() - started) * 1000
    row_times: list[float] = []
    for row in sample[: min(200, len(sample))]:
        started = time.perf_counter()
        _ = predict_labels(model, row.reshape(1, -1))
        row_times.append((time.perf_counter() - started) * 1000)
    return {
        "rows": int(len(sample)),
        "batch_ms_per_crop": float(batch_ms / max(len(sample), 1)),
        "single_row_mean_ms": float(np.mean(row_times)) if row_times else 0.0,
        "single_row_p95_ms": float(np.percentile(row_times, 95)) if row_times else 0.0,
        "single_row_max_ms": float(np.max(row_times)) if row_times else 0.0,
    }


def write_confusion_csv(path: Path, y_true: np.ndarray, y_pred: np.ndarray, class_names: tuple[str, ...]) -> None:
    """Write a multiclass confusion matrix as CSV."""

    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual", *class_names])
        for idx, name in enumerate(class_names):
            writer.writerow([name, *matrix[idx].astype(int).tolist()])


def write_manifest(path: Path, metadata: list[SampleMeta]) -> None:
    """Write split metadata as CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(metadata[0]).keys()))
        writer.writeheader()
        for row in metadata:
            writer.writerow(asdict(row))


def read_manifest(path: Path) -> list[SampleMeta]:
    """Read split metadata from CSV."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [SampleMeta(**row) for row in csv.DictReader(handle)]


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a compact Markdown comparison report."""

    rows = []
    for result in summary["results"]:
        test = result["test"]
        latency = result["latency"]
        rows.append(
            "| {task} | {model} | {accuracy:.4f} | {macro_f1:.4f} | {weighted_f1:.4f} | "
            "{false_clear:.4f} | {batch:.4f} | {row:.4f} |".format(
                task=result["task"],
                model=result["model"],
                accuracy=test["accuracy"],
                macro_f1=test["macro_f1"],
                weighted_f1=test["weighted_f1"],
                false_clear=test["false_clear_rate"],
                batch=latency["batch_ms_per_crop"],
                row=latency["single_row_mean_ms"],
            )
        )
    content = f"""# Typography Model Comparison

Synthetic CPU-only comparison using strict audit-v5 label policy.

## Data

| Split | Crops |
|---|---:|
| Train | {summary['counts']['train']:,} |
| Validation | {summary['counts']['validation']:,} |
| Test | {summary['counts']['test']:,} |

## Test Metrics

| Task | Model | Accuracy | Macro F1 | Weighted F1 | False-Clear Rate | Batch ms/crop | Single-row mean ms |
|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

False clear means:

- visual task: non-bold or unreadable heading predicted as clearly bold,
- header task: incorrect or unreadable heading predicted as correct.
"""
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    """Write stable pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
