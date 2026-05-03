"""Train and evaluate an OpenCV/SVM warning-heading typography preflight.

This experiment generates synthetic crops for the known heading
``GOVERNMENT WARNING:`` and trains a support vector machine to distinguish
acceptable bold evidence from non-bold, borderline, or degraded evidence.

The experiment is intentionally CPU-only and writes artifacts under
``data/work/typography-preflight/`` so it cannot interfere with OCR conveyor
outputs or the deployed app.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import cv2
import joblib
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from experiments.typography_preflight.features import (
    FeatureConfig,
    extract_feature_vector,
    feature_names,
    limit_cv2_threads,
)


TEXT = "GOVERNMENT WARNING:"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight"
DEFAULT_FONT_ROOT = Path("/usr/share/fonts")

WEIGHT_BOLD = {"bold", "black", "heavy", "extrabold", "extra-bold", "ultrabold"}
WEIGHT_BORDERLINE = {"medium", "semibold", "semi-bold", "demibold", "demi-bold"}
WEIGHT_NON_BOLD = {"regular", "book", "light", "thin", "extralight", "extra-light"}


@dataclass(frozen=True)
class FontRecord:
    """A local font file and its inferred weight class."""

    path: str
    family: str
    weight: str


@dataclass(frozen=True)
class SampleMeta:
    """Metadata for one generated synthetic typography crop."""

    split: str
    sample_id: str
    label: int
    sublabel: str
    font_path: str
    font_family: str
    font_weight: str
    distortion_recipe: str
    font_size: int
    saved_crop: str


def main() -> None:
    """Run dataset generation, SVM training, threshold tuning, and reporting."""

    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    limit_cv2_threads()
    configure_thread_env(args.threads)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["features", "manifests", "metrics", "models", "sample_crops"]:
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    fonts = discover_fonts(Path(args.font_root))
    splits = split_fonts(fonts, seed=args.seed)
    write_font_splits(splits, output_dir / "manifests/font_splits.json")

    config = FeatureConfig()
    split_specs = [
        ("train", args.train_samples),
        ("validation", args.validation_samples),
        ("test", args.test_samples),
    ]

    datasets: dict[str, tuple[np.ndarray, np.ndarray, list[SampleMeta]]] = {}
    for split, count in split_specs:
        feature_path = output_dir / f"features/{split}.npz"
        if args.reuse_features and feature_path.exists():
            loaded = np.load(feature_path, allow_pickle=False)
            features = loaded["features"].astype(np.float32)
            labels = loaded["labels"].astype(np.int8)
            metadata = []
        else:
            features, labels, metadata = generate_split(
                split=split,
                count=count,
                fonts=splits[split],
                output_dir=output_dir,
                config=config,
                seed=args.seed,
                sample_crop_limit=args.sample_crop_limit,
            )
            save_split_artifacts(split, features, labels, metadata, output_dir, config)
        datasets[split] = (features, labels, metadata)

    model = build_model(args)

    train_x, train_y, _ = datasets["train"]
    model.fit(train_x, train_y)

    validation_x, validation_y, _ = datasets["validation"]
    validation_scores = model.decision_function(validation_x)
    threshold, validation_metrics = tune_threshold(
        validation_y,
        validation_scores,
        false_clear_tolerance=args.false_clear_tolerance,
    )

    test_x, test_y, _ = datasets["test"]
    test_scores = model.decision_function(test_x)
    test_metrics = compute_metrics(test_y, test_scores >= threshold)
    latency = measure_latency(model, test_x, threshold, args.latency_rows)

    metrics = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "text": TEXT,
        "model": model_name(args),
        "seed": args.seed,
        "feature_count": int(train_x.shape[1]),
        "feature_names_path": "manifests/feature_names.json",
        "font_split_path": "manifests/font_splits.json",
        "counts": {
            "train": int(len(train_y)),
            "validation": int(len(validation_y)),
            "test": int(len(test_y)),
        },
        "label_policy": {
            "positive": "acceptable_bold",
            "negative": [
                "regular_non_bold",
                "medium_or_borderline",
                "degraded_uncertain",
            ],
            "primary_safety_metric": "false_clear_rate",
        },
        "threshold": float(threshold),
        "false_clear_tolerance": args.false_clear_tolerance,
        "validation": validation_metrics,
        "test": test_metrics,
        "latency": latency,
        "notes": [
            "Synthetic data only; public COLA crops are still needed for positive smoke testing.",
            "Font families and distortion recipes are held out across splits.",
            "Ambiguous or degraded runtime crops should route to Needs Review.",
        ],
    }
    write_json(output_dir / "metrics/summary.json", metrics)
    write_confusion_csv(output_dir / "metrics/test_confusion_matrix.csv", test_metrics)
    joblib.dump(
        {
            "model": model,
            "threshold": float(threshold),
            "feature_config": asdict(config),
            "feature_names": feature_names(config),
            "metrics": metrics,
        },
        output_dir / "models/boldness_svm.joblib",
    )
    write_markdown_report(output_dir / "metrics/report.md", metrics)

    print(json.dumps(metrics, indent=2))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--font-root", default=str(DEFAULT_FONT_ROOT))
    parser.add_argument("--train-samples", type=int, default=20_000)
    parser.add_argument("--validation-samples", type=int, default=5_000)
    parser.add_argument("--test-samples", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--false-clear-tolerance", type=float, default=0.0025)
    parser.add_argument("--latency-rows", type=int, default=1_000)
    parser.add_argument("--sample-crop-limit", type=int, default=160)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--alpha", type=float, default=0.0001)
    parser.add_argument("--max-iter", type=int, default=10_000)
    parser.add_argument(
        "--classifier",
        choices=["sgd-svm", "linear-svc"],
        default="sgd-svm",
        help="Margin classifier. sgd-svm is much faster for the full HOG matrix.",
    )
    parser.add_argument(
        "--reuse-features",
        action="store_true",
        help="Load existing split .npz files instead of regenerating synthetic crops.",
    )
    return parser.parse_args()


def configure_thread_env(threads: int) -> None:
    """Limit BLAS/OpenMP thread counts for polite CPU execution."""

    value = str(max(1, threads))
    for name in [
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ]:
        os.environ.setdefault(name, value)
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


def build_model(args: argparse.Namespace) -> Pipeline:
    """Build the selected scaled margin-classifier pipeline."""

    if args.classifier == "linear-svc":
        classifier = LinearSVC(
            C=args.c,
            class_weight="balanced",
            dual=False,
            max_iter=args.max_iter,
            random_state=args.seed,
        )
    else:
        classifier = SGDClassifier(
            loss="hinge",
            penalty="l2",
            alpha=args.alpha,
            class_weight="balanced",
            max_iter=args.max_iter,
            tol=1e-4,
            random_state=args.seed,
            n_jobs=1,
        )
    return Pipeline([("scale", StandardScaler()), ("svm", classifier)])


def model_name(args: argparse.Namespace) -> str:
    """Return a reviewer-readable model name for reports."""

    if args.classifier == "linear-svc":
        return "StandardScaler + LinearSVC"
    return "StandardScaler + SGDClassifier hinge-loss linear SVM"


def discover_fonts(font_root: Path) -> list[FontRecord]:
    """Discover local font files and infer broad weight labels.

    Parameters
    ----------
    font_root:
        Directory containing system fonts.

    Returns
    -------
    list[FontRecord]
        Font records usable for synthetic rendering.
    """

    records: list[FontRecord] = []
    for path in sorted(font_root.rglob("*")):
        if path.suffix.lower() not in {".ttf", ".otf"}:
            continue
        weight = infer_weight(path)
        if weight is None:
            continue
        family = infer_family(path)
        records.append(FontRecord(str(path), family, weight))
    if len(records) < 12:
        raise RuntimeError(f"Not enough usable fonts found under {font_root}")
    return records


def infer_weight(path: Path) -> str | None:
    """Infer a coarse weight class from a font filename."""

    name = normalize_token(path.stem)
    tokens = set(re.split(r"[-_\s]+", name))
    joined = name.replace("-", "").replace("_", "")
    if tokens & WEIGHT_BOLD or any(token.replace("-", "") in joined for token in WEIGHT_BOLD):
        return "bold"
    if tokens & WEIGHT_BORDERLINE or any(
        token.replace("-", "") in joined for token in WEIGHT_BORDERLINE
    ):
        return "borderline"
    if tokens & WEIGHT_NON_BOLD or any(
        token.replace("-", "") in joined for token in WEIGHT_NON_BOLD
    ):
        return "regular"
    return None


def infer_family(path: Path) -> str:
    """Infer a font-family key from path and filename."""

    stem = normalize_token(path.stem)
    for token in sorted(WEIGHT_BOLD | WEIGHT_BORDERLINE | WEIGHT_NON_BOLD, key=len, reverse=True):
        stem = stem.replace(token.replace("-", ""), "")
        stem = stem.replace(token, "")
    stem = re.sub(r"[-_\s]+", "-", stem).strip("-")
    parent = normalize_token(path.parent.name)
    return f"{parent}:{stem or normalize_token(path.stem)}"


def normalize_token(value: str) -> str:
    """Normalize a filename/family token for grouping."""

    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def split_fonts(records: Sequence[FontRecord], *, seed: int) -> dict[str, list[FontRecord]]:
    """Split font families into train/validation/test groups."""

    by_family: dict[str, list[FontRecord]] = {}
    for record in records:
        by_family.setdefault(record.family, []).append(record)

    usable_families = [
        family
        for family, family_records in by_family.items()
        if {record.weight for record in family_records} & {"bold"}
        and {record.weight for record in family_records} & {"regular", "borderline"}
    ]
    if len(usable_families) < 6:
        usable_families = list(by_family)

    rng = random.Random(seed)
    rng.shuffle(usable_families)
    train_cut = max(1, int(len(usable_families) * 0.70))
    validation_cut = max(train_cut + 1, int(len(usable_families) * 0.85))
    groups = {
        "train": usable_families[:train_cut],
        "validation": usable_families[train_cut:validation_cut],
        "test": usable_families[validation_cut:],
    }
    if not groups["test"]:
        groups["test"] = groups["validation"][-1:]
        groups["validation"] = groups["validation"][:-1] or groups["train"][-1:]

    return {
        split: [record for family in families for record in by_family[family]]
        for split, families in groups.items()
    }


def write_font_splits(splits: dict[str, list[FontRecord]], path: Path) -> None:
    """Write font split provenance."""

    payload = {
        split: {
            "font_count": len(records),
            "families": sorted({record.family for record in records}),
            "weights": sorted({record.weight for record in records}),
            "fonts": [asdict(record) for record in records],
        }
        for split, records in splits.items()
    }
    write_json(path, payload)


def generate_split(
    *,
    split: str,
    count: int,
    fonts: Sequence[FontRecord],
    output_dir: Path,
    config: FeatureConfig,
    seed: int,
    sample_crop_limit: int,
) -> tuple[np.ndarray, np.ndarray, list[SampleMeta]]:
    """Generate synthetic crops and feature rows for one split."""

    rng = random.Random(f"{seed}:{split}")
    split_seed_offsets = {"train": 101, "validation": 202, "test": 303}
    np_rng = np.random.default_rng(seed + split_seed_offsets.get(split, 404))
    features: list[np.ndarray] = []
    labels: list[int] = []
    metadata: list[SampleMeta] = []

    pools = {
        "bold": [record for record in fonts if record.weight == "bold"],
        "regular": [record for record in fonts if record.weight == "regular"],
        "borderline": [record for record in fonts if record.weight == "borderline"],
    }
    if not pools["bold"] or not (pools["regular"] or pools["borderline"]):
        raise RuntimeError(f"Font split {split!r} does not have usable bold/non-bold pools.")
    if not pools["regular"]:
        pools["regular"] = pools["borderline"]
    if not pools["borderline"]:
        pools["borderline"] = pools["regular"]

    sample_dir = output_dir / "sample_crops" / split
    sample_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(count):
        label, sublabel, record = choose_sample_spec(rng, pools)
        recipe = choose_recipe(rng, split, sublabel)
        font_size = rng.randint(18, 42)
        crop = render_crop(
            record,
            font_size=font_size,
            recipe=recipe,
            rng=rng,
            np_rng=np_rng,
            sublabel=sublabel,
        )
        vector = extract_feature_vector(crop, config)
        sample_id = f"{split}_{idx:06d}"
        saved_crop = ""
        if idx < sample_crop_limit:
            saved_path = sample_dir / f"{sample_id}_{sublabel}.png"
            cv2.imwrite(str(saved_path), crop)
            saved_crop = str(saved_path.relative_to(output_dir))
        features.append(vector)
        labels.append(label)
        metadata.append(
            SampleMeta(
                split=split,
                sample_id=sample_id,
                label=label,
                sublabel=sublabel,
                font_path=record.path,
                font_family=record.family,
                font_weight=record.weight,
                distortion_recipe=recipe,
                font_size=font_size,
                saved_crop=saved_crop,
            )
        )

    return np.vstack(features).astype(np.float32), np.array(labels, dtype=np.int8), metadata


def choose_sample_spec(
    rng: random.Random,
    pools: dict[str, list[FontRecord]],
) -> tuple[int, str, FontRecord]:
    """Choose label class, semantic sublabel, and font record."""

    draw = rng.random()
    if draw < 0.45:
        return 1, "acceptable_bold", rng.choice(pools["bold"])
    if draw < 0.78:
        return 0, "regular_non_bold", rng.choice(pools["regular"])
    if draw < 0.90:
        return 0, "medium_or_borderline", rng.choice(pools["borderline"])
    pool = pools["bold"] + pools["regular"] + pools["borderline"]
    return 0, "degraded_uncertain", rng.choice(pool)


def choose_recipe(rng: random.Random, split: str, sublabel: str) -> str:
    """Choose distortion recipe with held-out split-specific emphasis."""

    mild = ["clean", "low_contrast", "jpeg", "blur_noise"]
    validation = ["rotate_shear", "mild_warp", "threshold_artifact"]
    test = ["hard_blur", "hard_warp", "glare_compression", "threshold_artifact"]
    if sublabel == "degraded_uncertain":
        return rng.choice(test)
    if sublabel == "acceptable_bold":
        if split == "train":
            return rng.choice(mild + ["rotate_shear"])
        if split == "validation":
            return rng.choice(mild + validation)
        return rng.choice(mild + validation + ["mild_warp"])
    if split == "train":
        return rng.choice(mild + ["rotate_shear"])
    if split == "validation":
        return rng.choice(validation + mild)
    return rng.choice(test + validation)


def render_crop(
    record: FontRecord,
    *,
    font_size: int,
    recipe: str,
    rng: random.Random,
    np_rng: np.random.Generator,
    sublabel: str,
) -> np.ndarray:
    """Render and augment one synthetic typography crop."""

    font = ImageFont.truetype(record.path, font_size)
    padding_x = rng.randint(8, 28)
    padding_y = rng.randint(8, 18)
    dummy = Image.new("L", (10, 10), 255)
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), TEXT, font=font)
    width = bbox[2] - bbox[0] + padding_x * 2
    height = bbox[3] - bbox[1] + padding_y * 2
    background = rng.randint(225, 255)
    text_value = rng.randint(0, 35)
    image = Image.new("L", (width, height), color=background)
    draw = ImageDraw.Draw(image)
    draw.text((padding_x, padding_y - bbox[1]), TEXT, font=font, fill=text_value)

    if recipe in {"low_contrast", "glare_compression"}:
        image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.45, 0.80))
    if recipe in {"blur_noise", "hard_blur", "degraded_uncertain"} or sublabel == "degraded_uncertain":
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.4, 1.6)))

    arr = np.array(image, dtype=np.uint8)
    arr = apply_geometric_distortion(arr, recipe, rng)
    arr = apply_photometric_distortion(arr, recipe, rng, np_rng)
    return arr


def apply_geometric_distortion(
    image: np.ndarray,
    recipe: str,
    rng: random.Random,
) -> np.ndarray:
    """Apply rotation, shear, or mild warp."""

    h, w = image.shape[:2]
    if recipe in {"rotate_shear", "hard_warp", "mild_warp", "glare_compression"}:
        angle = rng.uniform(-7, 7) if recipe != "hard_warp" else rng.uniform(-11, 11)
        shear = rng.uniform(-0.08, 0.08)
        center = (w / 2.0, h / 2.0)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        matrix[0, 1] += shear
        image = cv2.warpAffine(
            image,
            matrix,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )
    if recipe in {"mild_warp", "hard_warp"}:
        image = sinusoidal_warp(image, amplitude=2.0 if recipe == "mild_warp" else 4.0)
    return image


def sinusoidal_warp(image: np.ndarray, *, amplitude: float) -> np.ndarray:
    """Apply a mild synthetic curve-like warp."""

    h, w = image.shape[:2]
    ys, xs = np.indices((h, w), dtype=np.float32)
    offset = amplitude * np.sin(np.linspace(0, np.pi * 2, w, dtype=np.float32))
    map_y = ys + offset[np.newaxis, :]
    map_x = xs
    return cv2.remap(
        image,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def apply_photometric_distortion(
    image: np.ndarray,
    recipe: str,
    rng: random.Random,
    np_rng: np.random.Generator,
) -> np.ndarray:
    """Apply noise, compression, thresholding, and glare-like artifacts."""

    arr = image.astype(np.float32)
    if recipe in {"blur_noise", "hard_blur", "hard_warp", "glare_compression"}:
        noise = np_rng.normal(0, rng.uniform(4, 18), arr.shape).astype(np.float32)
        arr = np.clip(arr + noise, 0, 255)
    if recipe in {"threshold_artifact", "hard_warp"}:
        threshold = rng.randint(105, 175)
        _, arr_uint = cv2.threshold(arr.astype(np.uint8), threshold, 255, cv2.THRESH_BINARY)
        arr = arr_uint.astype(np.float32)
    if recipe in {"jpeg", "glare_compression"}:
        arr_uint = arr.astype(np.uint8)
        ok, encoded = cv2.imencode(".jpg", arr_uint, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(35, 82)])
        if ok:
            arr = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE).astype(np.float32)
    if recipe == "glare_compression":
        h, w = arr.shape[:2]
        x0 = rng.randint(0, max(1, w - 1))
        cv2.circle(arr, (x0, rng.randint(0, max(1, h - 1))), rng.randint(8, 24), 245, -1)
    return np.clip(arr, 0, 255).astype(np.uint8)


def save_split_artifacts(
    split: str,
    features: np.ndarray,
    labels: np.ndarray,
    metadata: Sequence[SampleMeta],
    output_dir: Path,
    config: FeatureConfig,
) -> None:
    """Persist features, labels, metadata, and feature names for one split."""

    np.savez_compressed(
        output_dir / f"features/{split}.npz",
        features=features,
        labels=labels,
    )
    write_json(output_dir / "manifests/feature_names.json", feature_names(config))
    with (output_dir / f"manifests/{split}_manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(metadata[0]).keys()))
        writer.writeheader()
        for row in metadata:
            writer.writerow(asdict(row))


def tune_threshold(
    y_true: np.ndarray,
    scores: np.ndarray,
    *,
    false_clear_tolerance: float,
) -> tuple[float, dict[str, float | int]]:
    """Choose a decision threshold on validation scores.

    The threshold maximizes F1 among candidates whose false-clear rate is at or
    below the configured tolerance. This reflects the government-safety posture.
    """

    candidate_thresholds = np.unique(np.percentile(scores, np.linspace(0, 100, 501)))
    candidate_thresholds = np.concatenate(
        [[scores.max() + 1e-6], candidate_thresholds, [scores.min() - 1e-6]]
    )
    best_threshold = float(scores.max() + 1e-6)
    best_metrics = compute_metrics(y_true, scores >= best_threshold)
    for threshold in candidate_thresholds:
        metrics = compute_metrics(y_true, scores >= threshold)
        if metrics["false_clear_rate"] > false_clear_tolerance:
            continue
        if metrics["f1"] > best_metrics["f1"]:
            best_threshold = float(threshold)
            best_metrics = metrics
    return best_threshold, best_metrics


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int]:
    """Compute binary classification and safety metrics."""

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    specificity = tn / max(tn + fp, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    return {
        "accuracy": float((tp + tn) / max(tp + tn + fp + fn, 1)),
        "precision": float(precision),
        "recall": float(recall),
        "specificity": float(specificity),
        "f1": float(f1),
        "false_clear_rate": float(fp / max(fp + tn, 1)),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "examples": int(tp + tn + fp + fn),
    }


def measure_latency(
    model: Pipeline,
    features: np.ndarray,
    threshold: float,
    rows: int,
) -> dict[str, float | int]:
    """Measure CPU prediction latency for feature rows."""

    count = min(rows, len(features))
    sample = features[:count]
    times: list[float] = []
    for row in sample:
        start = time.perf_counter()
        score = model.decision_function(row.reshape(1, -1))[0]
        _ = score >= threshold
        times.append((time.perf_counter() - start) * 1000)
    return {
        "rows": int(count),
        "mean_ms_per_crop": float(np.mean(times)) if times else 0.0,
        "median_ms_per_crop": float(np.median(times)) if times else 0.0,
        "p95_ms_per_crop": float(np.percentile(times, 95)) if times else 0.0,
        "max_ms_per_crop": float(np.max(times)) if times else 0.0,
    }


def write_confusion_csv(path: Path, metrics: dict[str, float | int]) -> None:
    """Write a two-by-two confusion matrix in CSV form."""

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["actual", "predicted", "count"])
        writer.writerow(["not_acceptable", "not_acceptable", metrics["tn"]])
        writer.writerow(["not_acceptable", "acceptable_bold", metrics["fp"]])
        writer.writerow(["acceptable_bold", "not_acceptable", metrics["fn"]])
        writer.writerow(["acceptable_bold", "acceptable_bold", metrics["tp"]])


def write_markdown_report(path: Path, metrics: dict) -> None:
    """Write a compact Markdown report for quick copy into docs."""

    test = metrics["test"]
    latency = metrics["latency"]
    content = f"""# Typography Preflight SVM Report

Synthetic OpenCV/SVM classifier for the `GOVERNMENT WARNING:` boldness preflight.

## Data

| Split | Crops |
|---|---:|
| Train | {metrics['counts']['train']:,} |
| Validation | {metrics['counts']['validation']:,} |
| Test | {metrics['counts']['test']:,} |

Font families and distortion recipes are held out across splits.

## Test Metrics

| Metric | Value |
|---|---:|
| Accuracy | {test['accuracy']:.4f} |
| Precision | {test['precision']:.4f} |
| Recall | {test['recall']:.4f} |
| Specificity | {test['specificity']:.4f} |
| F1 | {test['f1']:.4f} |
| False-clear rate | {test['false_clear_rate']:.4f} |

## Confusion Counts

| TP | TN | FP | FN | Examples |
|---:|---:|---:|---:|---:|
| {test['tp']} | {test['tn']} | {test['fp']} | {test['fn']} | {test['examples']} |

## Latency

| Metric | Value |
|---|---:|
| Mean / crop | {latency['mean_ms_per_crop']:.4f} ms |
| Median / crop | {latency['median_ms_per_crop']:.4f} ms |
| p95 / crop | {latency['p95_ms_per_crop']:.4f} ms |
| Max / crop | {latency['max_ms_per_crop']:.4f} ms |

Primary safety metric: false clear, meaning a non-bold/borderline/degraded
heading classified as acceptable bold.
"""
    path.write_text(content)


def write_json(path: Path, payload: object) -> None:
    """Write JSON with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
