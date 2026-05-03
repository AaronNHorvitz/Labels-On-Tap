"""Large typography ensemble comparison with geometry stress.

This experiment scales the corrected ``audit-v5`` typography data to a larger
80/20 train/test design, applies extra rotation-and-bend stress to half of the
crops, retrains the strongest base learners, and compares multiple ensemble
policies:

* strict-veto voting ensemble,
* calibrated logistic-regression stacker,
* LightGBM stacker with a validation-tuned reject threshold,
* XGBoost stacker with a validation-tuned reject threshold,
* CatBoost stacker.

All outputs are written under gitignored ``data/work/typography-preflight/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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
from experiments.typography_preflight.compare_extended_models import StrictVetoEnsemble
from experiments.typography_preflight.compare_models import (
    DEFAULT_FONT_ROOT,
    HEADER_CLASSES,
    ROOT,
    VISUAL_CLASSES,
    configure_cpu,
    encode_labels,
    predict_labels,
    write_json,
)
from experiments.typography_preflight.features import FeatureConfig, extract_feature_vector, feature_names, limit_cv2_threads

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


DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/model-comparison-large-geometry-v1"
BASE_MODELS = ("svm", "lightgbm", "logistic_regression", "mlp")
STACKER_MODELS = (
    "strict_veto_ensemble",
    "calibrated_logistic_regression_stacker",
    "lightgbm_reject_threshold",
    "xgboost_reject_threshold",
    "catboost_stacker",
)


@dataclass(frozen=True)
class LargeSampleMeta:
    """Metadata for one large synthetic typography crop."""

    split: str
    sample_id: str
    font_weight_label: str
    header_text_label: str
    quality_label: str
    geometry_label: str
    visual_font_decision_label: str
    header_decision_label: str
    source_text: str
    font_path: str
    font_family: str
    font_style: str
    font_size: int
    saved_crop: str


class PositiveRejectWrapper:
    """Route weak positive predictions to review based on a tuned threshold."""

    def __init__(
        self,
        model: Any,
        *,
        threshold: float,
        positive_class: int = 0,
        review_class: int = 2,
    ) -> None:
        self.model = model
        self.threshold = threshold
        self.positive_class = positive_class
        self.review_class = review_class

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict labels, rejecting low-confidence positive predictions."""

        probabilities = np.asarray(self.model.predict_proba(features), dtype=np.float64)
        raw = probabilities.argmax(axis=1).astype(np.int64)
        weak_positive = (raw == self.positive_class) & (probabilities[:, self.positive_class] < self.threshold)
        raw[weak_positive] = self.review_class
        return raw


class StackerPipeline:
    """Run base learners and a learned stacker as one end-to-end predictor."""

    def __init__(self, base_models: dict[str, Any], stacker: Any) -> None:
        self.base_models = base_models
        self.stacker = stacker

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict labels from raw feature vectors via base-model stacker features."""

        return predict_labels(self.stacker, build_stacker_features(self.base_models, features))

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Return stacker probabilities from raw feature vectors."""

        stacker_features = build_stacker_features(self.base_models, features)
        return np.asarray(self.stacker.predict_proba(stacker_features), dtype=np.float64)


def main() -> None:
    """Run the large base-model and ensemble comparison."""

    args = parse_args()
    configure_cpu(args.threads)
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    warnings.filterwarnings("ignore", message="The max_iter was reached.*")
    limit_cv2_threads()
    np.random.seed(args.seed)

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["features", "manifests", "metrics", "models", "sample_crops"]:
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    config = FeatureConfig()
    fonts = discover_fonts(args.font_root)
    font_splits = split_font_pools(fonts, seed=args.seed, train_fraction=args.train_fraction)
    write_json(output_dir / "manifests/font_splits.json", serialize_font_splits(font_splits))

    train_count = int(round(args.total_samples * args.train_fraction))
    test_count = args.total_samples - train_count
    train_features, train_meta = load_or_generate_split(
        "train",
        train_count,
        font_splits["train"],
        output_dir,
        config,
        args,
    )
    test_features, test_meta = load_or_generate_split(
        "test",
        test_count,
        font_splits["test"],
        output_dir,
        config,
        args,
    )
    write_json(output_dir / "manifests/feature_names.json", feature_names(config))

    base_indices, calibration_indices = make_internal_split(len(train_features), args.calibration_fraction, seed=args.seed)
    datasets = {
        "base_train": (train_features[base_indices], [train_meta[idx] for idx in base_indices]),
        "calibration": (train_features[calibration_indices], [train_meta[idx] for idx in calibration_indices]),
        "train": (train_features, train_meta),
        "test": (test_features, test_meta),
    }
    summary: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seed": args.seed,
        "split": {
            "train_fraction": args.train_fraction,
            "calibration_fraction_of_train": args.calibration_fraction,
            "base_train": int(len(base_indices)),
            "calibration": int(len(calibration_indices)),
            "train": int(train_count),
            "test": int(test_count),
            "geometry_policy": "half normal, half rotated_bent within every split",
        },
        "label_policy": {
            "visual_font_decision_label": list(VISUAL_CLASSES),
            "header_decision_label": list(HEADER_CLASSES),
            "notes": [
                "Generated bold fonts are bold.",
                "Generated non-bold fonts are not bold.",
                "needs_review_unclear is reserved for degraded/unreadable crops.",
                "Half of generated crops receive additional rotation and sinusoidal bending.",
                "Stackers are trained/tuned on a calibration slice from the training split, never on test.",
            ],
        },
        "base_results": [],
        "ensemble_results": [],
    }

    tasks = {
        "visual_font_decision_label": VISUAL_CLASSES,
        "header_decision_label": HEADER_CLASSES,
    }
    print(
        f"Generated/loaded large split: train={len(train_features)}, test={len(test_features)}, "
        f"base_train={len(base_indices)}, calibration={len(calibration_indices)}",
        flush=True,
    )
    for task_name, class_names in tasks.items():
        print(f"Task: {task_name}", flush=True)
        y_base = labels_for(datasets["base_train"][1], task_name, class_names)
        y_cal = labels_for(datasets["calibration"][1], task_name, class_names)
        y_train = labels_for(train_meta, task_name, class_names)
        y_test = labels_for(test_meta, task_name, class_names)

        base_models: dict[str, Any] = {}
        for model_name in BASE_MODELS:
            print(f"  base model: {model_name}", flush=True)
            model = build_base_model(model_name, args, len(class_names))
            started = time.perf_counter()
            model.fit(datasets["base_train"][0], y_base)
            train_ms = (time.perf_counter() - started) * 1000
            base_models[model_name] = model
            result = evaluate_predictor(
                model,
                task_name=task_name,
                model_name=model_name,
                class_names=class_names,
                train_features=train_features,
                test_features=test_features,
                y_train=y_train,
                y_test=y_test,
                train_ms=train_ms,
                latency_rows=args.latency_rows,
            )
            summary["base_results"].append(result)
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

        cal_stack = build_stacker_features(base_models, datasets["calibration"][0])

        ensemble_predictors = build_ensemble_predictors(
            base_models=base_models,
            cal_stack=cal_stack,
            y_cal=y_cal,
            args=args,
            class_names=class_names,
            task_name=task_name,
        )
        for ensemble_name, predictor, details in ensemble_predictors:
            print(f"  ensemble: {ensemble_name}", flush=True)
            result = evaluate_predictor(
                predictor,
                task_name=task_name,
                model_name=ensemble_name,
                class_names=class_names,
                train_features=train_features,
                test_features=test_features,
                y_train=y_train,
                y_test=y_test,
                train_ms=details.pop("train_ms", 0.0),
                latency_rows=args.latency_rows,
                extra=details,
            )
            summary["ensemble_results"].append(result)
            joblib.dump(
                {
                    "model": predictor,
                    "task": task_name,
                    "class_names": class_names,
                    "metrics": result,
                    "base_models": list(base_models),
                },
                output_dir / f"models/{task_name}__{ensemble_name}.joblib",
            )

    write_json(output_dir / "metrics/summary.json", summary)
    write_markdown_report(output_dir / "metrics/report.md", summary)
    print(json.dumps(summary, indent=2))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--font-root", type=Path, default=DEFAULT_FONT_ROOT)
    parser.add_argument("--total-samples", type=int, default=50_000)
    parser.add_argument("--train-fraction", type=float, default=0.80)
    parser.add_argument("--calibration-fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--sample-crop-limit", type=int, default=240)
    parser.add_argument("--tree-iterations", type=int, default=120)
    parser.add_argument("--stacker-iterations", type=int, default=120)
    parser.add_argument("--svm-max-iter", type=int, default=2_000)
    parser.add_argument("--logistic-max-iter", type=int, default=350)
    parser.add_argument("--mlp-max-iter", type=int, default=90)
    parser.add_argument("--target-false-clear", type=float, default=0.005)
    parser.add_argument("--reuse-features", action="store_true")
    return parser.parse_args()


def split_font_pools(
    fonts: dict[str, list[FontRecord]], *, seed: int, train_fraction: float
) -> dict[str, dict[str, list[FontRecord]]]:
    """Split discovered fonts into train and test pools by font family."""

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
        for split, split_families in {"train": families[:train_cut], "test": families[train_cut:] or families[-1:]}.items():
            result[split][label] = [record for family in split_families for record in by_family[family]]
            if not result[split][label]:
                result[split][label] = list(fonts[label])
    return result


def serialize_font_splits(splits: dict[str, dict[str, list[FontRecord]]]) -> dict[str, Any]:
    """Serialize split font pools for provenance."""

    return {
        split: {
            label: {
                "font_count": len(records),
                "families": sorted({record.family for record in records}),
                "fonts": [asdict(record) for record in records],
            }
            for label, records in pools.items()
        }
        for split, pools in splits.items()
    }


def load_or_generate_split(
    split: str,
    count: int,
    font_pools: dict[str, list[FontRecord]],
    output_dir: Path,
    config: FeatureConfig,
    args: argparse.Namespace,
) -> tuple[np.ndarray, list[LargeSampleMeta]]:
    """Load cached features or generate a split with balanced geometry stress."""

    feature_path = output_dir / f"features/{split}.npz"
    manifest_path = output_dir / f"manifests/{split}_manifest.csv"
    if args.reuse_features and feature_path.exists() and manifest_path.exists():
        loaded = np.load(feature_path, allow_pickle=False)
        return loaded["features"].astype(np.float32), read_manifest(manifest_path)

    features: list[np.ndarray] = []
    metadata: list[LargeSampleMeta] = []
    split_rng = random.Random(f"{args.seed}:{split}:large")
    combos = [
        (fw, ht, quality, geometry)
        for fw in FONT_WEIGHT_LABELS
        for ht in HEADER_TEXT_LABELS
        for quality in QUALITY_LABELS
        for geometry in ("normal", "rotated_bent")
    ]
    sample_dir = output_dir / "sample_crops" / split
    sample_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(count):
        if idx % len(combos) == 0:
            split_rng.shuffle(combos)
        font_weight_label, header_text_label, quality_label, geometry_label = combos[idx % len(combos)]
        font = split_rng.choice(font_pools[font_weight_label])
        source_text = choose_source_text(header_text_label, quality_label, split_rng)
        font_size = split_rng.randint(24, 46)
        image = render_heading(source_text, font, font_size)
        image = apply_quality_recipe(image, quality_label, split_rng)
        if geometry_label == "rotated_bent":
            image = apply_geometry_stress(image, split_rng)
        gray = np.array(image, dtype=np.uint8)
        vector = extract_feature_vector(gray, config)
        sample_id = f"{split}_{idx:06d}"
        saved_crop = ""
        if idx < args.sample_crop_limit:
            crop_path = sample_dir / (
                f"{sample_id}__fw-{font_weight_label}__text-{header_text_label}"
                f"__quality-{quality_label}__geometry-{geometry_label}.png"
            )
            cv2.imwrite(str(crop_path), gray)
            saved_crop = str(crop_path.relative_to(output_dir))
        metadata.append(
            LargeSampleMeta(
                split=split,
                sample_id=sample_id,
                font_weight_label=font_weight_label,
                header_text_label=header_text_label,
                quality_label=quality_label,
                geometry_label=geometry_label,
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


def apply_geometry_stress(image: Image.Image, rng: random.Random) -> Image.Image:
    """Apply rotation plus sinusoidal bending for curved-label robustness."""

    angle = rng.uniform(-7.0, 7.0)
    rotated = image.rotate(angle, expand=True, fillcolor=255)
    gray = np.array(rotated, dtype=np.uint8)
    height, width = gray.shape[:2]
    amplitude = rng.uniform(2.0, 7.0)
    period = rng.uniform(max(width * 0.55, 1), max(width * 1.25, 2))
    phase = rng.uniform(0.0, math.tau)
    xs, ys = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    y_offsets = amplitude * np.sin((xs / period) * math.tau + phase)
    map_x = xs.astype(np.float32)
    map_y = (ys + y_offsets).astype(np.float32)
    warped = cv2.remap(gray, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return Image.fromarray(warped)


def visual_font_decision(font_weight_label: str, quality_label: str) -> str:
    """Return the strict model target for visual font-weight decisions."""

    if quality_label == "degraded":
        return "needs_review_unclear"
    if font_weight_label == "bold":
        return "clearly_bold"
    return "clearly_not_bold"


def header_decision(header_text_label: str, quality_label: str) -> str:
    """Return the strict model target for header text decisions."""

    if quality_label == "degraded":
        return "needs_review_unclear"
    return header_text_label


def write_manifest(path: Path, metadata: list[LargeSampleMeta]) -> None:
    """Write split metadata as CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(metadata[0]).keys()))
        writer.writeheader()
        for row in metadata:
            writer.writerow(asdict(row))


def read_manifest(path: Path) -> list[LargeSampleMeta]:
    """Read split metadata from CSV."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [LargeSampleMeta(**row) for row in csv.DictReader(handle)]


def make_internal_split(count: int, calibration_fraction: float, *, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Create base-train and calibration indices inside the training split."""

    rng = np.random.default_rng(seed)
    indices = np.arange(count)
    rng.shuffle(indices)
    calibration_count = int(round(count * calibration_fraction))
    calibration = np.sort(indices[:calibration_count])
    base = np.sort(indices[calibration_count:])
    return base, calibration


def labels_for(metadata: list[LargeSampleMeta], task_name: str, class_names: tuple[str, ...]) -> np.ndarray:
    """Encode labels for one task from split metadata."""

    return encode_labels([getattr(row, task_name) for row in metadata], class_names)


def build_base_model(name: str, args: argparse.Namespace, class_count: int) -> Any:
    """Build one base learner for typography features."""

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
    if name == "lightgbm":
        require(LGBMClassifier, "lightgbm")
        return LGBMClassifier(
            objective="multiclass",
            num_class=class_count,
            n_estimators=args.tree_iterations,
            learning_rate=0.06,
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
                        batch_size=512,
                        early_stopping=True,
                        n_iter_no_change=8,
                        learning_rate_init=0.001,
                        max_iter=args.mlp_max_iter,
                        random_state=args.seed,
                    ),
                ),
            ]
        )
    raise SystemExit(f"Unknown base model: {name}")


def require(factory: Any, package_name: str) -> None:
    """Fail with a useful message when an optional dependency is missing."""

    if factory is None:
        raise SystemExit(f"{package_name} is not installed in this Python environment.")


def build_stacker_features(base_models: dict[str, Any], features: np.ndarray) -> np.ndarray:
    """Convert base-model predictions into stacker features."""

    blocks: list[np.ndarray] = []
    vote_counts = np.zeros((len(features), 3), dtype=np.float32)
    for model in base_models.values():
        probabilities = probability_like_scores(model, features)
        predictions = probabilities.argmax(axis=1)
        one_hot = np.eye(3, dtype=np.float32)[predictions]
        vote_counts += one_hot
        blocks.extend([probabilities.astype(np.float32), one_hot])
    blocks.append(vote_counts / max(len(base_models), 1))
    blocks.append((vote_counts.max(axis=1, keepdims=True) / max(len(base_models), 1)).astype(np.float32))
    return np.hstack(blocks).astype(np.float32)


def probability_like_scores(model: Any, features: np.ndarray) -> np.ndarray:
    """Return calibrated-ish class scores for base models."""

    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(features), dtype=np.float64)
    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(features), dtype=np.float64)
        if scores.ndim == 1:
            scores = np.vstack([-scores, scores]).T
        scores -= scores.max(axis=1, keepdims=True)
        exp = np.exp(scores)
        return exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-12)
    predictions = predict_labels(model, features)
    return np.eye(3, dtype=np.float64)[predictions]


def build_ensemble_predictors(
    *,
    base_models: dict[str, Any],
    cal_stack: np.ndarray,
    y_cal: np.ndarray,
    args: argparse.Namespace,
    class_names: tuple[str, ...],
    task_name: str,
) -> list[tuple[str, Any, dict[str, Any]]]:
    """Train stackers and tune reject-threshold ensembles on calibration data."""

    predictors: list[tuple[str, Any, dict[str, Any]]] = []
    predictors.append(
        (
            "strict_veto_ensemble",
            StrictVetoEnsemble(list(base_models.values())),
            {"train_ms": 0.0, "base_models": list(base_models)},
        )
    )

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
    logistic.fit(cal_stack, y_cal)
    predictors.append(
        (
            "calibrated_logistic_regression_stacker",
            StackerPipeline(base_models, logistic),
            {
                "train_ms": (time.perf_counter() - started) * 1000,
                "stacker_input": list(base_models),
                "latency_scope": "end_to_end_base_models_plus_stacker",
            },
        )
    )

    for name, model in [
        ("lightgbm_reject_threshold", build_lightgbm_stacker(args)),
        ("xgboost_reject_threshold", build_xgboost_stacker(args, len(class_names))),
    ]:
        started = time.perf_counter()
        model.fit(cal_stack, y_cal)
        train_ms = (time.perf_counter() - started) * 1000
        threshold, tuning = tune_positive_reject_threshold(
            model,
            cal_stack,
            y_cal,
            class_names,
            target_false_clear=args.target_false_clear,
        )
        predictors.append(
            (
                name,
                PositiveRejectWrapper(StackerPipeline(base_models, model), threshold=threshold),
                {
                    "train_ms": train_ms,
                    "threshold": threshold,
                    "threshold_tuning": tuning,
                    "stacker_input": list(base_models),
                    "latency_scope": "end_to_end_base_models_plus_stacker",
                },
            )
        )

    catboost = build_catboost_stacker(args)
    started = time.perf_counter()
    catboost.fit(cal_stack, y_cal)
    predictors.append(
        (
            "catboost_stacker",
            StackerPipeline(base_models, catboost),
            {
                "train_ms": (time.perf_counter() - started) * 1000,
                "stacker_input": list(base_models),
                "latency_scope": "end_to_end_base_models_plus_stacker",
            },
        )
    )
    return predictors


def build_lightgbm_stacker(args: argparse.Namespace) -> Any:
    """Build a LightGBM stacker."""

    require(LGBMClassifier, "lightgbm")
    return LGBMClassifier(
        objective="multiclass",
        num_class=3,
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


def build_xgboost_stacker(args: argparse.Namespace, class_count: int) -> Any:
    """Build an XGBoost stacker."""

    require(XGBClassifier, "xgboost")
    return XGBClassifier(
        objective="multi:softprob",
        num_class=class_count,
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
    features: np.ndarray,
    y_true: np.ndarray,
    class_names: tuple[str, ...],
    *,
    target_false_clear: float,
) -> tuple[float, dict[str, Any]]:
    """Tune a positive-class reject threshold on calibration data."""

    probabilities = np.asarray(model.predict_proba(features), dtype=np.float64)
    candidates: list[dict[str, Any]] = []
    for threshold in np.linspace(1 / len(class_names), 0.999, 80):
        raw = probabilities.argmax(axis=1).astype(np.int64)
        raw[(raw == 0) & (probabilities[:, 0] < threshold)] = 2
        metric = compute_metrics(y_true, raw, class_names)
        candidates.append({"threshold": float(threshold), **metric})
    feasible = [item for item in candidates if item["false_clear_rate"] <= target_false_clear]
    if feasible:
        best = max(feasible, key=lambda item: (item["macro_f1"], item["accuracy"]))
    else:
        best = min(candidates, key=lambda item: (item["false_clear_rate"], -item["macro_f1"]))
    return float(best["threshold"]), {
        "target_false_clear": target_false_clear,
        "selected": {key: value for key, value in best.items() if key != "confusion"},
        "feasible_thresholds": len(feasible),
    }


def evaluate_predictor(
    predictor: Any,
    *,
    task_name: str,
    model_name: str,
    class_names: tuple[str, ...],
    train_features: np.ndarray,
    test_features: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    train_ms: float,
    latency_rows: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a model on train and test plus CPU prediction latency."""

    train_pred = predict_labels(predictor, train_features)
    test_pred = predict_labels(predictor, test_features)
    result: dict[str, Any] = {
        "task": task_name,
        "model": model_name,
        "class_names": list(class_names),
        "train_ms": train_ms,
        "train": compute_metrics(y_train, train_pred, class_names),
        "test": compute_metrics(y_test, test_pred, class_names),
        "latency": measure_latency(predictor, test_features, latency_rows),
    }
    if extra:
        result.update(extra)
    return result


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, class_names: tuple[str, ...]) -> dict[str, Any]:
    """Compute standard and false-clear metrics."""

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(range(len(class_names))),
        zero_division=0,
    )
    macro = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    weighted = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
    false_clear_mask = y_true != 0
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
        "false_clear_rate": float(((y_pred == 0) & false_clear_mask).sum() / max(false_clear_mask.sum(), 1)),
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


def measure_latency(predictor: Any, features: np.ndarray, rows: int) -> dict[str, float | int]:
    """Measure batch and single-row prediction latency."""

    sample = features[: min(rows, len(features))]
    started = time.perf_counter()
    _ = predict_labels(predictor, sample)
    batch_ms = (time.perf_counter() - started) * 1000
    row_times = []
    for row in sample[: min(200, len(sample))]:
        started = time.perf_counter()
        _ = predict_labels(predictor, row.reshape(1, -1))
        row_times.append((time.perf_counter() - started) * 1000)
    return {
        "rows": int(len(sample)),
        "batch_ms_per_crop": float(batch_ms / max(len(sample), 1)),
        "single_row_mean_ms": float(np.mean(row_times)) if row_times else 0.0,
        "single_row_p95_ms": float(np.percentile(row_times, 95)) if row_times else 0.0,
        "single_row_max_ms": float(np.max(row_times)) if row_times else 0.0,
    }


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a Markdown report with model and ensemble tables."""

    lines = [
        "# Large Geometry Typography Ensemble Comparison",
        "",
        "Synthetic CPU-only comparison using strict audit-v5 labels, a 5x larger 80/20 split, and rotation/bend stress on half of crops.",
        "",
        "## Data",
        "",
        "| Split | Crops |",
        "|---|---:|",
        f"| Base train | {summary['split']['base_train']:,} |",
        f"| Calibration | {summary['split']['calibration']:,} |",
        f"| Full train | {summary['split']['train']:,} |",
        f"| Test | {summary['split']['test']:,} |",
        "",
        "## Base Model Metrics",
        "",
        "| Task | Model | Train Acc | Train F1 | Train False-Clear | Test Acc | Test F1 | Test False-Clear | Train s | Single ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in summary["base_results"]:
        lines.append(format_metric_row(result))
    lines.extend(
        [
            "",
            "## Ensemble Metrics",
            "",
            "| Task | Model | Train Acc | Train F1 | Train False-Clear | Test Acc | Test F1 | Test False-Clear | Train s | Single ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in summary["ensemble_results"]:
        lines.append(format_metric_row(result))
    lines.extend(["", "## Test Confusion Matrices", ""])
    for result in [*summary["base_results"], *summary["ensemble_results"]]:
        lines.append(f"### {pretty_task(result['task'])} - {pretty_model(result['model'])}")
        lines.append("")
        class_names = result["class_names"]
        lines.append("| Actual \\ Predicted | " + " | ".join(class_names) + " |")
        lines.append("|---|" + "|".join(["---:" for _ in class_names]) + "|")
        for class_name, row in zip(class_names, result["test"]["confusion"]):
            lines.append("| " + class_name + " | " + " | ".join(str(value) for value in row) + " |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def format_metric_row(result: dict[str, Any]) -> str:
    """Format one Markdown metric row."""

    return (
        f"| {pretty_task(result['task'])} | {pretty_model(result['model'])} | "
        f"{result['train']['accuracy']:.4f} | {result['train']['macro_f1']:.4f} | "
        f"{result['train']['false_clear_rate']:.4f} | {result['test']['accuracy']:.4f} | "
        f"{result['test']['macro_f1']:.4f} | {result['test']['false_clear_rate']:.4f} | "
        f"{result['train_ms'] / 1000:.1f} | {result['latency']['single_row_mean_ms']:.4f} |"
    )


def pretty_task(task: str) -> str:
    """Return display label for a task."""

    return {
        "visual_font_decision_label": "Visual font decision",
        "header_decision_label": "Header text decision",
    }.get(task, task)


def pretty_model(model: str) -> str:
    """Return display label for a model."""

    return {
        "svm": "SVM",
        "lightgbm": "LightGBM",
        "logistic_regression": "Logistic Regression",
        "mlp": "MLP",
        "strict_veto_ensemble": "Strict-veto ensemble",
        "calibrated_logistic_regression_stacker": "Calibrated logistic stacker",
        "lightgbm_reject_threshold": "LightGBM reject-threshold stacker",
        "xgboost_reject_threshold": "XGBoost reject-threshold stacker",
        "catboost_stacker": "CatBoost stacker",
    }.get(model, model)


if __name__ == "__main__":
    main()
