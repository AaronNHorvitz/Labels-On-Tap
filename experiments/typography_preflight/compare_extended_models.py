"""Extended CPU typography-model comparison with an 80/20 split.

This experiment compares classical and lightweight tabular learners on the
strict ``audit-v5`` government-warning typography targets:

* SVM-style linear margin classifier,
* XGBoost,
* LightGBM,
* logistic regression,
* a small multi-layer perceptron,
* a strict-veto ensemble over the fitted base models.

The strict-veto ensemble is intentionally conservative. It only predicts the
positive class when every base model predicts that positive class. Any
disagreement routes to ``needs_review_unclear`` unless all models agree on the
same non-positive class.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from experiments.typography_preflight.build_audit_dataset import FONT_WEIGHT_LABELS, FontRecord, discover_fonts
from experiments.typography_preflight.compare_models import (
    DEFAULT_FONT_ROOT,
    HEADER_CLASSES,
    ROOT,
    VISUAL_CLASSES,
    compute_multiclass_metrics,
    configure_cpu,
    encode_labels,
    load_or_generate_split,
    measure_latency,
    predict_labels,
    write_confusion_csv,
    write_json,
)
from experiments.typography_preflight.features import FeatureConfig, feature_names, limit_cv2_threads

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional experiment dependency
    XGBClassifier = None

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - optional experiment dependency
    LGBMClassifier = None


DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/model-comparison-extended-80-20-v1"
BASE_MODEL_NAMES = ("svm", "xgboost", "lightgbm", "logistic_regression", "mlp")


class StrictVetoEnsemble:
    """Conservative argmax ensemble for the typography preflight.

    Parameters
    ----------
    models:
        Fitted base estimators.
    review_class:
        Class index used for ``needs_review_unclear``.
    positive_class:
        Class index that means safe support for the regulatory property under
        test, such as ``clearly_bold`` or ``correct``.
    """

    def __init__(self, models: list[Any], *, review_class: int = 2, positive_class: int = 0) -> None:
        self.models = models
        self.review_class = review_class
        self.positive_class = positive_class

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict with a unanimity requirement for positive clearance."""

        predictions = np.vstack([predict_labels(model, features) for model in self.models])
        output = np.full(predictions.shape[1], self.review_class, dtype=np.int64)
        unanimous = np.all(predictions == predictions[0], axis=0)
        unanimous_positive = unanimous & (predictions[0] == self.positive_class)
        unanimous_non_positive = unanimous & (predictions[0] != self.positive_class)
        output[unanimous_positive] = self.positive_class
        output[unanimous_non_positive] = predictions[0, unanimous_non_positive]
        return output


def main() -> None:
    """Run the extended model comparison and write local reports."""

    args = parse_args()
    configure_cpu(args.threads)
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    limit_cv2_threads()
    np.random.seed(args.seed)
    rng = random.Random(args.seed)

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["features", "manifests", "metrics", "models", "sample_crops"]:
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    train_samples = int(round(args.total_samples * args.train_fraction))
    test_samples = args.total_samples - train_samples
    fonts = discover_fonts(args.font_root)
    font_splits = split_font_pools_80_20(fonts, seed=args.seed, train_fraction=args.train_fraction)
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
            for split, pools in font_splits.items()
        },
    )

    config = FeatureConfig()
    datasets = {
        "train": load_or_generate_split("train", train_samples, font_splits["train"], output_dir, config, args, rng),
        "test": load_or_generate_split("test", test_samples, font_splits["test"], output_dir, config, args, rng),
    }
    write_json(output_dir / "manifests/feature_names.json", feature_names(config))

    tasks = {
        "visual_font_decision_label": VISUAL_CLASSES,
        "header_decision_label": HEADER_CLASSES,
    }
    all_results: list[dict[str, Any]] = []
    print(
        f"Generated/loaded 80/20 split: train={len(datasets['train'][0])}, test={len(datasets['test'][0])}",
        flush=True,
    )
    for task_name, class_names in tasks.items():
        print(f"Training task: {task_name}", flush=True)
        y_train = encode_labels([getattr(meta, task_name) for meta in datasets["train"][1]], class_names)
        y_test = encode_labels([getattr(meta, task_name) for meta in datasets["test"][1]], class_names)
        fitted_models: dict[str, Any] = {}
        task_results: list[dict[str, Any]] = []

        for model_name in args.models:
            print(f"  model: {model_name}", flush=True)
            model = build_model(model_name, args, len(class_names))
            started = time.perf_counter()
            model.fit(datasets["train"][0], y_train)
            train_ms = (time.perf_counter() - started) * 1000
            fitted_models[model_name] = model
            result = evaluate_model(
                model,
                task_name=task_name,
                model_name=model_name,
                class_names=class_names,
                y_test=y_test,
                test_features=datasets["test"][0],
                train_ms=train_ms,
                output_dir=output_dir,
                latency_rows=args.latency_rows,
            )
            task_results.append(result)
            all_results.append(result)
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

        ensemble_names = [name for name in args.ensemble_models if name in fitted_models]
        if ensemble_names:
            print(f"  model: strict_veto_ensemble ({', '.join(ensemble_names)})", flush=True)
            ensemble = StrictVetoEnsemble([fitted_models[name] for name in ensemble_names])
            result = evaluate_model(
                ensemble,
                task_name=task_name,
                model_name="strict_veto_ensemble",
                class_names=class_names,
                y_test=y_test,
                test_features=datasets["test"][0],
                train_ms=0.0,
                output_dir=output_dir,
                latency_rows=args.latency_rows,
                extra={"base_models": ensemble_names},
            )
            task_results.append(result)
            all_results.append(result)

    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seed": args.seed,
        "split": {"train_fraction": args.train_fraction, "train": train_samples, "test": test_samples},
        "label_policy": {
            "visual_font_decision_label": list(VISUAL_CLASSES),
            "header_decision_label": list(HEADER_CLASSES),
            "notes": [
                "Generated bold fonts are bold.",
                "Generated non-bold fonts are not bold.",
                "needs_review_unclear is reserved for degraded/unreadable crops.",
                "Strict-veto ensemble only clears the positive class on unanimous base-model support.",
            ],
        },
        "results": all_results,
    }
    write_json(output_dir / "metrics/summary.json", summary)
    write_markdown_report(output_dir / "metrics/report.md", summary)
    print(json.dumps(summary, indent=2))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--font-root", type=Path, default=DEFAULT_FONT_ROOT)
    parser.add_argument("--total-samples", type=int, default=10_000)
    parser.add_argument("--train-fraction", type=float, default=0.80)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--sample-crop-limit", type=int, default=180)
    parser.add_argument("--tree-iterations", type=int, default=120)
    parser.add_argument("--svm-max-iter", type=int, default=2_000)
    parser.add_argument("--logistic-max-iter", type=int, default=500)
    parser.add_argument("--mlp-max-iter", type=int, default=120)
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--models", nargs="+", default=list(BASE_MODEL_NAMES))
    parser.add_argument("--ensemble-models", nargs="+", default=list(BASE_MODEL_NAMES))
    return parser.parse_args()


def split_font_pools_80_20(
    fonts: dict[str, list[FontRecord]], *, seed: int, train_fraction: float
) -> dict[str, dict[str, list[FontRecord]]]:
    """Split font pools by family into train/test buckets."""

    result: dict[str, dict[str, list[FontRecord]]] = {
        "train": {label: [] for label in FONT_WEIGHT_LABELS},
        "test": {label: [] for label in FONT_WEIGHT_LABELS},
    }
    rng = random.Random(seed)
    for label in FONT_WEIGHT_LABELS:
        by_family: dict[str, list[FontRecord]] = {}
        for record in fonts[label]:
            by_family.setdefault(record.family, []).append(record)
        families = sorted(by_family)
        rng.shuffle(families)
        train_cut = min(max(1, int(round(len(families) * train_fraction))), max(1, len(families) - 1))
        buckets = {
            "train": families[:train_cut],
            "test": families[train_cut:] or families[-1:],
        }
        for split, split_families in buckets.items():
            result[split][label] = [record for family in split_families for record in by_family[family]]
            if not result[split][label]:
                result[split][label] = list(fonts[label])
    return result


def build_model(name: str, args: argparse.Namespace, class_count: int) -> Any:
    """Build one extended comparison model."""

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
    if name == "lightgbm":
        if LGBMClassifier is None:
            raise SystemExit("lightgbm is not installed in this Python environment.")
        return LGBMClassifier(
            objective="multiclass",
            num_class=class_count,
            n_estimators=args.tree_iterations,
            learning_rate=0.06,
            num_leaves=31,
            max_depth=-1,
            subsample=0.9,
            colsample_bytree=0.9,
            class_weight="balanced",
            n_jobs=max(1, args.threads),
            random_state=args.seed,
            verbosity=-1,
        )
    if name == "logistic_regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        solver="saga",
                        l1_ratio=0,
                        C=1.0,
                        class_weight="balanced",
                        max_iter=args.logistic_max_iter,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    if name == "mlp":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    MLPClassifier(
                        hidden_layer_sizes=(96,),
                        activation="relu",
                        alpha=0.0005,
                        batch_size=256,
                        early_stopping=True,
                        n_iter_no_change=8,
                        learning_rate_init=0.001,
                        max_iter=args.mlp_max_iter,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    raise SystemExit(f"Unknown model: {name}")


def evaluate_model(
    model: Any,
    *,
    task_name: str,
    model_name: str,
    class_names: tuple[str, ...],
    y_test: np.ndarray,
    test_features: np.ndarray,
    train_ms: float,
    output_dir: Path,
    latency_rows: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one fitted model and persist its test confusion matrix."""

    test_pred = predict_labels(model, test_features)
    test_metrics = compute_multiclass_metrics(y_test, test_pred, class_names)
    latency = measure_latency(model, test_features, latency_rows)
    write_confusion_csv(output_dir / f"metrics/{task_name}__{model_name}__test_confusion.csv", y_test, test_pred, class_names)
    result: dict[str, Any] = {
        "task": task_name,
        "model": model_name,
        "class_names": list(class_names),
        "train_ms": train_ms,
        "test": test_metrics,
        "latency": latency,
    }
    if extra:
        result.update(extra)
    return result


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a Markdown report for the extended comparison."""

    rows = []
    for result in summary["results"]:
        test = result["test"]
        latency = result["latency"]
        rows.append(
            "| {task} | {model} | {accuracy:.4f} | {macro_f1:.4f} | {weighted_f1:.4f} | "
            "{false_clear:.4f} | {train:.1f} | {batch:.4f} | {row:.4f} |".format(
                task=result["task"],
                model=result["model"],
                accuracy=test["accuracy"],
                macro_f1=test["macro_f1"],
                weighted_f1=test["weighted_f1"],
                false_clear=test["false_clear_rate"],
                train=result["train_ms"],
                batch=latency["batch_ms_per_crop"],
                row=latency["single_row_mean_ms"],
            )
        )
    content = f"""# Extended Typography Model Comparison

Synthetic CPU-only comparison using strict audit-v5 label policy and an 80/20
train/test split.

## Data

| Split | Crops |
|---|---:|
| Train | {summary['split']['train']:,} |
| Test | {summary['split']['test']:,} |

## Test Metrics

| Task | Model | Accuracy | Macro F1 | Weighted F1 | False-Clear Rate | Train ms | Batch ms/crop | Single-row mean ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

False clear means:

- visual task: non-bold or unreadable heading predicted as clearly bold,
- header task: incorrect or unreadable heading predicted as correct.

Strict veto ensemble policy:

- positive class clears only when every base model predicts the positive class,
- unanimous non-positive predictions are preserved,
- all disagreements route to needs_review_unclear.
"""
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
