"""Smoke-test typography classifiers on real approved COLA label images.

This script answers a narrow MVP question:

```
Can cached OCR find a GOVERNMENT WARNING heading in real approved COLA label
images, crop that region, and run the trained typography classifiers quickly?
```

It does not estimate false-clear safety because approved COLA records are
positive public examples. Synthetic negatives remain necessary for false-clear
measurement.
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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
from PIL import Image

from experiments.typography_preflight.compare_extended_models import StrictVetoEnsemble
from experiments.typography_preflight.compare_large_ensemble_models import PositiveRejectWrapper, StackerPipeline
from experiments.typography_preflight.features import FeatureConfig, extract_feature_vector, limit_cv2_threads


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OCR_RUN = ROOT / "data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16"
DEFAULT_MODEL_DIR = ROOT / "data/work/typography-preflight/model-comparison-large-geometry-v1/models"
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/real-cola-smoke-v1"
TASKS = {
    "visual_font_decision_label": {
        "plain_name": "Boldness classifier",
        "positive": "clearly_bold",
        "review": "needs_review_unclear",
    },
    "header_decision_label": {
        "plain_name": "Warning text classifier",
        "positive": "correct",
        "review": "needs_review_unclear",
    },
}
MODEL_NAMES = (
    "strict_veto_ensemble",
    "calibrated_logistic_regression_stacker",
    "lightgbm_reject_threshold",
    "xgboost_reject_threshold",
    "catboost_stacker",
)
MODEL_LABELS = {
    "strict_veto_ensemble": "Strict-veto ensemble",
    "calibrated_logistic_regression_stacker": "Logistic stacker",
    "lightgbm_reject_threshold": "LightGBM reject",
    "xgboost_reject_threshold": "XGBoost reject",
    "catboost_stacker": "CatBoost stacker",
}
CLASS_LABELS = {
    "clearly_bold": "Bold",
    "clearly_not_bold": "Not bold",
    "correct": "Correct text",
    "incorrect": "Incorrect text",
    "needs_review_unclear": "Needs review / cannot tell",
}


@dataclass(frozen=True)
class ImageRecord:
    """One image from the OCR conveyor manifest."""

    split: str
    ttb_id: str
    image_path: str


@dataclass(frozen=True)
class OcrRecord:
    """Cached OCR output row for one image/engine pair."""

    engine: str
    image_path: str
    total_ms: float
    avg_confidence: float | None
    ocr_json_path: str


@dataclass(frozen=True)
class HeadingCrop:
    """A warning-heading crop found in one real label image."""

    ttb_id: str
    image_path: str
    engine: str
    crop_path: str
    matched_text: str
    match_score: float
    ocr_confidence: float | None
    crop_ms: float


def main() -> None:
    """Run the real-COLA typography smoke test."""

    patch_pickle_main_namespace()
    args = parse_args()
    limit_cv2_threads()
    warnings.filterwarnings("ignore", message="X does not have valid feature names.*")
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("crops", "metrics"):
        (output_dir / name).mkdir(parents=True, exist_ok=True)

    images_by_app = load_image_manifest(args.ocr_run / "manifest/images.csv")
    selected_apps = list(images_by_app)[: args.app_limit]
    selected_images = [record for app in selected_apps for record in images_by_app[app]]
    ocr_index = load_ocr_index(args.ocr_run, set(args.engines))
    crops = find_heading_crops(selected_images, ocr_index, output_dir, args)

    models = load_models(args.model_dir)
    feature_config = FeatureConfig()
    classification_rows = classify_crops(crops, models, feature_config, output_dir)
    app_rows = summarize_app_decisions(selected_apps, classification_rows)
    summary = build_summary(
        selected_apps=selected_apps,
        selected_images=selected_images,
        ocr_index=ocr_index,
        crops=crops,
        classification_rows=classification_rows,
        app_rows=app_rows,
        args=args,
    )

    write_csv(output_dir / "metrics/heading_crops.csv", [asdict(crop) for crop in crops])
    write_csv(output_dir / "metrics/classification_rows.csv", classification_rows)
    write_csv(output_dir / "metrics/application_decisions.csv", app_rows)
    write_json(output_dir / "metrics/summary.json", summary)
    write_markdown(output_dir / "metrics/report.md", summary)
    print(json.dumps(summary, indent=2))


def patch_pickle_main_namespace() -> None:
    """Expose classes needed by joblib models saved from ``__main__``."""

    main_module = sys.modules["__main__"]
    setattr(main_module, "StackerPipeline", StackerPipeline)
    setattr(main_module, "PositiveRejectWrapper", PositiveRejectWrapper)
    setattr(main_module, "StrictVetoEnsemble", StrictVetoEnsemble)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr-run", type=Path, default=DEFAULT_OCR_RUN)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--app-limit", type=int, default=100)
    parser.add_argument("--engines", nargs="+", default=["doctr", "paddleocr", "openocr"])
    parser.add_argument("--crop-padding-x", type=float, default=0.30)
    parser.add_argument("--crop-padding-top", type=float, default=0.20)
    parser.add_argument("--crop-padding-bottom", type=float, default=0.05)
    parser.add_argument("--heading-width-factor", type=float, default=1.08)
    parser.add_argument("--min-heading-score", type=float, default=0.72)
    return parser.parse_args()


def load_image_manifest(path: Path) -> dict[str, list[ImageRecord]]:
    """Load valid image rows from the OCR conveyor image manifest."""

    by_app: dict[str, list[ImageRecord]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("preflight_status") != "valid":
                continue
            record = ImageRecord(
                split=row["split"],
                ttb_id=row["ttb_id"],
                image_path=row["image_path"],
            )
            by_app[record.ttb_id].append(record)
    return dict(by_app)


def load_ocr_index(ocr_run: Path, engines: set[str]) -> dict[tuple[str, str], OcrRecord]:
    """Index cached OCR rows by ``(engine, image_path)``."""

    index: dict[tuple[str, str], OcrRecord] = {}
    for rows_path in sorted((ocr_run / "runs").glob("*/rows.csv")):
        with rows_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") != "ok" or row.get("engine") not in engines:
                    continue
                image_path = row["image_path"]
                engine = row["engine"]
                index[(engine, image_path)] = OcrRecord(
                    engine=engine,
                    image_path=image_path,
                    total_ms=float(row.get("total_ms") or 0),
                    avg_confidence=parse_optional_float(row.get("avg_confidence")),
                    ocr_json_path=row["ocr_json_path"],
                )
    return index


def find_heading_crops(
    images: list[ImageRecord],
    ocr_index: dict[tuple[str, str], OcrRecord],
    output_dir: Path,
    args: argparse.Namespace,
) -> list[HeadingCrop]:
    """Find and crop warning-heading candidates from cached OCR boxes."""

    crops: list[HeadingCrop] = []
    for record in images:
        for engine in args.engines:
            ocr = ocr_index.get((engine, record.image_path))
            if ocr is None:
                continue
            started = time.perf_counter()
            candidate = load_best_heading_candidate(Path(ocr.ocr_json_path), min_score=args.min_heading_score)
            if candidate is None:
                continue
            image_path = ROOT / record.image_path
            image = Image.open(image_path).convert("L")
            crop = crop_candidate_heading(
                image,
                candidate["bbox"],
                candidate["text"],
                padding_x_factor=args.crop_padding_x,
                padding_top_factor=args.crop_padding_top,
                padding_bottom_factor=args.crop_padding_bottom,
                heading_width_factor=args.heading_width_factor,
            )
            crop_rel = Path("crops") / record.ttb_id / f"{engine}__{Path(record.image_path).stem}.png"
            crop_abs = output_dir / crop_rel
            crop_abs.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_abs)
            crops.append(
                HeadingCrop(
                    ttb_id=record.ttb_id,
                    image_path=record.image_path,
                    engine=engine,
                    crop_path=str(crop_abs.relative_to(output_dir)),
                    matched_text=candidate["text"],
                    match_score=float(candidate["score"]),
                    ocr_confidence=candidate["confidence"],
                    crop_ms=(time.perf_counter() - started) * 1000,
                )
            )
    return crops


def load_best_heading_candidate(path: Path, *, min_score: float) -> dict[str, Any] | None:
    """Return the best OCR block that appears to contain the warning heading."""

    data = json.loads(path.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = []
    for block in data.get("blocks", []):
        text = str(block.get("text") or "")
        score = heading_score(text)
        if score < min_score:
            continue
        candidates.append(
            {
                "text": text,
                "score": score,
                "confidence": parse_optional_float(block.get("confidence")),
                "bbox": block.get("bbox"),
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["score"], item["confidence"] or 0.0))


def heading_score(text: str) -> float:
    """Score whether OCR text resembles ``GOVERNMENT WARNING``."""

    normalized = "".join(ch for ch in text.upper() if ch.isalpha())
    target = "GOVERNMENTWARNING"
    if target in normalized:
        return 1.0
    if "GOVERNMENT" in normalized and "WARNING" in normalized:
        return 0.95
    return sequence_similarity(normalized[: len(target) + 8], target)


def sequence_similarity(left: str, right: str) -> float:
    """Small dependency-free similarity score for short OCR strings."""

    if not left or not right:
        return 0.0
    # A compact longest-common-subsequence ratio works well enough for heading
    # detection and avoids adding fuzzy-matching dependencies to this script.
    previous = [0] * (len(right) + 1)
    for lchar in left:
        current = [0]
        for idx, rchar in enumerate(right, start=1):
            current.append(previous[idx - 1] + 1 if lchar == rchar else max(previous[idx], current[-1]))
        previous = current
    return previous[-1] / max(len(right), 1)


def crop_candidate_heading(
    image: Image.Image,
    bbox: list[list[float]],
    text: str,
    *,
    padding_x_factor: float,
    padding_top_factor: float,
    padding_bottom_factor: float,
    heading_width_factor: float,
) -> Image.Image:
    """Crop only the visible ``GOVERNMENT WARNING:`` heading.

    Real OCR engines often return a single line containing both the bold
    heading and the regular-weight body text, e.g. ``GOVERNMENT WARNING:
    (1) ACCORDING...``. The typography model should never see that whole line
    when answering the boldness question. This cropper trims the OCR box to the
    heading prefix and uses asymmetric vertical padding so the next line of the
    warning paragraph does not contaminate the crop.
    """

    width, height = image.size
    x1, y1, x2, y2 = bbox_bounds(bbox, image_width=width, image_height=height)
    left = x1 * width
    top = y1 * height
    right = x2 * width
    bottom = y2 * height
    block_width = max(right - left, 1.0)
    block_height = max(bottom - top, 1.0)

    prefix_fraction = heading_prefix_fraction(text)
    if prefix_fraction < 0.98:
        right = left + block_width * min(1.0, prefix_fraction * heading_width_factor)

    pad_x = max(3.0, block_height * padding_x_factor)
    pad_top = max(2.0, block_height * padding_top_factor)
    pad_bottom = max(1.0, block_height * padding_bottom_factor)
    left = min(max(left, 0.0), float(width - 1))
    right = min(max(right, left + 1.0), float(width))
    top = min(max(top, 0.0), float(height - 1))
    bottom = min(max(bottom, top + 1.0), float(height))
    crop_box = (
        max(0, int(round(left - pad_x))),
        max(0, int(round(top - pad_top))),
        min(width, int(round(right + pad_x))),
        min(height, int(round(bottom + pad_bottom))),
    )
    return normalize_heading_crop(image.crop(crop_box))


def heading_prefix_fraction(text: str) -> float:
    """Estimate how much of an OCR line belongs to the warning heading."""

    if not text:
        return 1.0
    raw = text.strip()
    upper = raw.upper()
    colon_index = upper.find(":")
    if colon_index >= 0:
        prefix_end = colon_index + 1
        return min(1.0, max(0.05, prefix_end / max(len(raw), 1)))

    mapped: list[tuple[int, str]] = [(idx, ch) for idx, ch in enumerate(upper) if ch.isalpha()]
    normalized = "".join(ch for _, ch in mapped)
    target = "GOVERNMENTWARNING"
    found = normalized.find(target)
    if found >= 0:
        raw_end = mapped[min(len(mapped) - 1, found + len(target) - 1)][0] + 1
        return min(1.0, max(0.05, raw_end / max(len(raw), 1)))
    if len(normalized) > len(target):
        return min(1.0, max(0.05, len(target) / len(normalized)))
    return 1.0


def normalize_heading_crop(crop: Image.Image) -> Image.Image:
    """Normalize real crops toward black text on white, tightly framed."""

    gray = np.array(crop.convert("L"))
    if gray.size == 0:
        return crop
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    if float(np.median(border)) < 128.0:
        gray = 255 - gray
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    ys, xs = np.where(binary > 0)
    if len(xs) == 0 or len(ys) == 0:
        return Image.fromarray(gray)
    pad = 2
    x1 = max(0, int(xs.min()) - pad)
    x2 = min(gray.shape[1], int(xs.max()) + pad + 1)
    y1 = max(0, int(ys.min()) - pad)
    y2 = min(gray.shape[0], int(ys.max()) + pad + 1)
    return Image.fromarray(gray[y1:y2, x1:x2])


def bbox_bounds(
    bbox: list[list[float]],
    *,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """Return normalized min/max bounds for boxes or polygons."""

    points = [(float(point[0]), float(point[1])) for point in bbox if len(point) >= 2]
    if not points:
        return 0.0, 0.0, 1.0, 1.0
    if max(max(abs(x), abs(y)) for x, y in points) > 1.5:
        points = [(x / max(image_width, 1), y / max(image_height, 1)) for x, y in points]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys))


def load_models(model_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load typography classifiers from the large geometry comparison run."""

    models: dict[tuple[str, str], dict[str, Any]] = {}
    for task in TASKS:
        for model_name in MODEL_NAMES:
            path = model_dir / f"{task}__{model_name}.joblib"
            payload = joblib.load(path)
            models[(task, model_name)] = payload
    return models


def classify_crops(
    crops: list[HeadingCrop],
    models: dict[tuple[str, str], dict[str, Any]],
    feature_config: FeatureConfig,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Run all model policies against all real-COLA heading crops."""

    rows: list[dict[str, Any]] = []
    for crop in crops:
        crop_abs = output_dir / crop.crop_path
        gray = cv2.imread(str(crop_abs), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue
        feature_started = time.perf_counter()
        features = extract_feature_vector(gray, feature_config).reshape(1, -1)
        feature_ms = (time.perf_counter() - feature_started) * 1000
        for (task, model_name), payload in models.items():
            model = payload["model"]
            class_names = tuple(payload["class_names"])
            started = time.perf_counter()
            prediction = int(model.predict(features)[0])
            predict_ms = (time.perf_counter() - started) * 1000
            predicted_class = class_names[prediction]
            rows.append(
                {
                    "ttb_id": crop.ttb_id,
                    "image_path": crop.image_path,
                    "engine": crop.engine,
                    "crop_path": crop.crop_path,
                    "task": task,
                    "classifier": TASKS[task]["plain_name"],
                    "model": model_name,
                    "model_label": MODEL_LABELS[model_name],
                    "predicted_class": predicted_class,
                    "predicted_label": CLASS_LABELS.get(predicted_class, predicted_class),
                    "clears_expected_positive": str(predicted_class == TASKS[task]["positive"]).lower(),
                    "needs_review": str(predicted_class == TASKS[task]["review"]).lower(),
                    "feature_ms": round(feature_ms, 6),
                    "predict_ms": round(predict_ms, 6),
                    "total_classification_ms": round(feature_ms + predict_ms, 6),
                    "matched_text": crop.matched_text,
                    "match_score": crop.match_score,
                    "ocr_confidence": crop.ocr_confidence,
                }
            )
    return rows


def summarize_app_decisions(selected_apps: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse crop-level predictions into simple app-level smoke decisions."""

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["ttb_id"], row["task"], row["model"])].append(row)

    app_rows: list[dict[str, Any]] = []
    for app in selected_apps:
        for task in TASKS:
            for model_name in MODEL_NAMES:
                candidates = grouped.get((app, task, model_name), [])
                if not candidates:
                    decision = "no_heading_found"
                elif any(row["clears_expected_positive"] == "true" for row in candidates):
                    decision = "cleared_expected_positive"
                elif any(row["needs_review"] == "true" for row in candidates):
                    decision = "needs_review"
                else:
                    decision = "flagged_negative"
                app_rows.append(
                    {
                        "ttb_id": app,
                        "task": task,
                        "classifier": TASKS[task]["plain_name"],
                        "model": model_name,
                        "model_label": MODEL_LABELS[model_name],
                        "decision": decision,
                        "crop_count": len(candidates),
                    }
                )
    return app_rows


def build_summary(
    *,
    selected_apps: list[str],
    selected_images: list[ImageRecord],
    ocr_index: dict[tuple[str, str], OcrRecord],
    crops: list[HeadingCrop],
    classification_rows: list[dict[str, Any]],
    app_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Build the JSON summary."""

    app_with_crop = {crop.ttb_id for crop in crops}
    crops_by_engine = Counter(crop.engine for crop in crops)
    ocr_by_engine = Counter(engine for engine, _ in ocr_index)
    model_summary: dict[str, dict[str, Any]] = {}
    for task in TASKS:
        for model_name in MODEL_NAMES:
            key = f"{TASKS[task]['plain_name']} / {MODEL_LABELS[model_name]}"
            subset = [row for row in classification_rows if row["task"] == task and row["model"] == model_name]
            decisions = [row for row in app_rows if row["task"] == task and row["model"] == model_name]
            model_summary[key] = {
                "crop_predictions": len(subset),
                "crop_prediction_counts": dict(Counter(row["predicted_label"] for row in subset)),
                "crop_expected_positive_clear_rate": rate(
                    sum(row["clears_expected_positive"] == "true" for row in subset),
                    len(subset),
                ),
                "crop_needs_review_rate": rate(sum(row["needs_review"] == "true" for row in subset), len(subset)),
                "app_decision_counts": dict(Counter(row["decision"] for row in decisions)),
                "app_expected_positive_clear_rate": rate(
                    sum(row["decision"] == "cleared_expected_positive" for row in decisions),
                    len(decisions),
                ),
                "latency_ms": summarize_numbers(float(row["total_classification_ms"]) for row in subset),
            }
    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "Real approved COLA smoke test for warning-heading crop location and typography classifier latency/pass-through.",
        "important_limitations": [
            "Approved public COLA records are positive examples; this run cannot estimate false-clear safety.",
            "Synthetic negatives remain the source for false-clear measurement.",
            "A no-heading result often means OCR/crop isolation failed, not necessarily that the approved label lacks a warning.",
        ],
        "inputs": {
            "ocr_run": str(args.ocr_run),
            "model_dir": str(args.model_dir),
            "app_limit": args.app_limit,
            "engines": list(args.engines),
        },
        "counts": {
            "applications_selected": len(selected_apps),
            "images_selected": len(selected_images),
            "cached_ocr_rows_loaded": len(ocr_index),
            "heading_crops_found": len(crops),
            "applications_with_heading_crop": len(app_with_crop),
            "application_heading_crop_rate": rate(len(app_with_crop), len(selected_apps)),
            "crops_by_engine": dict(crops_by_engine),
            "cached_ocr_rows_by_engine": dict(ocr_by_engine),
        },
        "models": model_summary,
    }


def summarize_numbers(values: Any) -> dict[str, float | int | None]:
    """Summarize numeric values."""

    numbers = sorted(float(value) for value in values)
    if not numbers:
        return {"count": 0, "mean": None, "median": None, "p95": None, "max": None}
    p95_index = min(len(numbers) - 1, int(round((len(numbers) - 1) * 0.95)))
    return {
        "count": len(numbers),
        "mean": round(statistics.fmean(numbers), 6),
        "median": round(statistics.median(numbers), 6),
        "p95": round(numbers[p95_index], 6),
        "max": round(max(numbers), 6),
    }


def parse_optional_float(value: Any) -> float | None:
    """Parse optional numeric values from CSV/JSON."""

    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rate(numerator: int, denominator: int) -> float | None:
    """Return a rounded rate or ``None`` when denominator is zero."""

    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write CSV rows if available."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    """Write a compact Markdown report for review."""

    lines = [
        "# Real COLA Typography Smoke Test",
        "",
        "Approved public COLA records are positive examples. This smoke test measures heading-location success, pass-through behavior, and classifier latency. It does not measure false clears.",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary["counts"].items():
        lines.append(f"| {key} | {json.dumps(value)} |")
    lines.extend(["", "## Model Summary", "", "| Classifier / Model | App clear rate | Crop clear rate | Crop review rate | Mean ms | P95 ms |"])
    lines.append("|---|---:|---:|---:|---:|---:|")
    for key, value in summary["models"].items():
        latency = value["latency_ms"]
        lines.append(
            "| "
            + f"{key} | {value['app_expected_positive_clear_rate']} | {value['crop_expected_positive_clear_rate']} "
            + f"| {value['crop_needs_review_rate']} | {latency['mean']} | {latency['p95']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
