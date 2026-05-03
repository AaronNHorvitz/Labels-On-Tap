#!/usr/bin/env python
"""Benchmark an MMOCR FCENet detector plus ASTER recognizer stack.

FCENet is a text detector, not a recognizer. It predicts arbitrary-shaped text
contours using Fourier-domain signatures, then reconstructs polygons during
inference. To test whether that geometry helps this project, the benchmark
runs FCENet on each full label image, crops the detected polygon bounds, runs
ASTER recognition on those crops, and writes normalized OCR artifacts for the
same field-support scorer used by the other OCR experiments.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.schemas.ocr import OCRResult


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep"


@dataclass(frozen=True)
class FCENetAsterRow:
    """One FCENet plus ASTER benchmark row."""

    engine: str
    image_path: str
    status: str
    total_ms: int
    detector_ms: int
    recognizer_ms: int
    avg_confidence: float
    block_count: int
    text_chars: int
    detected_count: int
    crop_count: int
    detector_model: str
    recognizer_model: str
    image_source_run: str
    error: str = ""
    ocr_json_path: str = ""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-run-dir",
        type=Path,
        required=True,
        help="Existing OCR benchmark run directory whose image list should be reused.",
    )
    parser.add_argument(
        "--image-engine",
        default="openocr",
        help="Engine name from the source rows.csv used only to choose the same images.",
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--detector-model", default="FCENet")
    parser.add_argument("--recognizer-model", default="ASTER")
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--max-crops-per-image", type=int, default=128)
    parser.add_argument("--padding", type=int, default=2)
    parser.add_argument("--run-name", default="fcenet-aster-smoke-30")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def relative_path(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def safe_artifact_stem(image_path: Path) -> str:
    """Return a filesystem-safe artifact stem for an image path."""

    relative = relative_path(image_path)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", relative).strip("._")


def load_image_rows(image_run_dir: Path, image_engine: str, limit: int) -> list[dict]:
    """Load image rows from an existing benchmark run for sample parity."""

    rows_path = image_run_dir / "rows.csv"
    rows: list[dict] = []
    with rows_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("engine") != image_engine or row.get("status") != "ok":
                continue
            rows.append(row)
    return rows[:limit]


def flat_polygon_to_points(polygon: object) -> list[list[float]]:
    """Convert MMOCR flat polygon coordinates into ``[[x, y], ...]`` points."""

    if not isinstance(polygon, list):
        return []
    values: list[float] = []
    for value in polygon:
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(values) < 4:
        return []
    return [[values[index], values[index + 1]] for index in range(0, len(values) - 1, 2)]


def bbox_bounds(points: list[list[float]], image_size: tuple[int, int], padding: int) -> tuple[int, int, int, int] | None:
    """Convert polygon points into a padded rectangular crop."""

    if not points:
        return None
    width, height = image_size
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    left = max(0, int(min(x_values)) - padding)
    upper = max(0, int(min(y_values)) - padding)
    right = min(width, int(max(x_values)) + padding)
    lower = min(height, int(max(y_values)) + padding)
    if right <= left or lower <= upper:
        return None
    return left, upper, right, lower


class FCENetDetector:
    """Lazy wrapper around MMOCR's FCENet text detector."""

    def __init__(self, *, model: str, device: str) -> None:
        """Load FCENet on the requested device."""

        try:
            from mmocr.apis import TextDetInferencer
        except Exception as exc:  # pragma: no cover - optional experiment deps
            raise RuntimeError(f"MMOCR FCENet dependencies are unavailable: {exc}") from exc

        self.inferencer = TextDetInferencer(model=model, device=device)

    def detect(self, image_path: Path, min_score: float, max_crops: int) -> list[dict]:
        """Detect text polygons for one image path."""

        output = self.inferencer(str(image_path), return_vis=False)
        predictions = output.get("predictions", []) if isinstance(output, dict) else []
        if not predictions:
            return []
        first_prediction = predictions[0] if isinstance(predictions[0], dict) else {}
        polygons = first_prediction.get("polygons") or []
        scores = first_prediction.get("scores") or [1.0] * len(polygons)
        detections: list[dict] = []
        for polygon, score in zip(polygons, scores, strict=False):
            score_value = float(score or 0.0)
            if score_value < min_score:
                continue
            points = flat_polygon_to_points(polygon)
            if not points:
                continue
            detections.append({"points": points, "score": score_value})
        detections.sort(key=lambda item: item["score"], reverse=True)
        return detections[:max_crops]


class AsterRecognizer:
    """Lazy wrapper around MMOCR's ASTER text-recognition inferencer."""

    def __init__(self, *, model: str, device: str) -> None:
        """Load ASTER on the requested device."""

        try:
            from mmocr.apis import TextRecInferencer
        except Exception as exc:  # pragma: no cover - optional experiment deps
            raise RuntimeError(f"MMOCR ASTER dependencies are unavailable: {exc}") from exc

        self.inferencer = TextRecInferencer(model=model, device=device)

    def recognize(self, crop_paths: list[Path], batch_size: int) -> list[tuple[str, float]]:
        """Recognize text from crop file paths with ASTER."""

        if not crop_paths:
            return []
        path_strings = [str(path) for path in crop_paths]
        try:
            output = self.inferencer(path_strings, batch_size=batch_size, return_vis=False)
        except TypeError:
            output = self.inferencer(path_strings, return_vis=False)
        predictions = output.get("predictions", []) if isinstance(output, dict) else []
        results: list[tuple[str, float]] = []
        for prediction in predictions:
            if not isinstance(prediction, dict):
                results.append(("", 0.0))
                continue
            text = str(prediction.get("text") or "")
            score = prediction.get("scores", 0.0)
            if isinstance(score, list):
                confidence = float(sum(float(value) for value in score) / len(score)) if score else 0.0
            else:
                confidence = float(score or 0.0)
            results.append((text, confidence))
        return results


def write_ocr_json(output_dir: Path, image_path: Path, result: OCRResult) -> Path:
    """Write normalized OCR JSON for later field-support scoring."""

    ocr_dir = output_dir / "ocr" / "fcenet_aster"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    path = ocr_dir / f"{safe_artifact_stem(image_path)}.json"
    path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def summarize(rows: list[FCENetAsterRow]) -> dict:
    """Summarize FCENet plus ASTER benchmark rows."""

    ok_rows = [row for row in rows if row.status == "ok"]
    latencies = [row.total_ms for row in ok_rows]
    return {
        "fcenet_aster": {
            "image_count": len(rows),
            "ok_count": len(ok_rows),
            "error_count": len(rows) - len(ok_rows),
            "mean_ms": round(mean(latencies), 2) if latencies else None,
            "median_ms": round(median(latencies), 2) if latencies else None,
            "worst_ms": max(latencies) if latencies else None,
            "mean_detector_ms": round(mean(row.detector_ms for row in ok_rows), 2) if ok_rows else None,
            "mean_recognizer_ms": round(mean(row.recognizer_ms for row in ok_rows), 2) if ok_rows else None,
            "mean_confidence": round(mean(row.avg_confidence for row in ok_rows), 4) if ok_rows else None,
            "mean_detected_count": round(mean(row.detected_count for row in ok_rows), 2) if ok_rows else None,
            "mean_crop_count": round(mean(row.crop_count for row in ok_rows), 2) if ok_rows else None,
            "mean_block_count": round(mean(row.block_count for row in ok_rows), 2) if ok_rows else None,
            "mean_text_chars": round(mean(row.text_chars for row in ok_rows), 2) if ok_rows else None,
        }
    }


def main() -> None:
    """Run FCENet detection plus ASTER recognition."""

    args = parse_args()
    output_dir = args.output_dir / args.run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional experiment deps
        raise SystemExit(f"Pillow is required: {exc}") from exc

    detector = FCENetDetector(model=args.detector_model, device=args.device)
    recognizer = AsterRecognizer(model=args.recognizer_model, device=args.device)
    rows: list[FCENetAsterRow] = []

    image_rows = load_image_rows(args.image_run_dir, args.image_engine, args.limit)
    for index, row in enumerate(image_rows, start=1):
        image_path = REPO_ROOT / row["image_path"]
        print(f"[fcenet_aster] {index}/{len(image_rows)} {relative_path(image_path)}")
        started = perf_counter()
        detector_ms = 0
        recognizer_ms = 0
        try:
            image = Image.open(image_path).convert("RGB")
            detector_started = perf_counter()
            detections = detector.detect(image_path, args.min_score, args.max_crops_per_image)
            detector_ms = int((perf_counter() - detector_started) * 1000)

            crop_polygons = []
            with tempfile.TemporaryDirectory(prefix="fcenet-aster-crops-") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                crop_paths: list[Path] = []
                for crop_index, detection in enumerate(detections):
                    bounds = bbox_bounds(detection["points"], image.size, args.padding)
                    if bounds is None:
                        continue
                    crop_path = temp_dir / f"crop_{crop_index:03d}.png"
                    image.crop(bounds).save(crop_path)
                    crop_paths.append(crop_path)
                    crop_polygons.append(detection["points"])

                recognizer_started = perf_counter()
                recognized = recognizer.recognize(crop_paths, args.batch_size)
                recognizer_ms = int((perf_counter() - recognizer_started) * 1000)

            blocks = [
                {"text": text, "confidence": confidence, "bbox": polygon}
                for (text, confidence), polygon in zip(recognized, crop_polygons, strict=False)
                if text
            ]
            full_text = " ".join(block["text"] for block in blocks).strip()
            confidences = [float(block["confidence"]) for block in blocks]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            total_ms = int((perf_counter() - started) * 1000)
            result = OCRResult(
                filename=image_path.name,
                full_text=full_text,
                avg_confidence=avg_confidence,
                blocks=blocks,
                source="local MMOCR FCENet + ASTER",
                ocr_ms=total_ms,
                total_ms=total_ms,
            )
            ocr_json_path = write_ocr_json(output_dir, image_path, result)
            rows.append(
                FCENetAsterRow(
                    engine="fcenet_aster",
                    image_path=relative_path(image_path),
                    status="ok",
                    total_ms=total_ms,
                    detector_ms=detector_ms,
                    recognizer_ms=recognizer_ms,
                    avg_confidence=avg_confidence,
                    block_count=len(blocks),
                    text_chars=len(full_text),
                    detected_count=len(detections),
                    crop_count=len(crop_paths),
                    detector_model=args.detector_model,
                    recognizer_model=args.recognizer_model,
                    image_source_run=relative_path(args.image_run_dir),
                    ocr_json_path=relative_path(ocr_json_path),
                )
            )
        except Exception as exc:
            rows.append(
                FCENetAsterRow(
                    engine="fcenet_aster",
                    image_path=relative_path(image_path),
                    status="error",
                    total_ms=int((perf_counter() - started) * 1000),
                    detector_ms=detector_ms,
                    recognizer_ms=recognizer_ms,
                    avg_confidence=0.0,
                    block_count=0,
                    text_chars=0,
                    detected_count=0,
                    crop_count=0,
                    detector_model=args.detector_model,
                    recognizer_model=args.recognizer_model,
                    image_source_run=relative_path(args.image_run_dir),
                    error=str(exc),
                )
            )
            print(f"  error: {exc}")

    with (output_dir / "rows.csv").open("w", newline="", encoding="utf-8") as file:
        fieldnames = list(asdict(rows[0]).keys()) if rows else list(FCENetAsterRow.__dataclass_fields__)
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for output_row in rows:
            writer.writerow(asdict(output_row))

    summary = summarize(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote FCENet + ASTER benchmark outputs to {output_dir}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
