"""Compare classical typography classifiers on the audit-v6 image set.

This experiment retrains the non-CNN baselines against the same ``audit-v6``
train/validation/test split used by the MobileNetV3 challenger. The target is
``boldness_label``:

``bold`` / ``not_bold`` / ``unreadable_review`` / ``not_applicable``.

The positive class is ``bold``. The safety metric is false-clear rate:

``actual != bold`` but the model predicts ``bold``.

All model artifacts and metrics are written under gitignored ``data/work/``.
No runtime model is promoted by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from experiments.typography_preflight.features import (
    FeatureConfig,
    extract_feature_vector,
    feature_names,
    limit_cv2_threads,
)

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - optional experiment dependency
    LGBMClassifier = None

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional experiment dependency
    XGBClassifier = None

try:
    from catboost import CatBoostClassifier
except Exception:  # pragma: no cover - optional experiment dependency
    CatBoostClassifier = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_DIR = ROOT / "data/work/typography-preflight/audit-v6"
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/model-comparison-audit-v6-defensible-v2"
CLASS_NAMES = ("bold", "not_bold", "unreadable_review", "not_applicable")
POSITIVE_CLASS = "bold"
REVIEW_CLASS = "unreadable_review"
BASE_MODELS = ("svm", "xgboost", "lightgbm", "logistic_regression", "mlp", "catboost")


@dataclass(frozen=True)
class AuditRow:
    """One audit-v6 crop row and its provenance."""

    split: str
    sample_id: str
    crop_path: str
    boldness_label: str
    source_kind: str
    source_origin: str
    ttb_id: str
    panel_warning_label: str
    heading_text_label: str
    quality_label: str


class StrictVetoEnsemble:
    """Conservative ensemble that only clears bold on unanimous support."""

    def __init__(self, models: dict[str, Any], *, review_class: int, positive_class: int) -> None:
        self.models = models
        self.review_class = review_class
        self.positive_class = positive_class

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict labels with a strict positive-clear veto."""

        predictions = np.vstack([predict_labels(model, features) for model in self.models.values()])
        output = np.full(predictions.shape[1], self.review_class, dtype=np.int64)
        unanimous = np.all(predictions == predictions[0], axis=0)
        unanimous_positive = unanimous & (predictions[0] == self.positive_class)
        unanimous_non_positive = unanimous & (predictions[0] != self.positive_class)
        output[unanimous_positive] = self.positive_class
        output[unanimous_non_positive] = predictions[0, unanimous_non_positive]
        return output


class StackerPipeline:
    """Run fitted base learners and a fitted stacker as one predictor."""

    def __init__(self, base_models: dict[str, Any], stacker: Any) -> None:
        self.base_models = base_models
        self.stacker = stacker

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict from raw feature vectors."""

        return predict_labels(self.stacker, build_stacker_features(self.base_models, features))

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Return probabilities from the stacker."""

        return np.asarray(self.stacker.predict_proba(build_stacker_features(self.base_models, features)), dtype=np.float64)


class PositiveRejectWrapper:
    """Route weak positive predictions to review using a tuned probability threshold."""

    def __init__(self, model: Any, *, threshold: float, positive_class: int, review_class: int) -> None:
        self.model = model
        self.threshold = threshold
        self.positive_class = positive_class
        self.review_class = review_class

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict and reject weak positive clears."""

        probabilities = np.asarray(self.model.predict_proba(features), dtype=np.float64)
        raw = probabilities.argmax(axis=1).astype(np.int64)
        weak_positive = (raw == self.positive_class) & (probabilities[:, self.positive_class] < self.threshold)
        raw[weak_positive] = self.review_class
        return raw

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Return wrapped model probabilities for diagnostics."""

        return np.asarray(self.model.predict_proba(features), dtype=np.float64)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target", choices=["boldness_label"], default="boldness_label")
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--tree-iterations", type=int, default=160)
    parser.add_argument("--stacker-iterations", type=int, default=140)
    parser.add_argument("--svm-max-iter", type=int, default=3_000)
    parser.add_argument("--logistic-max-iter", type=int, default=1_000)
    parser.add_argument("--mlp-max-iter", type=int, default=180)
    parser.add_argument("--target-false-clear", type=float, default=0.0025)
    parser.add_argument("--meta-fraction", type=float, default=0.20)
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--models", nargs="+", default=list(BASE_MODELS))
    return parser.parse_args()


def main() -> None:
    """Run the audit-v6 baseline comparison."""

    args = parse_args()
    configure_cpu(args.threads)
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    warnings.filterwarnings("ignore", message="The max_iter was reached.*")
    limit_cv2_threads()
    np.random.seed(args.seed)

    audit_dir = resolve_path(args.audit_dir)
    output_dir = resolve_path(args.output_dir)
    for child in ("features", "manifests", "metrics", "models"):
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    rows_by_split = load_manifest(audit_dir / "manifest.csv")
    config = FeatureConfig()
    datasets = {
        split: load_or_extract_features(
            split=split,
            rows=rows,
            audit_dir=audit_dir,
            output_dir=output_dir,
            config=config,
            reuse=args.reuse_features,
        )
        for split, rows in rows_by_split.items()
    }
    write_json(output_dir / "manifests/feature_names.json", feature_names(config))
    write_json(
        output_dir / "manifests/split_counts.json",
        {
            split: {
                "rows": len(rows),
                "labels": dict(sorted(Counter(row.boldness_label for row in rows).items())),
                "source_kind": dict(sorted(Counter(row.source_kind for row in rows).items())),
                "source_origin": dict(sorted(Counter(row.source_origin for row in rows).items())),
            }
            for split, rows in rows_by_split.items()
        },
    )

    class_to_idx = {name: idx for idx, name in enumerate(CLASS_NAMES)}
    y = {
        split: np.array([class_to_idx[row.boldness_label] for row in rows_by_split[split]], dtype=np.int64)
        for split in ("train", "validation", "test")
    }
    base_train_idx, meta_train_idx = make_base_meta_split(y["train"], meta_fraction=args.meta_fraction, seed=args.seed)
    training_views = {
        "base_train": (
            datasets["train"][0][base_train_idx],
            [datasets["train"][1][idx] for idx in base_train_idx],
        ),
        "meta_train": (
            datasets["train"][0][meta_train_idx],
            [datasets["train"][1][idx] for idx in meta_train_idx],
        ),
        "validation": datasets["validation"],
        "test": datasets["test"],
    }
    y_views = {
        "base_train": y["train"][base_train_idx],
        "meta_train": y["train"][meta_train_idx],
        "validation": y["validation"],
        "test": y["test"],
    }
    base_results: list[dict[str, Any]] = []
    ensemble_results: list[dict[str, Any]] = []
    fitted_models: dict[str, Any] = {}
    print(
        "Loaded audit-v6 features: "
        f"base_train={len(y_views['base_train'])}, meta_train={len(y_views['meta_train'])}, "
        f"validation={len(y_views['validation'])}, test={len(y_views['test'])}",
        flush=True,
    )

    for model_name in args.models:
        print(f"Training baseline: {model_name}", flush=True)
        model = build_model(model_name, args)
        started = time.perf_counter()
        model.fit(training_views["base_train"][0], y_views["base_train"])
        train_ms = (time.perf_counter() - started) * 1000
        fitted_models[model_name] = model
        result = evaluate_predictor(
            model,
            model_name=model_name,
            train_ms=train_ms,
            datasets={
                "train": training_views["base_train"],
                "validation": training_views["validation"],
                "test": training_views["test"],
            },
            y={
                "train": y_views["base_train"],
                "validation": y_views["validation"],
                "test": y_views["test"],
            },
            test_rows=rows_by_split["test"],
            latency_rows=args.latency_rows,
            extra={"fit_split": "base_train"},
        )
        base_results.append(result)
        write_confusion_csv(output_dir / f"metrics/{model_name}__test_confusion.csv", result["test"]["confusion"])
        joblib.dump(
            {
                "model": model,
                "class_names": CLASS_NAMES,
                "feature_config": asdict(config),
                "feature_names": feature_names(config),
                "metrics": result,
            },
            output_dir / f"models/{model_name}.joblib",
        )

    meta_stack = build_stacker_features(fitted_models, training_views["meta_train"][0])
    validation_stack = build_stacker_features(fitted_models, training_views["validation"][0])
    for model_name, predictor, extra in build_ensemble_predictors(
        base_models=fitted_models,
        meta_stack=meta_stack,
        y_meta=y_views["meta_train"],
        validation_stack=validation_stack,
        y_validation=y_views["validation"],
        args=args,
    ):
        print(f"Evaluating ensemble: {model_name}", flush=True)
        result = evaluate_predictor(
            predictor,
            model_name=model_name,
            train_ms=extra.pop("train_ms", 0.0),
            datasets={
                "train": training_views["meta_train"],
                "validation": training_views["validation"],
                "test": training_views["test"],
            },
            y={
                "train": y_views["meta_train"],
                "validation": y_views["validation"],
                "test": y_views["test"],
            },
            test_rows=rows_by_split["test"],
            latency_rows=args.latency_rows,
            extra=extra,
        )
        ensemble_results.append(result)
        write_confusion_csv(output_dir / f"metrics/{model_name}__test_confusion.csv", result["test"]["confusion"])
        joblib.dump(
            {
                "model": predictor,
                "class_names": CLASS_NAMES,
                "feature_config": asdict(config),
                "feature_names": feature_names(config),
                "metrics": result,
            },
            output_dir / f"models/{model_name}.joblib",
        )

    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "Audit-v6 CPU baseline and ensemble comparison with separated base-train, meta-train, validation, and test roles.",
        "audit_dir": str(audit_dir.relative_to(ROOT)),
        "audit_manifest_sha256": sha256_file(audit_dir / "manifest.csv"),
        "output_dir": str(output_dir.relative_to(ROOT)),
        "seed": args.seed,
        "target": args.target,
        "class_names": list(CLASS_NAMES),
        "positive_class": POSITIVE_CLASS,
        "review_class": REVIEW_CLASS,
        "methodology": {
            "base_models_fit_on": "stratified 80% subset of audit-v6 train",
            "stackers_fit_on": "stratified 20% meta subset of audit-v6 train",
            "thresholds_tuned_on": "audit-v6 validation",
            "final_scored_on": "audit-v6 test",
            "test_usage": "never used for fitting, threshold selection, or model selection",
        },
        "split_counts": {
            "audit_v6_train_total": summarize_labels(rows_by_split["train"]),
            "base_train": summarize_encoded_labels(y_views["base_train"]),
            "meta_train": summarize_encoded_labels(y_views["meta_train"]),
            "validation": summarize_labels(rows_by_split["validation"]),
            "test": summarize_labels(rows_by_split["test"]),
        },
        "base_results": base_results,
        "ensemble_results": ensemble_results,
        "notes": [
            "False clear means actual class is not bold but predicted/cleared as bold.",
            "Base models fit on base_train; stackers fit on meta_train; reject thresholds tune on validation; final comparisons use test only.",
            "This is an offline experiment and does not promote a runtime model.",
        ],
    }
    write_json(output_dir / "metrics/summary.json", summary)
    write_markdown_report(output_dir / "metrics/report.md", summary)
    print(json.dumps(summary, indent=2), flush=True)


def resolve_path(path: Path) -> Path:
    """Resolve relative paths from the repo root."""

    return path if path.is_absolute() else ROOT / path


def configure_cpu(threads: int) -> None:
    """Pin CPU-heavy libraries to a predictable thread count."""

    value = str(max(1, threads))
    os.environ.setdefault("OMP_NUM_THREADS", value)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", value)
    os.environ.setdefault("MKL_NUM_THREADS", value)
    os.environ.setdefault("NUMEXPR_NUM_THREADS", value)


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for a local file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_base_meta_split(y_train: np.ndarray, *, meta_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Create a stratified base-train/meta-train split inside audit-v6 train."""

    indices = np.arange(len(y_train))
    base_idx, meta_idx = train_test_split(
        indices,
        test_size=meta_fraction,
        random_state=seed,
        stratify=y_train,
    )
    return np.sort(base_idx), np.sort(meta_idx)


def summarize_labels(rows: list[AuditRow]) -> dict[str, Any]:
    """Summarize split row counts and labels."""

    return {
        "rows": len(rows),
        "labels": dict(sorted(Counter(row.boldness_label for row in rows).items())),
    }


def summarize_encoded_labels(labels: np.ndarray) -> dict[str, Any]:
    """Summarize encoded labels using class names."""

    counts = Counter(CLASS_NAMES[int(label)] for label in labels)
    return {
        "rows": int(len(labels)),
        "labels": dict(sorted(counts.items())),
    }


def load_manifest(path: Path) -> dict[str, list[AuditRow]]:
    """Load audit-v6 manifest rows grouped by split."""

    rows_by_split: dict[str, list[AuditRow]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            label = raw["boldness_label"]
            if label not in CLASS_NAMES:
                raise ValueError(f"Unexpected boldness label: {label!r}")
            row = AuditRow(
                split=raw["split"],
                sample_id=raw["sample_id"],
                crop_path=raw["crop_path"],
                boldness_label=label,
                source_kind=raw["source_kind"],
                source_origin=raw["source_origin"],
                ttb_id=raw["ttb_id"],
                panel_warning_label=raw["panel_warning_label"],
                heading_text_label=raw["heading_text_label"],
                quality_label=raw["quality_label"],
            )
            rows_by_split[row.split].append(row)
    for split in ("train", "validation", "test"):
        if split not in rows_by_split:
            raise ValueError(f"Missing split in manifest: {split}")
    return dict(rows_by_split)


def load_or_extract_features(
    *,
    split: str,
    rows: list[AuditRow],
    audit_dir: Path,
    output_dir: Path,
    config: FeatureConfig,
    reuse: bool,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Load cached features or extract OpenCV features from image crops."""

    feature_path = output_dir / f"features/{split}_features.npy"
    meta_path = output_dir / f"features/{split}_meta.json"
    if reuse and feature_path.exists() and meta_path.exists():
        return np.load(feature_path), json.loads(meta_path.read_text(encoding="utf-8"))

    features: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    started = time.perf_counter()
    for idx, row in enumerate(rows, start=1):
        crop_file = audit_dir / row.crop_path
        image = cv2.imread(str(crop_file), cv2.IMREAD_GRAYSCALE)
        if image is None:
            image = np.full((config.height, config.width), 255, dtype=np.uint8)
        features.append(extract_feature_vector(image, config))
        meta.append(asdict(row))
        if idx % 1000 == 0:
            print(f"  extracted {idx:,} {split} features", flush=True)
    array = np.vstack(features).astype(np.float32)
    np.save(feature_path, array)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {split} features in {time.perf_counter() - started:.1f}s", flush=True)
    return array, meta


def build_model(name: str, args: argparse.Namespace) -> Any:
    """Build one baseline model."""

    if name == "svm":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    SGDClassifier(
                        loss="hinge",
                        alpha=0.0001,
                        class_weight="balanced",
                        max_iter=args.svm_max_iter,
                        tol=1e-4,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    if name == "xgboost":
        require(XGBClassifier, "xgboost")
        return XGBClassifier(
            objective="multi:softprob",
            num_class=len(CLASS_NAMES),
            n_estimators=args.tree_iterations,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="mlogloss",
            tree_method="hist",
            device="cpu",
            n_jobs=max(1, args.threads),
            random_state=args.seed,
        )
    if name == "lightgbm":
        require(LGBMClassifier, "lightgbm")
        return LGBMClassifier(
            objective="multiclass",
            num_class=len(CLASS_NAMES),
            n_estimators=args.tree_iterations,
            learning_rate=0.05,
            num_leaves=31,
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
                        solver="lbfgs",
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
                        hidden_layer_sizes=(128,),
                        activation="relu",
                        alpha=0.0005,
                        batch_size=512,
                        early_stopping=True,
                        n_iter_no_change=10,
                        learning_rate_init=0.001,
                        max_iter=args.mlp_max_iter,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    if name == "catboost":
        require(CatBoostClassifier, "catboost")
        return CatBoostClassifier(
            iterations=args.tree_iterations,
            depth=5,
            learning_rate=0.05,
            loss_function="MultiClass",
            random_seed=args.seed,
            thread_count=max(1, args.threads),
            verbose=False,
            allow_writing_files=False,
        )
    raise SystemExit(f"Unknown model: {name}")


def require(factory: Any, package_name: str) -> None:
    """Fail with a useful message when an optional package is missing."""

    if factory is None:
        raise SystemExit(f"{package_name} is not installed in this Python environment.")


def build_ensemble_predictors(
    *,
    base_models: dict[str, Any],
    meta_stack: np.ndarray,
    y_meta: np.ndarray,
    validation_stack: np.ndarray,
    y_validation: np.ndarray,
    args: argparse.Namespace,
) -> list[tuple[str, Any, dict[str, Any]]]:
    """Train stackers on meta data and tune reject wrappers on validation data."""

    positive_idx = CLASS_NAMES.index(POSITIVE_CLASS)
    review_idx = CLASS_NAMES.index(REVIEW_CLASS)
    predictors: list[tuple[str, Any, dict[str, Any]]] = [
        (
            "strict_veto_ensemble",
            StrictVetoEnsemble(base_models, review_class=review_idx, positive_class=positive_idx),
            {"train_ms": 0.0, "base_models": list(base_models)},
        )
    ]

    logistic = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    solver="lbfgs",
                    C=1.0,
                    class_weight="balanced",
                    max_iter=500,
                    random_state=args.seed,
                ),
            ),
        ]
    )
    started = time.perf_counter()
    logistic.fit(meta_stack, y_meta)
    predictors.append(
        (
            "calibrated_logistic_regression_stacker",
            StackerPipeline(base_models, logistic),
            {
                "train_ms": (time.perf_counter() - started) * 1000,
                "stacker_input": list(base_models),
                "stacker_training_split": "meta_train",
            },
        )
    )

    for name, stacker in [
        ("lightgbm_reject_threshold", build_lightgbm_stacker(args)),
        ("xgboost_reject_threshold", build_xgboost_stacker(args)),
        ("catboost_stacker", build_catboost_stacker(args)),
    ]:
        started = time.perf_counter()
        stacker.fit(meta_stack, y_meta)
        train_ms = (time.perf_counter() - started) * 1000
        pipeline = StackerPipeline(base_models, stacker)
        extra: dict[str, Any] = {
            "train_ms": train_ms,
            "stacker_input": list(base_models),
            "stacker_training_split": "meta_train",
        }
        predictor: Any = pipeline
        if name in {"lightgbm_reject_threshold", "xgboost_reject_threshold"}:
            threshold, tuning = tune_positive_reject_threshold(
                stacker,
                validation_stack,
                y_validation,
                target_false_clear=args.target_false_clear,
            )
            predictor = PositiveRejectWrapper(
                pipeline,
                threshold=threshold,
                positive_class=positive_idx,
                review_class=review_idx,
            )
            extra.update({"threshold": threshold, "threshold_tuning": tuning, "threshold_tuning_split": "validation"})
        predictors.append((name, predictor, extra))
    return predictors


def build_lightgbm_stacker(args: argparse.Namespace) -> Any:
    """Build a LightGBM stacker."""

    require(LGBMClassifier, "lightgbm")
    return LGBMClassifier(
        objective="multiclass",
        num_class=len(CLASS_NAMES),
        n_estimators=args.stacker_iterations,
        learning_rate=0.05,
        num_leaves=15,
        subsample=0.9,
        colsample_bytree=0.9,
        class_weight="balanced",
        n_jobs=max(1, args.threads),
        random_state=args.seed,
        verbosity=-1,
    )


def build_xgboost_stacker(args: argparse.Namespace) -> Any:
    """Build an XGBoost stacker."""

    require(XGBClassifier, "xgboost")
    return XGBClassifier(
        objective="multi:softprob",
        num_class=len(CLASS_NAMES),
        n_estimators=args.stacker_iterations,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="mlogloss",
        tree_method="hist",
        device="cpu",
        n_jobs=max(1, args.threads),
        random_state=args.seed,
    )


def build_catboost_stacker(args: argparse.Namespace) -> Any:
    """Build a CatBoost stacker."""

    require(CatBoostClassifier, "catboost")
    return CatBoostClassifier(
        iterations=args.stacker_iterations,
        depth=4,
        learning_rate=0.05,
        loss_function="MultiClass",
        random_seed=args.seed,
        thread_count=max(1, args.threads),
        verbose=False,
        allow_writing_files=False,
    )


def tune_positive_reject_threshold(
    model: Any,
    validation_stack: np.ndarray,
    y_validation: np.ndarray,
    *,
    target_false_clear: float,
) -> tuple[float, dict[str, Any]]:
    """Tune positive-clear threshold on validation predictions."""

    probabilities = np.asarray(model.predict_proba(validation_stack), dtype=np.float64)
    candidates: list[dict[str, Any]] = []
    positive_idx = CLASS_NAMES.index(POSITIVE_CLASS)
    review_idx = CLASS_NAMES.index(REVIEW_CLASS)
    for threshold in np.linspace(1 / len(CLASS_NAMES), 0.999, 100):
        raw = probabilities.argmax(axis=1).astype(np.int64)
        raw[(raw == positive_idx) & (probabilities[:, positive_idx] < threshold)] = review_idx
        metric = compute_metrics(y_validation, raw)
        candidates.append({"threshold": float(threshold), **metric})
    feasible = [item for item in candidates if item["false_clear_rate"] <= target_false_clear]
    if feasible:
        best = max(feasible, key=lambda item: (item["macro_f1"], item["accuracy"]))
    else:
        best = min(candidates, key=lambda item: (item["false_clear_rate"], -item["macro_f1"]))
    return float(best["threshold"]), {
        "target_false_clear": target_false_clear,
        "feasible_thresholds": len(feasible),
        "selected": {key: value for key, value in best.items() if key != "confusion"},
    }


def build_stacker_features(base_models: dict[str, Any], features: np.ndarray) -> np.ndarray:
    """Convert base-model outputs into stacker features."""

    class_count = len(CLASS_NAMES)
    vote_counts = np.zeros((len(features), class_count), dtype=np.float32)
    blocks: list[np.ndarray] = []
    for model in base_models.values():
        probabilities = probability_like_scores(model, features, class_count)
        predictions = probabilities.argmax(axis=1)
        one_hot = np.eye(class_count, dtype=np.float32)[predictions]
        vote_counts += one_hot
        blocks.extend([probabilities.astype(np.float32), one_hot])
    blocks.append(vote_counts / max(len(base_models), 1))
    blocks.append((vote_counts.max(axis=1, keepdims=True) / max(len(base_models), 1)).astype(np.float32))
    return np.hstack(blocks).astype(np.float32)


def probability_like_scores(model: Any, features: np.ndarray, class_count: int) -> np.ndarray:
    """Return probability-like class scores for a fitted model."""

    if hasattr(model, "predict_proba"):
        probabilities = np.asarray(model.predict_proba(features), dtype=np.float64)
        if probabilities.shape[1] == class_count:
            return probabilities
    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(features), dtype=np.float64)
        if scores.ndim == 1:
            scores = np.vstack([-scores, scores]).T
        scores -= scores.max(axis=1, keepdims=True)
        exp = np.exp(scores)
        return exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-12)
    predictions = predict_labels(model, features)
    return np.eye(class_count, dtype=np.float64)[predictions]


def evaluate_predictor(
    predictor: Any,
    *,
    model_name: str,
    train_ms: float,
    datasets: dict[str, tuple[np.ndarray, list[dict[str, Any]]]],
    y: dict[str, np.ndarray],
    test_rows: list[AuditRow],
    latency_rows: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one predictor on train/validation/test."""

    predictions = {
        split: predict_labels(predictor, datasets[split][0])
        for split in ("train", "validation", "test")
    }
    result: dict[str, Any] = {
        "task": "boldness_label",
        "model": model_name,
        "class_names": list(CLASS_NAMES),
        "train_ms": train_ms,
        "train": compute_metrics(y["train"], predictions["train"]),
        "validation": compute_metrics(y["validation"], predictions["validation"]),
        "test": compute_metrics(y["test"], predictions["test"]),
        "test_breakdowns": compute_breakdowns(y["test"], predictions["test"], test_rows),
        "latency": measure_latency(predictor, datasets["test"][0], latency_rows),
    }
    if extra:
        result.update(extra)
    return result


def predict_labels(model: Any, features: np.ndarray) -> np.ndarray:
    """Return int64 labels from estimator predictions."""

    return np.asarray(model.predict(features), dtype=np.int64).reshape(-1)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Compute multiclass metrics plus false-clear rate."""

    labels = list(range(len(CLASS_NAMES)))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )
    macro = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    weighted = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
    positive_idx = CLASS_NAMES.index(POSITIVE_CLASS)
    non_positive = y_true != positive_idx
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
        "false_clear_rate": float(((y_pred == positive_idx) & non_positive).sum() / max(non_positive.sum(), 1)),
        "per_class": {
            class_name: {
                "precision": float(precision[idx]),
                "recall": float(recall[idx]),
                "f1": float(f1[idx]),
                "support": int(support[idx]),
            }
            for idx, class_name in enumerate(CLASS_NAMES)
        },
        "confusion": confusion_matrix(y_true, y_pred, labels=labels).astype(int).tolist(),
        "examples": int(len(y_true)),
    }


def compute_breakdowns(y_true: np.ndarray, y_pred: np.ndarray, rows: list[AuditRow]) -> dict[str, dict[str, Any]]:
    """Compute test metrics by source provenance."""

    result: dict[str, dict[str, Any]] = {}
    for field in ("source_kind", "source_origin", "quality_label"):
        grouped: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"true": [], "pred": []})
        for idx, row in enumerate(rows):
            grouped[getattr(row, field)]["true"].append(int(y_true[idx]))
            grouped[getattr(row, field)]["pred"].append(int(y_pred[idx]))
        result[field] = {
            key: compute_metrics(np.asarray(value["true"], dtype=np.int64), np.asarray(value["pred"], dtype=np.int64))
            for key, value in sorted(grouped.items())
        }
    return result


def measure_latency(model: Any, features: np.ndarray, rows: int) -> dict[str, float | int]:
    """Measure batch and single-row prediction latency."""

    sample = features[: min(rows, len(features))]
    started = time.perf_counter()
    _ = predict_labels(model, sample)
    batch_ms = (time.perf_counter() - started) * 1000
    row_times = []
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


def write_confusion_csv(path: Path, matrix: list[list[int]]) -> None:
    """Write a confusion matrix CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual", *CLASS_NAMES])
        for class_name, row in zip(CLASS_NAMES, matrix):
            writer.writerow([class_name, *row])


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a Markdown report with side-by-side metrics."""

    lines = [
        "# Audit-v6 Typography Baseline Comparison",
        "",
        "CPU-only comparison on the same audit-v6 split used by the CNN challenger.",
        "",
        "Positive class: `bold`. False clear means actual class is not `bold` but the model predicts `bold`.",
        "",
        "## Data",
        "",
        "| Split role | Crops | Bold | Not bold | Unreadable review | Not applicable |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("base_train", "meta_train", "validation", "test"):
        labels = summary["split_counts"][split]["labels"]
        lines.append(
            f"| {split} | {summary['split_counts'][split]['rows']:,} | "
            f"{labels.get('bold', 0):,} | {labels.get('not_bold', 0):,} | "
            f"{labels.get('unreadable_review', 0):,} | {labels.get('not_applicable', 0):,} |"
        )
    lines.extend(
        [
            "",
            "Protocol: base models fit on `base_train`; stackers fit on `meta_train` using base-model outputs; reject thresholds tune on `validation`; final metrics are scored once on `test`.",
        ]
    )
    lines.extend(["", "## Base Model Metrics", ""])
    lines.extend(metric_table_header())
    for result in summary["base_results"]:
        lines.append(format_metric_row(result))
    lines.extend(["", "## Ensemble Metrics", ""])
    lines.extend(metric_table_header())
    for result in summary["ensemble_results"]:
        lines.append(format_metric_row(result))
    lines.extend(["", "## Test Confusion Matrices", ""])
    for result in [*summary["base_results"], *summary["ensemble_results"]]:
        lines.append(f"### {pretty_model(result['model'])}")
        lines.append("")
        lines.append("| Actual \\ Predicted | " + " | ".join(CLASS_NAMES) + " |")
        lines.append("|---|" + "|".join(["---:" for _ in CLASS_NAMES]) + "|")
        for class_name, row in zip(CLASS_NAMES, result["test"]["confusion"]):
            lines.append("| " + class_name + " | " + " | ".join(str(value) for value in row) + " |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def metric_table_header() -> list[str]:
    """Return shared Markdown table header."""

    return [
        "| Model | Train Acc | Train F1 | Train False-Clear | Val Acc | Val F1 | Val False-Clear | Test Acc | Test F1 | Test False-Clear | Train s | Single p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]


def format_metric_row(result: dict[str, Any]) -> str:
    """Format one report row."""

    return (
        f"| {pretty_model(result['model'])} | "
        f"{result['train']['accuracy']:.4f} | {result['train']['macro_f1']:.4f} | {result['train']['false_clear_rate']:.4f} | "
        f"{result['validation']['accuracy']:.4f} | {result['validation']['macro_f1']:.4f} | {result['validation']['false_clear_rate']:.4f} | "
        f"{result['test']['accuracy']:.4f} | {result['test']['macro_f1']:.4f} | {result['test']['false_clear_rate']:.4f} | "
        f"{result['train_ms'] / 1000:.1f} | {result['latency']['single_row_p95_ms']:.4f} |"
    )


def pretty_model(model: str) -> str:
    """Return display name for a model."""

    return {
        "svm": "SVM",
        "xgboost": "XGBoost",
        "lightgbm": "LightGBM",
        "logistic_regression": "Logistic Regression",
        "mlp": "MLP",
        "catboost": "CatBoost",
        "strict_veto_ensemble": "Strict-veto ensemble",
        "calibrated_logistic_regression_stacker": "Calibrated logistic stacker",
        "lightgbm_reject_threshold": "LightGBM reject-threshold stacker",
        "xgboost_reject_threshold": "XGBoost reject-threshold stacker",
        "catboost_stacker": "CatBoost stacker",
    }.get(model, model)


def write_json(path: Path, payload: object) -> None:
    """Write stable pretty JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
