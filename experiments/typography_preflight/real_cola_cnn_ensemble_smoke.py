"""Smoke-test audit-v6 CNN-inclusive ensembles on real COLA heading crops.

This script is intentionally narrow. It reuses the real approved COLA
``GOVERNMENT WARNING:`` heading crops produced by ``real_cola_smoke.py`` and
scores them with the audit-v6 base learners and CNN-inclusive ensemble
artifacts.

The run answers an operational smoke question:

```
Can the saved base models, CNN, and ensembles all score real COLA heading crops
without crashing, and how quickly do they run?
```

Approved public COLA crops are positive-domain examples. They cannot estimate
false-clear risk, because they do not include real rejected/non-bold public
applications. Synthetic negatives remain the false-clear measurement source.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from experiments.typography_preflight.compare_audit_v6_baselines import (
    CLASS_NAMES,
    BASE_MODELS,
    FeatureConfig,
    extract_feature_vector,
    limit_cv2_threads,
    probability_like_scores,
)
from experiments.typography_preflight.compare_audit_v6_cnn_ensemble import (
    ALL_BASE_NAMES,
    CNN_MODEL_NAME,
    PositiveRejectWrapper,
    ProbabilityStacker,
    SoftVotingEnsemble,
    StrictVetoProbabilityEnsemble,
)
from experiments.typography_preflight.train_audit_v6_cnn import (
    build_model as build_cnn_model,
    build_transforms,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CROP_RUN = ROOT / "data/work/typography-preflight/real-cola-smoke-v2-trainval-heading-only"
DEFAULT_MODEL_DIR = ROOT / "data/work/typography-preflight/model-comparison-audit-v6-cnn-ensemble-v1/models"
DEFAULT_CNN_CHECKPOINT = ROOT / "data/work/typography-preflight/cnn-audit-v6-mobilenet-v1/models/mobilenet_v3_small_best.pt"
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/real-cola-cnn-ensemble-smoke-v1"
ENSEMBLE_MODELS = (
    "soft_voting_all_bases",
    "strict_veto_all_bases",
    "logistic_stacker_all_bases",
    "lightgbm_stacker_all_bases",
    "xgboost_stacker_all_bases",
    "catboost_stacker_all_bases",
    "lightgbm_reject_all_bases",
    "xgboost_reject_all_bases",
)
MODEL_LABELS = {
    "svm": "SVM",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "logistic_regression": "Logistic Regression",
    "mlp": "MLP",
    "catboost": "CatBoost",
    CNN_MODEL_NAME: "MobileNetV3 CNN",
    "soft_voting_all_bases": "Soft voting + CNN",
    "strict_veto_all_bases": "Strict veto + CNN",
    "logistic_stacker_all_bases": "Logistic stacker + CNN",
    "lightgbm_stacker_all_bases": "LightGBM stacker + CNN",
    "xgboost_stacker_all_bases": "XGBoost stacker + CNN",
    "catboost_stacker_all_bases": "CatBoost stacker + CNN",
    "lightgbm_reject_all_bases": "LightGBM reject + CNN",
    "xgboost_reject_all_bases": "XGBoost reject + CNN",
}
POSITIVE_CLASS = "bold"
REVIEW_CLASS = "unreadable_review"


@dataclass(frozen=True)
class CropRow:
    """One real COLA heading crop from the existing crop smoke run."""

    ttb_id: str
    image_path: str
    engine: str
    crop_path: str
    matched_text: str
    match_score: float
    ocr_confidence: str


class CropDataset(Dataset[dict[str, Any]]):
    """Torch dataset for arbitrary heading crop paths."""

    def __init__(self, root: Path, rows: list[CropRow], transform: Any) -> None:
        self.root = root
        self.rows = rows
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        image = Image.open(self.root / row.crop_path).convert("RGB")
        return {"image": self.transform(image), "index": index}


def main() -> None:
    """Run the real-COLA CNN-inclusive ensemble smoke test."""

    patch_pickle_main_namespace()
    args = parse_args()
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    limit_cv2_threads()
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics").mkdir(parents=True, exist_ok=True)

    crop_run = resolve_path(args.crop_run)
    rows = load_crop_rows(crop_run / "metrics/heading_crops.csv", limit=args.limit)
    if not rows:
        raise SystemExit(f"No heading crop rows found in {crop_run}")
    print(f"Loaded {len(rows)} real COLA heading crops", flush=True)

    feature_matrix, feature_timing = extract_features(crop_run, rows)
    base_models = load_base_models(resolve_path(args.model_dir))
    base_probabilities, base_timing = score_classical_base_models(base_models, feature_matrix)
    cnn_probabilities, cnn_timing = score_cnn(resolve_path(args.cnn_checkpoint), crop_run, rows, args)
    base_probabilities[CNN_MODEL_NAME] = cnn_probabilities
    stack_features = make_probability_stack(base_probabilities)
    ensemble_models = load_ensemble_models(resolve_path(args.model_dir))
    ensemble_results, ensemble_timing, row_predictions = score_predictors(
        base_probabilities=base_probabilities,
        ensemble_models=ensemble_models,
        stack_features=stack_features,
        rows=rows,
    )

    summary = build_summary(
        rows=rows,
        base_probabilities=base_probabilities,
        ensemble_results=ensemble_results,
        feature_timing=feature_timing,
        base_timing=base_timing,
        cnn_timing=cnn_timing,
        ensemble_timing=ensemble_timing,
        args=args,
        crop_run=crop_run,
    )
    write_json(output_dir / "metrics/summary.json", summary)
    write_csv(output_dir / "metrics/predictions.csv", row_predictions)
    write_report(output_dir / "metrics/report.md", summary)
    print_compact(summary)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-run", type=Path, default=DEFAULT_CROP_RUN)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--cnn-checkpoint", type=Path, default=DEFAULT_CNN_CHECKPOINT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Optional crop limit; 0 means all crops.")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    return parser.parse_args()


def patch_pickle_main_namespace() -> None:
    """Expose custom classes for joblib artifacts saved from ``__main__``."""

    main_module = sys.modules["__main__"]
    for cls in (
        ProbabilityStacker,
        PositiveRejectWrapper,
        StrictVetoProbabilityEnsemble,
        SoftVotingEnsemble,
    ):
        setattr(main_module, cls.__name__, cls)


def resolve_path(path: Path) -> Path:
    """Resolve paths relative to the repository root."""

    return path if path.is_absolute() else ROOT / path


def load_crop_rows(path: Path, *, limit: int) -> list[CropRow]:
    """Load existing heading crop rows."""

    rows: list[CropRow] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                CropRow(
                    ttb_id=raw["ttb_id"],
                    image_path=raw["image_path"],
                    engine=raw["engine"],
                    crop_path=raw["crop_path"],
                    matched_text=raw.get("matched_text", ""),
                    match_score=float(raw.get("match_score") or 0.0),
                    ocr_confidence=raw.get("ocr_confidence", ""),
                )
            )
            if limit and len(rows) >= limit:
                break
    return rows


def extract_features(crop_run: Path, rows: list[CropRow]) -> tuple[np.ndarray, dict[str, float]]:
    """Extract OpenCV features for all real COLA crops."""

    config = FeatureConfig()
    vectors: list[np.ndarray] = []
    timings: list[float] = []
    for row in rows:
        image = cv2.imread(str(crop_run / row.crop_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Could not read crop: {crop_run / row.crop_path}")
        started = time.perf_counter()
        vectors.append(extract_feature_vector(image, config))
        timings.append((time.perf_counter() - started) * 1000)
    return np.vstack(vectors), summarize_numbers(timings)


def load_base_models(model_dir: Path) -> dict[str, Any]:
    """Load final audit-v6 base learners."""

    models = {}
    for name in BASE_MODELS:
        payload = joblib.load(model_dir / f"{name}.joblib")
        models[name] = payload["model"]
    return models


def score_classical_base_models(
    models: dict[str, Any],
    features: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, float]]]:
    """Score all classical base models on OpenCV features."""

    probabilities: dict[str, np.ndarray] = {}
    timings: dict[str, dict[str, float]] = {}
    for name in BASE_MODELS:
        model = models[name]
        started = time.perf_counter()
        probabilities[name] = probability_like_scores(model, features, len(CLASS_NAMES)).astype(np.float32)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings[name] = {
            "total_ms": round(elapsed_ms, 6),
            "mean_ms_per_crop": round(elapsed_ms / max(len(features), 1), 6),
        }
    return probabilities, timings


def choose_device(requested: str) -> torch.device:
    """Choose CNN inference device."""

    if requested == "cuda":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device("cpu")


@torch.inference_mode()
def score_cnn(
    checkpoint_path: Path,
    crop_run: Path,
    rows: list[CropRow],
    args: argparse.Namespace,
) -> tuple[np.ndarray, dict[str, float | str]]:
    """Score the MobileNetV3 CNN on real COLA crops."""

    device = choose_device(args.device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model = build_cnn_model(class_count=len(CLASS_NAMES), weights="none")
    model.load_state_dict(checkpoint["model"])
    model.to(device)
    model.eval()
    _, transform = build_transforms(args.image_size)
    loader = DataLoader(
        CropDataset(crop_run, rows, transform),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=device.type == "cuda",
    )
    chunks: list[np.ndarray] = []
    started = time.perf_counter()
    for batch in loader:
        images = batch["image"].to(device, non_blocking=device.type == "cuda")
        probs = torch.softmax(model(images), dim=1)
        chunks.append(probs.detach().cpu().numpy().astype(np.float32))
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return np.vstack(chunks), {
        "device": device.type,
        "total_ms": round(elapsed_ms, 6),
        "mean_ms_per_crop": round(elapsed_ms / max(len(rows), 1), 6),
    }


def make_probability_stack(probabilities_by_model: dict[str, np.ndarray]) -> np.ndarray:
    """Create stacker features in the training-time base model order."""

    return np.hstack([probabilities_by_model[name] for name in ALL_BASE_NAMES]).astype(np.float32)


def load_ensemble_models(model_dir: Path) -> dict[str, Any]:
    """Load saved audit-v6 CNN-inclusive ensemble predictors."""

    models = {}
    for name in ENSEMBLE_MODELS:
        payload = joblib.load(model_dir / f"{name}.joblib")
        models[name] = payload["model"]
    return models


def score_predictors(
    *,
    base_probabilities: dict[str, np.ndarray],
    ensemble_models: dict[str, Any],
    stack_features: np.ndarray,
    rows: list[CropRow],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]], list[dict[str, Any]]]:
    """Score base learners and ensemble predictors."""

    results: dict[str, dict[str, Any]] = {}
    timings: dict[str, dict[str, float]] = {}
    prediction_rows: list[dict[str, Any]] = []

    for name in ALL_BASE_NAMES:
        started = time.perf_counter()
        predictions = base_probabilities[name].argmax(axis=1)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings[name] = {"total_ms": round(elapsed_ms, 6), "mean_ms_per_crop": round(elapsed_ms / max(len(rows), 1), 6)}
        results[name] = summarize_predictions(rows, predictions)
        add_prediction_rows(prediction_rows, rows, name, "base_model", predictions)

    for name, model in ensemble_models.items():
        started = time.perf_counter()
        predictions = np.asarray(model.predict(stack_features), dtype=np.int64)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings[name] = {"total_ms": round(elapsed_ms, 6), "mean_ms_per_crop": round(elapsed_ms / max(len(rows), 1), 6)}
        results[name] = summarize_predictions(rows, predictions)
        add_prediction_rows(prediction_rows, rows, name, "ensemble", predictions)

    return results, timings, prediction_rows


def summarize_predictions(rows: list[CropRow], predictions: np.ndarray) -> dict[str, Any]:
    """Summarize predictions treating real approved headings as positive-domain examples."""

    labels = [CLASS_NAMES[int(pred)] for pred in predictions]
    counts = dict(sorted(Counter(labels).items()))
    positive = sum(label == POSITIVE_CLASS for label in labels)
    review = sum(label == REVIEW_CLASS for label in labels)
    by_app: dict[str, list[str]] = defaultdict(list)
    for row, label in zip(rows, labels, strict=True):
        by_app[row.ttb_id].append(label)
    app_decisions = Counter(app_decision(labels_for_app) for labels_for_app in by_app.values())
    app_total = max(len(by_app), 1)
    return {
        "crop_predictions": len(labels),
        "prediction_counts": counts,
        "positive_clear_rate": round(positive / max(len(labels), 1), 6),
        "review_rate": round(review / max(len(labels), 1), 6),
        "application_count": len(by_app),
        "application_decision_counts": dict(sorted(app_decisions.items())),
        "application_positive_clear_rate": round(app_decisions["cleared_expected_positive"] / app_total, 6),
        "application_review_rate": round(app_decisions["needs_review"] / app_total, 6),
    }


def app_decision(labels: list[str]) -> str:
    """Collapse crop predictions into an application-level positive-domain decision."""

    if any(label == POSITIVE_CLASS for label in labels):
        return "cleared_expected_positive"
    if any(label == REVIEW_CLASS for label in labels):
        return "needs_review"
    return "flagged_negative"


def add_prediction_rows(
    output: list[dict[str, Any]],
    rows: list[CropRow],
    model_name: str,
    model_type: str,
    predictions: np.ndarray,
) -> None:
    """Append per-crop prediction rows."""

    for row, prediction in zip(rows, predictions, strict=True):
        output.append(
            {
                "ttb_id": row.ttb_id,
                "image_path": row.image_path,
                "engine": row.engine,
                "crop_path": row.crop_path,
                "model_type": model_type,
                "model": model_name,
                "model_label": MODEL_LABELS[model_name],
                "predicted_class": CLASS_NAMES[int(prediction)],
                "matched_text": row.matched_text,
                "match_score": row.match_score,
                "ocr_confidence": row.ocr_confidence,
            }
        )


def build_summary(
    *,
    rows: list[CropRow],
    base_probabilities: dict[str, np.ndarray],
    ensemble_results: dict[str, dict[str, Any]],
    feature_timing: dict[str, float],
    base_timing: dict[str, dict[str, float]],
    cnn_timing: dict[str, float | str],
    ensemble_timing: dict[str, dict[str, float]],
    args: argparse.Namespace,
    crop_run: Path,
) -> dict[str, Any]:
    """Build summary JSON."""

    app_count = len({row.ttb_id for row in rows})
    image_count = len({row.image_path for row in rows})
    models: list[dict[str, Any]] = []
    for name in ALL_BASE_NAMES:
        latency = cnn_timing if name == CNN_MODEL_NAME else base_timing[name]
        models.append(
            {
                "type": "base_model",
                "model": name,
                "model_label": MODEL_LABELS[name],
                **ensemble_results[name],
                "latency_ms": latency,
            }
        )
    for name in ENSEMBLE_MODELS:
        models.append(
            {
                "type": "ensemble",
                "model": name,
                "model_label": MODEL_LABELS[name],
                **ensemble_results[name],
                "latency_ms": ensemble_timing[name],
            }
        )
    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "Smoke test audit-v6 CNN-inclusive base learners and ensembles on real approved COLA warning-heading crops.",
        "important_limitations": [
            "Approved public COLA heading crops are positive-domain examples; this smoke cannot estimate false-clear safety.",
            "Synthetic non-bold/review crops remain the false-clear measurement source.",
            "Latency is measured from cached crops and saved models; it excludes OCR and heading-crop discovery.",
            "Ensemble latency is aggregator-only after base probability generation.",
        ],
        "inputs": {
            "crop_run": str(crop_run),
            "model_dir": str(resolve_path(args.model_dir)),
            "cnn_checkpoint": str(resolve_path(args.cnn_checkpoint)),
            "limit": args.limit,
            "cnn_device": cnn_timing["device"],
        },
        "counts": {
            "heading_crops": len(rows),
            "applications": app_count,
            "source_images": image_count,
            "crops_by_engine": dict(sorted(Counter(row.engine for row in rows).items())),
        },
        "stage_latency_ms": {
            "feature_extraction": feature_timing,
            "cnn_inference": cnn_timing,
        },
        "models": models,
        "base_order_for_ensembles": list(ALL_BASE_NAMES),
        "class_names": list(CLASS_NAMES),
    }


def summarize_numbers(values: list[float]) -> dict[str, float | int | None]:
    """Summarize a list of timings."""

    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None, "max": None}
    ordered = sorted(float(value) for value in values)
    p95_idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "count": len(ordered),
        "mean": round(statistics.fmean(ordered), 6),
        "median": round(statistics.median(ordered), 6),
        "p95": round(ordered[p95_idx], 6),
        "max": round(max(ordered), 6),
    }


def write_json(path: Path, payload: Any) -> None:
    """Write JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write CSV rows."""

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    """Write Markdown report."""

    lines = [
        "# Real COLA CNN-Inclusive Ensemble Smoke",
        "",
        "Approved public COLA heading crops are positive-domain examples. This run checks runtime behavior and real-crop clear rates; it does not estimate false-clear safety.",
        "",
        f"Heading crops: {summary['counts']['heading_crops']}",
        f"Applications represented: {summary['counts']['applications']}",
        f"Source images represented: {summary['counts']['source_images']}",
        "",
        "| Type | Model / Policy | Crop clear rate | App clear rate | Crop review rate | App review rate | Predicted bold | Predicted review | Mean ms/crop |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in summary["models"]:
        counts = model["prediction_counts"]
        latency = model["latency_ms"]
        lines.append(
            f"| {model['type']} | {model['model_label']} | "
            f"{model['positive_clear_rate']:.4f} | {model['application_positive_clear_rate']:.4f} | "
            f"{model['review_rate']:.4f} | {model['application_review_rate']:.4f} | "
            f"{counts.get(POSITIVE_CLASS, 0)} | {counts.get(REVIEW_CLASS, 0)} | "
            f"{float(latency['mean_ms_per_crop']):.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_compact(summary: dict[str, Any]) -> None:
    """Print compact terminal summary."""

    print(json.dumps({"counts": summary["counts"], "stage_latency_ms": summary["stage_latency_ms"]}, indent=2))
    print("\nMODEL SMOKE RESULTS")
    for model in summary["models"]:
        latency = model["latency_ms"]
        print(
            f"{model['type']} | {model['model_label']}: "
            f"crop_clear={model['positive_clear_rate']:.4f} app_clear={model['application_positive_clear_rate']:.4f} "
            f"crop_review={model['review_rate']:.4f} app_review={model['application_review_rate']:.4f} "
            f"mean_ms={float(latency['mean_ms_per_crop']):.4f}"
        )


if __name__ == "__main__":
    main()
