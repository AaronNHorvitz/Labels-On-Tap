"""Train audit-v6 base models and ensembles with CNN included.

This is the statistically defensible comparison the typography preflight needs:

* every model uses the same ``audit-v6`` image set,
* base learners are trained on the same training rows,
* stackers train on out-of-fold training predictions,
* the CNN is included as one of the base learners,
* final metrics are reported on the untouched ``audit-v6`` test split.

The target is ``boldness_label``:

``bold`` / ``not_bold`` / ``unreadable_review`` / ``not_applicable``.

The positive class is ``bold``. False clear means actual class is not ``bold``
but the model predicts or clears ``bold``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import warnings
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from torch import nn
from torch.utils.data import DataLoader

from experiments.typography_preflight.compare_audit_v6_baselines import (
    BASE_MODELS,
    CLASS_NAMES,
    DEFAULT_AUDIT_DIR,
    POSITIVE_CLASS,
    REVIEW_CLASS,
    build_catboost_stacker,
    build_lightgbm_stacker,
    build_model as build_tabular_model,
    build_stacker_features,
    build_xgboost_stacker,
    compute_breakdowns,
    configure_cpu,
    load_manifest as load_audit_manifest,
    load_or_extract_features,
    measure_latency,
    predict_labels,
    probability_like_scores,
    resolve_path,
    tune_positive_reject_threshold,
    write_confusion_csv,
    write_json,
)
from experiments.typography_preflight.features import FeatureConfig, feature_names, limit_cv2_threads
from experiments.typography_preflight.train_audit_v6_cnn import (
    AuditV6Dataset,
    build_model as build_cnn_model,
    build_transforms,
    class_weights,
    configure_reproducibility,
    run_train_epoch,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/model-comparison-audit-v6-cnn-ensemble-v1"
DEFAULT_CNN_CHECKPOINT = ROOT / "data/work/typography-preflight/cnn-audit-v6-mobilenet-v1/models/mobilenet_v3_small_best.pt"
CNN_MODEL_NAME = "mobilenet_v3_small"
ALL_BASE_NAMES = (*BASE_MODELS, CNN_MODEL_NAME)


class ProbabilityStacker:
    """Run base probability producers and a fitted stacker."""

    def __init__(self, stacker: Any) -> None:
        self.stacker = stacker

    def predict(self, stack_features: np.ndarray) -> np.ndarray:
        return np.asarray(self.stacker.predict(stack_features), dtype=np.int64).reshape(-1)

    def predict_proba(self, stack_features: np.ndarray) -> np.ndarray:
        return np.asarray(self.stacker.predict_proba(stack_features), dtype=np.float64)


class PositiveRejectWrapper:
    """Route weak positive predictions to review based on validation threshold."""

    def __init__(self, model: Any, *, threshold: float) -> None:
        self.model = model
        self.threshold = threshold
        self.positive_idx = CLASS_NAMES.index(POSITIVE_CLASS)
        self.review_idx = CLASS_NAMES.index(REVIEW_CLASS)

    def predict(self, features: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(self.model.predict_proba(features), dtype=np.float64)
        raw = probabilities.argmax(axis=1).astype(np.int64)
        raw[(raw == self.positive_idx) & (probabilities[:, self.positive_idx] < self.threshold)] = self.review_idx
        return raw

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict_proba(features), dtype=np.float64)


class StrictVetoProbabilityEnsemble:
    """Only clear bold when every base learner predicts bold."""

    def __init__(self, *, positive_class: int, review_class: int, class_count: int, base_count: int) -> None:
        self.positive_class = positive_class
        self.review_class = review_class
        self.class_count = class_count
        self.base_count = base_count

    def predict(self, stack_features: np.ndarray) -> np.ndarray:
        probabilities = probabilities_from_stack(stack_features, self.base_count, self.class_count)
        predictions = probabilities.argmax(axis=2)
        output = np.full(predictions.shape[0], self.review_class, dtype=np.int64)
        unanimous = np.all(predictions == predictions[:, :1], axis=1)
        unanimous_positive = unanimous & (predictions[:, 0] == self.positive_class)
        unanimous_non_positive = unanimous & (predictions[:, 0] != self.positive_class)
        output[unanimous_positive] = self.positive_class
        output[unanimous_non_positive] = predictions[unanimous_non_positive, 0]
        return output


class SoftVotingEnsemble:
    """Average base probabilities."""

    def __init__(self, *, class_count: int, base_count: int) -> None:
        self.class_count = class_count
        self.base_count = base_count

    def predict(self, stack_features: np.ndarray) -> np.ndarray:
        probabilities = probabilities_from_stack(stack_features, self.base_count, self.class_count)
        return probabilities.mean(axis=1).argmax(axis=1).astype(np.int64)

    def predict_proba(self, stack_features: np.ndarray) -> np.ndarray:
        probabilities = probabilities_from_stack(stack_features, self.base_count, self.class_count)
        return probabilities.mean(axis=1)


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the audit-v6 comparison run.

    Returns
    -------
    argparse.Namespace
        Paths, model hyperparameters, split settings, and latency-sampling
        controls used by the experiment.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cnn-checkpoint", type=Path, default=DEFAULT_CNN_CHECKPOINT)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--tree-iterations", type=int, default=160)
    parser.add_argument("--stacker-iterations", type=int, default=140)
    parser.add_argument("--svm-max-iter", type=int, default=3_000)
    parser.add_argument("--logistic-max-iter", type=int, default=1_000)
    parser.add_argument("--mlp-max-iter", type=int, default=180)
    parser.add_argument("--cnn-epochs", type=int, default=8)
    parser.add_argument("--cnn-batch-size", type=int, default=64)
    parser.add_argument("--cnn-workers", type=int, default=4)
    parser.add_argument("--cnn-freeze-backbone-epochs", type=int, default=2)
    parser.add_argument("--cnn-lr", type=float, default=3e-4)
    parser.add_argument("--cnn-weight-decay", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--target-false-clear", type=float, default=0.0025)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--reuse-cnn-oof", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Train and evaluate base models plus CNN-inclusive ensembles.

    Notes
    -----
    This entrypoint is deliberately offline-only. It writes metrics and model
    artifacts under ``data/work/`` so the submission can document the experiment
    without promoting heavyweight research artifacts into the runtime image.
    """

    args = parse_args()
    configure_cpu(args.threads)
    limit_cv2_threads()
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    warnings.filterwarnings("ignore", message="The max_iter was reached.*")
    np.random.seed(args.seed)

    audit_dir = resolve_path(args.audit_dir)
    output_dir = resolve_path(args.output_dir)
    for child in ("features", "manifests", "metrics", "models", "cnn-folds"):
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    rows_by_split = load_audit_manifest(audit_dir / "manifest.csv")
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
    y = {
        split: encode_labels([row.boldness_label for row in rows_by_split[split]])
        for split in ("train", "validation", "test")
    }
    print(
        f"Loaded audit-v6: train={len(y['train'])}, validation={len(y['validation'])}, test={len(y['test'])}",
        flush=True,
    )

    classical = train_classical_oof(args, datasets, y, output_dir)
    cnn = train_cnn_oof(args, audit_dir, rows_by_split, y, output_dir)
    base_probabilities = merge_base_probabilities(classical, cnn)
    stack_features = {
        split: make_probability_stack(base_probabilities[split])
        for split in ("train", "validation", "test")
    }

    base_results = evaluate_base_models(base_probabilities, y, rows_by_split, args)
    ensemble_results = train_and_evaluate_ensembles(
        stack_features=stack_features,
        y=y,
        rows_by_split=rows_by_split,
        args=args,
        output_dir=output_dir,
    )
    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "Audit-v6 comparison of base models and ensembles with CNN included as a base learner.",
        "audit_dir": str(audit_dir.relative_to(ROOT)),
        "audit_manifest_sha256": sha256_file(audit_dir / "manifest.csv"),
        "output_dir": str(output_dir.relative_to(ROOT)),
        "seed": args.seed,
        "folds": args.folds,
        "class_names": list(CLASS_NAMES),
        "positive_class": POSITIVE_CLASS,
        "review_class": REVIEW_CLASS,
        "methodology": {
            "dataset": "audit-v6 with COLA-derived images plus synthetic/review examples",
            "base_oof": "5-fold out-of-fold predictions on audit-v6 train",
            "cnn_oof": "MobileNetV3 fold models trained on audit-v6 train folds",
            "final_base_models": "fit on full audit-v6 train for validation/test probabilities",
            "stackers_fit_on": "out-of-fold train probabilities from all base models including CNN",
            "thresholds_tuned_on": "audit-v6 validation probabilities",
            "final_scored_on": "audit-v6 test",
            "test_usage": "never used for fitting, threshold selection, or model selection",
        },
        "split_counts": {
            split: {
                "rows": len(rows_by_split[split]),
                "labels": dict(sorted(Counter(row.boldness_label for row in rows_by_split[split]).items())),
            }
            for split in ("train", "validation", "test")
        },
        "base_results": base_results,
        "ensemble_results": ensemble_results,
    }
    write_json(output_dir / "metrics/summary.json", summary)
    write_report(output_dir / "metrics/report.md", summary)
    print_compact_table(summary)


def train_classical_oof(
    args: argparse.Namespace,
    datasets: dict[str, tuple[np.ndarray, list[dict[str, Any]]]],
    y: dict[str, np.ndarray],
    output_dir: Path,
) -> dict[str, dict[str, np.ndarray]]:
    """Train classical base learners and return train OOF plus full-model probabilities."""

    result: dict[str, dict[str, np.ndarray]] = {}
    splitter = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    train_x = datasets["train"][0]
    for model_name in BASE_MODELS:
        print(f"Classical OOF: {model_name}", flush=True)
        oof = np.zeros((len(train_x), len(CLASS_NAMES)), dtype=np.float32)
        fold_metrics: list[dict[str, Any]] = []
        for fold, (fit_idx, hold_idx) in enumerate(splitter.split(train_x, y["train"]), start=1):
            model = build_tabular_model(model_name, args)
            started = time.perf_counter()
            model.fit(train_x[fit_idx], y["train"][fit_idx])
            train_ms = (time.perf_counter() - started) * 1000
            oof[hold_idx] = probability_like_scores(model, train_x[hold_idx], len(CLASS_NAMES)).astype(np.float32)
            fold_metrics.append({"fold": fold, "train_ms": train_ms, "holdout_rows": int(len(hold_idx))})
        final_model = build_tabular_model(model_name, args)
        started = time.perf_counter()
        final_model.fit(train_x, y["train"])
        final_train_ms = (time.perf_counter() - started) * 1000
        result[model_name] = {
            "train": oof,
            "validation": probability_like_scores(final_model, datasets["validation"][0], len(CLASS_NAMES)).astype(np.float32),
            "test": probability_like_scores(final_model, datasets["test"][0], len(CLASS_NAMES)).astype(np.float32),
            "train_full": probability_like_scores(final_model, train_x, len(CLASS_NAMES)).astype(np.float32),
            "fit_ms": np.array([final_train_ms], dtype=np.float32),
        }
        joblib.dump(
            {
                "model": final_model,
                "class_names": CLASS_NAMES,
                "feature_config": asdict(FeatureConfig()),
                "fold_metrics": fold_metrics,
            },
            output_dir / f"models/{model_name}.joblib",
        )
    return result


def train_cnn_oof(
    args: argparse.Namespace,
    audit_dir: Path,
    rows_by_split: dict[str, list[Any]],
    y: dict[str, np.ndarray],
    output_dir: Path,
) -> dict[str, dict[str, np.ndarray]]:
    """Train CNN fold models for OOF probabilities and load final CNN for test probabilities."""

    train_oof_path = output_dir / "features/cnn_train_oof_probs.npy"
    if args.reuse_cnn_oof and train_oof_path.exists():
        train_oof = np.load(train_oof_path)
    else:
        train_oof = np.zeros((len(rows_by_split["train"]), len(CLASS_NAMES)), dtype=np.float32)
        splitter = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
        train_tf, eval_tf = build_transforms(args.image_size)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device.type != "cuda":
            raise SystemExit("CUDA is required for CNN OOF training.")
        for fold, (fit_idx, hold_idx) in enumerate(splitter.split(np.zeros(len(y["train"])), y["train"]), start=1):
            print(f"CNN OOF fold {fold}/{args.folds}", flush=True)
            configure_reproducibility(args.seed + fold)
            fit_rows = [rows_by_split["train"][idx] for idx in fit_idx]
            hold_rows = [rows_by_split["train"][idx] for idx in hold_idx]
            fit_loader = DataLoader(
                AuditV6Dataset(audit_dir, fit_rows, transform=train_tf),
                batch_size=args.cnn_batch_size,
                shuffle=True,
                num_workers=args.cnn_workers,
                pin_memory=True,
            )
            hold_loader = DataLoader(
                AuditV6Dataset(audit_dir, hold_rows, transform=eval_tf),
                batch_size=args.cnn_batch_size,
                shuffle=False,
                num_workers=args.cnn_workers,
                pin_memory=True,
            )
            model = build_cnn_model(class_count=len(CLASS_NAMES), weights="imagenet").to(device)
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.cnn_lr, weight_decay=args.cnn_weight_decay)
            criterion = nn.CrossEntropyLoss(weight=class_weights(fit_rows).to(device))
            for epoch in range(1, args.cnn_epochs + 1):
                set_cnn_backbone_trainability(model, trainable=epoch > args.cnn_freeze_backbone_epochs)
                stats = run_train_epoch(model, fit_loader, optimizer, criterion, device)
                print(f"  fold {fold} epoch {epoch}: loss={stats['loss']:.4f} acc={stats['accuracy']:.4f}", flush=True)
            train_oof[hold_idx] = cnn_predict_proba(model, hold_loader, device)
            torch.save({"model": model.state_dict(), "class_names": CLASS_NAMES}, output_dir / f"cnn-folds/fold_{fold}.pt")
        np.save(train_oof_path, train_oof)

    final_probs = final_cnn_probabilities(args, audit_dir, rows_by_split)
    return {
        CNN_MODEL_NAME: {
            "train": train_oof,
            "validation": final_probs["validation"],
            "test": final_probs["test"],
            "train_full": final_probs["train"],
            "fit_ms": np.array([0.0], dtype=np.float32),
        }
    }


def final_cnn_probabilities(args: argparse.Namespace, audit_dir: Path, rows_by_split: dict[str, list[Any]]) -> dict[str, np.ndarray]:
    """Load the full-train CNN checkpoint and compute probabilities."""

    checkpoint_path = resolve_path(args.cnn_checkpoint)
    if not checkpoint_path.exists():
        raise SystemExit(f"Missing CNN checkpoint: {checkpoint_path}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model = build_cnn_model(class_count=len(CLASS_NAMES), weights="none")
    model.load_state_dict(checkpoint["model"])
    model.to(device)
    _, eval_tf = build_transforms(args.image_size)
    probs: dict[str, np.ndarray] = {}
    for split in ("train", "validation", "test"):
        loader = DataLoader(
            AuditV6Dataset(audit_dir, rows_by_split[split], transform=eval_tf),
            batch_size=args.cnn_batch_size,
            shuffle=False,
            num_workers=args.cnn_workers,
            pin_memory=True,
        )
        probs[split] = cnn_predict_proba(model, loader, device)
    return probs


@torch.inference_mode()
def cnn_predict_proba(model: nn.Module, loader: DataLoader, device: torch.device) -> np.ndarray:
    """Return CNN softmax probabilities in dataloader order."""

    model.eval()
    chunks: list[np.ndarray] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        probs = torch.softmax(model(images), dim=1)
        chunks.append(probs.detach().cpu().numpy().astype(np.float32))
    return np.vstack(chunks)


def set_cnn_backbone_trainability(model: nn.Module, *, trainable: bool) -> None:
    """Freeze/unfreeze MobileNet feature layers."""

    for parameter in model.features.parameters():
        parameter.requires_grad = trainable
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True


def merge_base_probabilities(*sources: dict[str, dict[str, np.ndarray]]) -> dict[str, dict[str, np.ndarray]]:
    """Merge classical and CNN probability dictionaries by split.

    Parameters
    ----------
    *sources:
        Probability dictionaries keyed by model name and split name.

    Returns
    -------
    dict[str, dict[str, numpy.ndarray]]
        Split-first probability dictionary used by the stacker feature builder.
    """

    merged: dict[str, dict[str, np.ndarray]] = {split: {} for split in ("train", "validation", "test", "train_full")}
    for source in sources:
        for model_name, split_probs in source.items():
            for split, probs in split_probs.items():
                if split == "fit_ms":
                    continue
                merged[split][model_name] = probs
    return merged


def make_probability_stack(probabilities_by_model: dict[str, np.ndarray]) -> np.ndarray:
    """Create stacker feature matrix from model probability blocks."""

    return np.hstack([probabilities_by_model[name] for name in ALL_BASE_NAMES]).astype(np.float32)


def probabilities_from_stack(stack: np.ndarray, base_count: int, class_count: int) -> np.ndarray:
    """Reshape flat stacker features back into model-by-class probabilities.

    Parameters
    ----------
    stack:
        Two-dimensional array whose columns are concatenated base-model
        probabilities.
    base_count:
        Number of base learners included in the stack.
    class_count:
        Number of target classes per base learner.

    Returns
    -------
    numpy.ndarray
        Array with shape ``(rows, base_count, class_count)``.
    """

    return stack.reshape(len(stack), base_count, class_count)


def train_and_evaluate_ensembles(
    *,
    stack_features: dict[str, np.ndarray],
    y: dict[str, np.ndarray],
    rows_by_split: dict[str, list[Any]],
    args: argparse.Namespace,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Train stackers with CNN included and evaluate on train/test."""

    predictors: list[tuple[str, Any, dict[str, Any]]] = []
    class_count = len(CLASS_NAMES)
    base_count = len(ALL_BASE_NAMES)
    predictors.append(
        (
            "soft_voting_all_bases",
            SoftVotingEnsemble(class_count=class_count, base_count=base_count),
            {"fit_ms": 0.0, "stacker_input": list(ALL_BASE_NAMES)},
        )
    )
    predictors.append(
        (
            "strict_veto_all_bases",
            StrictVetoProbabilityEnsemble(
                positive_class=CLASS_NAMES.index(POSITIVE_CLASS),
                review_class=CLASS_NAMES.index(REVIEW_CLASS),
                class_count=class_count,
                base_count=base_count,
            ),
            {"fit_ms": 0.0, "stacker_input": list(ALL_BASE_NAMES)},
        )
    )

    stackers = [
        (
            "logistic_stacker_all_bases",
            Pipeline(
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
            ),
            False,
        ),
        ("lightgbm_stacker_all_bases", build_lightgbm_stacker(args), False),
        ("xgboost_stacker_all_bases", build_xgboost_stacker(args), False),
        ("catboost_stacker_all_bases", build_catboost_stacker(args), False),
        ("lightgbm_reject_all_bases", build_lightgbm_stacker(args), True),
        ("xgboost_reject_all_bases", build_xgboost_stacker(args), True),
    ]
    for name, stacker, tune_reject in stackers:
        print(f"Training ensemble with CNN base: {name}", flush=True)
        started = time.perf_counter()
        stacker.fit(stack_features["train"], y["train"])
        train_ms = (time.perf_counter() - started) * 1000
        predictor: Any = ProbabilityStacker(stacker)
        extra: dict[str, Any] = {"fit_ms": train_ms, "stacker_input": list(ALL_BASE_NAMES)}
        if tune_reject:
            threshold, tuning = tune_positive_reject_threshold(
                stacker,
                stack_features["validation"],
                y["validation"],
                target_false_clear=args.target_false_clear,
            )
            predictor = PositiveRejectWrapper(ProbabilityStacker(stacker), threshold=threshold)
            extra.update({"threshold": threshold, "threshold_tuning": tuning})
        predictors.append((name, predictor, extra))

    results: list[dict[str, Any]] = []
    for name, predictor, extra in predictors:
        result = evaluate_probability_predictor(
            predictor,
            model_name=name,
            train_features=stack_features["train"],
            validation_features=stack_features["validation"],
            test_features=stack_features["test"],
            y=y,
            rows_by_split=rows_by_split,
            fit_ms=extra.pop("fit_ms"),
            latency_rows=args.latency_rows,
            extra=extra,
        )
        results.append(result)
        write_confusion_csv(output_dir / f"metrics/{name}__test_confusion.csv", result["test"]["confusion"])
        joblib.dump({"model": predictor, "class_names": CLASS_NAMES, "metrics": result}, output_dir / f"models/{name}.joblib")
    return results


def evaluate_base_models(
    base_probabilities: dict[str, dict[str, np.ndarray]],
    y: dict[str, np.ndarray],
    rows_by_split: dict[str, list[Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """Evaluate OOF train and final test probabilities for each base learner."""

    results = []
    for model_name in ALL_BASE_NAMES:
        predictor = PrecomputedProbabilityPredictor(base_probabilities, model_name)
        results.append(
            {
                "model": model_name,
                "class_names": list(CLASS_NAMES),
                "train": compute_metrics(y["train"], base_probabilities["train"][model_name].argmax(axis=1)),
                "train_full_in_sample": compute_metrics(y["train"], base_probabilities["train_full"][model_name].argmax(axis=1)),
                "validation": compute_metrics(y["validation"], base_probabilities["validation"][model_name].argmax(axis=1)),
                "test": compute_metrics(y["test"], base_probabilities["test"][model_name].argmax(axis=1)),
                "test_breakdowns": compute_breakdowns(
                    y["test"],
                    base_probabilities["test"][model_name].argmax(axis=1),
                    rows_by_split["test"],
                ),
                "latency": {"single_row_p95_ms": None, "note": "base latency measured in prior baseline/CNN runs"},
            }
        )
        del predictor
    return results


class PrecomputedProbabilityPredictor:
    """Tiny holder used only to make base result intent explicit."""

    def __init__(self, probabilities: dict[str, dict[str, np.ndarray]], model_name: str) -> None:
        self.probabilities = probabilities
        self.model_name = model_name


def evaluate_probability_predictor(
    predictor: Any,
    *,
    model_name: str,
    train_features: np.ndarray,
    validation_features: np.ndarray,
    test_features: np.ndarray,
    y: dict[str, np.ndarray],
    rows_by_split: dict[str, list[Any]],
    fit_ms: float,
    latency_rows: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a fitted probability predictor on train, validation, and test.

    Parameters
    ----------
    predictor:
        Object exposing ``predict`` and optionally ``predict_proba``.
    model_name:
        Stable name used in reports and artifact paths.
    train_features, validation_features, test_features:
        Stacker feature matrices for the corresponding split.
    y:
        Encoded labels keyed by split.
    rows_by_split:
        Original manifest rows used for breakdown reporting.
    fit_ms:
        Measured model fitting time in milliseconds.
    latency_rows:
        Number of test rows used for latency sampling.
    extra:
        Optional metadata to attach to the result.

    Returns
    -------
    dict[str, Any]
        Nested metric summary including confusion matrices, false-clear rate,
        source breakdowns, and latency.
    """

    train_pred = predict_labels(predictor, train_features)
    validation_pred = predict_labels(predictor, validation_features)
    test_pred = predict_labels(predictor, test_features)
    result: dict[str, Any] = {
        "model": model_name,
        "class_names": list(CLASS_NAMES),
        "fit_ms": fit_ms,
        "train": compute_metrics(y["train"], train_pred),
        "validation": compute_metrics(y["validation"], validation_pred),
        "test": compute_metrics(y["test"], test_pred),
        "test_breakdowns": compute_breakdowns(y["test"], test_pred, rows_by_split["test"]),
        "latency": measure_latency(predictor, test_features, latency_rows),
    }
    if extra:
        result.update(extra)
    return result


def encode_labels(labels: list[str]) -> np.ndarray:
    """Encode string labels with the experiment's class order.

    Parameters
    ----------
    labels:
        Label names from the audit manifest.

    Returns
    -------
    numpy.ndarray
        Integer class IDs aligned to ``CLASS_NAMES``.
    """

    class_to_idx = {name: idx for idx, name in enumerate(CLASS_NAMES)}
    return np.asarray([class_to_idx[label] for label in labels], dtype=np.int64)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Compute classification metrics for the typography experiment.

    Parameters
    ----------
    y_true:
        Ground-truth class IDs.
    y_pred:
        Predicted class IDs.

    Returns
    -------
    dict[str, Any]
        Accuracy, macro/weighted F1, per-class metrics, confusion matrix, and
        false-clear rate where ``bold`` is the positive class.
    """

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


def write_report(path: Path, summary: dict[str, Any]) -> None:
    """Write the Markdown summary for the CNN-inclusive comparison.

    Parameters
    ----------
    path:
        Destination Markdown file.
    summary:
        Experiment summary dictionary written beside the JSON metrics.
    """

    lines = [
        "# Audit-v6 CNN-Inclusive Ensemble Comparison",
        "",
        "All rows come from the audit-v6 image set. CNN probabilities are included as one base learner in every ensemble below.",
        "",
        "Protocol: base models use 5-fold out-of-fold train predictions; final base models score validation/test; stackers train on OOF train predictions; reject thresholds tune on validation; final metrics are test-only.",
        "",
        "## Base Learners",
        "",
        "| Model | Train OOF F1 | Train OOF FC | Test Acc | Test F1 | Test FC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in summary["base_results"]:
        lines.append(format_result_row(result, include_model=True))
    lines.extend(
        [
            "",
            "## CNN-Inclusive Ensembles",
            "",
            "| Model | Train F1 | Train FC | Test Acc | Test F1 | Test FC | p95 ms |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in summary["ensemble_results"]:
        lines.append(
            f"| {pretty_name(result['model'])} | {result['train']['macro_f1']:.4f} | "
            f"{result['train']['false_clear_rate']:.4f} | {result['test']['accuracy']:.4f} | "
            f"{result['test']['macro_f1']:.4f} | {result['test']['false_clear_rate']:.4f} | "
            f"{result['latency']['single_row_p95_ms']:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_result_row(result: dict[str, Any], *, include_model: bool) -> str:
    """Format one base-model metric row for the Markdown report.

    Parameters
    ----------
    result:
        Metric dictionary for one model.
    include_model:
        Retained for compatibility with earlier report code; the current format
        always includes the model name.

    Returns
    -------
    str
        Markdown table row.
    """

    name = pretty_name(result["model"])
    return (
        f"| {name} | {result['train']['macro_f1']:.4f} | {result['train']['false_clear_rate']:.4f} | "
        f"{result['test']['accuracy']:.4f} | {result['test']['macro_f1']:.4f} | "
        f"{result['test']['false_clear_rate']:.4f} |"
    )


def pretty_name(name: str) -> str:
    """Return a reviewer-friendly model name.

    Parameters
    ----------
    name:
        Internal model key.

    Returns
    -------
    str
        Display name used in terminal and Markdown reports.
    """

    return {
        "svm": "SVM",
        "xgboost": "XGBoost",
        "lightgbm": "LightGBM",
        "logistic_regression": "Logistic Regression",
        "mlp": "MLP",
        "catboost": "CatBoost",
        CNN_MODEL_NAME: "MobileNetV3 CNN",
        "soft_voting_all_bases": "Soft voting, all bases + CNN",
        "strict_veto_all_bases": "Strict veto, all bases + CNN",
        "logistic_stacker_all_bases": "Logistic stacker, all bases + CNN",
        "lightgbm_stacker_all_bases": "LightGBM stacker, all bases + CNN",
        "xgboost_stacker_all_bases": "XGBoost stacker, all bases + CNN",
        "catboost_stacker_all_bases": "CatBoost stacker, all bases + CNN",
        "lightgbm_reject_all_bases": "LightGBM reject, all bases + CNN",
        "xgboost_reject_all_bases": "XGBoost reject, all bases + CNN",
    }.get(name, name)


def print_compact_table(summary: dict[str, Any]) -> None:
    """Print the high-signal train/test statistics to the terminal.

    Parameters
    ----------
    summary:
        Experiment summary containing base and ensemble result lists.
    """

    print("\nBASE LEARNERS")
    for result in summary["base_results"]:
        print(
            f"{pretty_name(result['model'])}: train_oof_f1={result['train']['macro_f1']:.4f} "
            f"train_oof_fc={result['train']['false_clear_rate']:.4f} "
            f"test_f1={result['test']['macro_f1']:.4f} test_fc={result['test']['false_clear_rate']:.4f}"
        )
    print("\nENSEMBLES WITH CNN")
    for result in summary["ensemble_results"]:
        print(
            f"{pretty_name(result['model'])}: train_f1={result['train']['macro_f1']:.4f} "
            f"train_fc={result['train']['false_clear_rate']:.4f} "
            f"test_f1={result['test']['macro_f1']:.4f} test_fc={result['test']['false_clear_rate']:.4f}"
        )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file.

    Parameters
    ----------
    path:
        File to hash.

    Returns
    -------
    str
        Hexadecimal SHA-256 digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
