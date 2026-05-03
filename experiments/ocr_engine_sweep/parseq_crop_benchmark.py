#!/usr/bin/env python
"""Benchmark PARSeq recognition over detected OCR crops.

This experiment is intentionally separate from ``benchmark_ocr_engines.py``
because PARSeq is a scene-text recognizer, not a complete label-page OCR
pipeline by itself. The script takes text-region boxes from an existing OCR
run, crops those regions, runs PARSeq recognition on the crops, and writes the
same normalized OCR JSON/CSV artifacts used by the field-support scorer.

The resulting latency is recognition-stage latency plus crop preparation. It
does not include detector latency unless the chosen box-source run already
accounts for it separately.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
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
class ParseqCropRow:
    """One PARSeq crop-recognition benchmark row."""

    engine: str
    image_path: str
    status: str
    total_ms: int
    avg_confidence: float
    block_count: int
    text_chars: int
    crop_count: int
    decode_ar: bool
    refine_iters: int
    box_source_run: str
    error: str = ""
    ocr_json_path: str = ""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--box-run-dir",
        type=Path,
        required=True,
        help="Existing OCR benchmark run directory whose normalized boxes should be reused.",
    )
    parser.add_argument(
        "--box-engine",
        default="openocr",
        help="Engine name from the box-source rows.csv to use for boxes.",
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--decode-ar", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--refine-iters", type=int, default=1)
    parser.add_argument("--max-crops-per-image", type=int, default=96)
    parser.add_argument("--padding", type=int, default=2)
    parser.add_argument("--run-name", default="parseq-openocr-crops-smoke-30")
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


def load_box_rows(box_run_dir: Path, box_engine: str, limit: int) -> list[dict]:
    """Load benchmark row metadata for the selected box-source engine."""

    rows_path = box_run_dir / "rows.csv"
    rows: list[dict] = []
    with rows_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("engine") != box_engine or row.get("status") != "ok":
                continue
            rows.append(row)
    return rows[:limit]


def load_ocr_json(row: dict) -> dict:
    """Load the normalized OCR JSON artifact referenced by a benchmark row."""

    return json.loads((REPO_ROOT / row["ocr_json_path"]).read_text(encoding="utf-8"))


def bbox_bounds(points: object, image_size: tuple[int, int], padding: int) -> tuple[int, int, int, int] | None:
    """Convert a polygon/box-like value into a padded rectangular crop."""

    if not isinstance(points, list) or not points:
        return None

    coordinates: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, list) and len(point) >= 2:
            try:
                coordinates.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if not coordinates:
        return None

    width, height = image_size
    x_values = [point[0] for point in coordinates]
    y_values = [point[1] for point in coordinates]
    left = max(0, int(min(x_values)) - padding)
    upper = max(0, int(min(y_values)) - padding)
    right = min(width, int(max(x_values)) + padding)
    lower = min(height, int(max(y_values)) + padding)
    if right <= left or lower <= upper:
        return None
    return left, upper, right, lower


def confidence_from_token_probs(token_probs) -> float:
    """Return a single confidence score from PARSeq token probabilities."""

    try:
        values = token_probs.detach().cpu().tolist()
    except AttributeError:
        values = token_probs
    if isinstance(values, (int, float)):
        return float(values)
    if not values:
        return 0.0
    return float(sum(float(value) for value in values) / len(values))


class ParseqRecognizer:
    """Lazy wrapper around the PARSeq Torch Hub model."""

    def __init__(self, *, device: str, decode_ar: bool, refine_iters: int) -> None:
        """Load PARSeq and its image transform."""

        try:
            import torch
        except Exception as exc:  # pragma: no cover - optional experiment deps
            raise RuntimeError(f"PARSeq dependencies are unavailable: {exc}") from exc

        self.torch = torch
        self.device = torch.device(device)
        self.model = torch.hub.load(
            "baudm/parseq",
            "parseq",
            pretrained=True,
            trust_repo=True,
            decode_ar=decode_ar,
            refine_iters=refine_iters,
        ).eval()
        self.model.to(self.device)
        try:
            from strhub.data.module import SceneTextDataModule
        except Exception as exc:  # pragma: no cover - optional experiment deps
            raise RuntimeError(f"PARSeq transform dependency is unavailable: {exc}") from exc
        self.transform = SceneTextDataModule.get_transform(self.model.hparams.img_size)

    def recognize(self, crops, batch_size: int) -> list[tuple[str, float]]:
        """Recognize a list of PIL image crops with PARSeq."""

        outputs: list[tuple[str, float]] = []
        for start in range(0, len(crops), batch_size):
            batch_crops = crops[start : start + batch_size]
            tensors = [self.transform(crop.convert("RGB")) for crop in batch_crops]
            batch = self.torch.stack(tensors).to(self.device)
            with self.torch.inference_mode():
                logits = self.model(batch)
                predictions = logits.softmax(-1)
            labels, confidences = self.model.tokenizer.decode(predictions)
            outputs.extend(
                (label, confidence_from_token_probs(confidence))
                for label, confidence in zip(labels, confidences, strict=False)
            )
        return outputs


def write_ocr_json(output_dir: Path, image_path: Path, result: OCRResult) -> Path:
    """Write normalized OCR JSON for later field-support scoring."""

    ocr_dir = output_dir / "ocr" / "parseq_openocr_crops"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    path = ocr_dir / f"{safe_artifact_stem(image_path)}.json"
    path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def summarize(rows: list[ParseqCropRow]) -> dict:
    """Summarize PARSeq crop benchmark rows."""

    ok_rows = [row for row in rows if row.status == "ok"]
    latencies = [row.total_ms for row in ok_rows]
    return {
        "parseq_openocr_crops": {
            "image_count": len(rows),
            "ok_count": len(ok_rows),
            "error_count": len(rows) - len(ok_rows),
            "mean_ms": round(mean(latencies), 2) if latencies else None,
            "median_ms": round(median(latencies), 2) if latencies else None,
            "worst_ms": max(latencies) if latencies else None,
            "mean_confidence": round(mean(row.avg_confidence for row in ok_rows), 4) if ok_rows else None,
            "mean_block_count": round(mean(row.block_count for row in ok_rows), 2) if ok_rows else None,
            "mean_crop_count": round(mean(row.crop_count for row in ok_rows), 2) if ok_rows else None,
            "mean_text_chars": round(mean(row.text_chars for row in ok_rows), 2) if ok_rows else None,
        }
    }


def main() -> None:
    """Run PARSeq recognition over detected crop boxes."""

    args = parse_args()
    output_dir = args.output_dir / args.run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional experiment deps
        raise SystemExit(f"Pillow is required: {exc}") from exc

    recognizer = ParseqRecognizer(device=args.device, decode_ar=args.decode_ar, refine_iters=args.refine_iters)
    rows: list[ParseqCropRow] = []

    box_rows = load_box_rows(args.box_run_dir, args.box_engine, args.limit)
    for index, row in enumerate(box_rows, start=1):
        image_path = REPO_ROOT / row["image_path"]
        print(f"[parseq_openocr_crops] {index}/{len(box_rows)} {relative_path(image_path)}")
        started = perf_counter()
        try:
            source_payload = load_ocr_json(row)
            image = Image.open(image_path).convert("RGB")
            source_blocks = source_payload.get("blocks", [])[: args.max_crops_per_image]
            crops = []
            crop_boxes = []
            for block in source_blocks:
                bounds = bbox_bounds(block.get("bbox"), image.size, args.padding)
                if bounds is None:
                    continue
                crops.append(image.crop(bounds))
                crop_boxes.append(block.get("bbox"))

            recognized = recognizer.recognize(crops, args.batch_size) if crops else []
            blocks = [
                {"text": text, "confidence": confidence, "bbox": bbox}
                for (text, confidence), bbox in zip(recognized, crop_boxes, strict=False)
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
                source="local PARSeq over OpenOCR crops",
                ocr_ms=total_ms,
                total_ms=total_ms,
            )
            ocr_json_path = write_ocr_json(output_dir, image_path, result)
            rows.append(
                ParseqCropRow(
                    engine="parseq_openocr_crops",
                    image_path=relative_path(image_path),
                    status="ok",
                    total_ms=total_ms,
                    avg_confidence=avg_confidence,
                    block_count=len(blocks),
                    text_chars=len(full_text),
                    crop_count=len(crops),
                    decode_ar=args.decode_ar,
                    refine_iters=args.refine_iters,
                    box_source_run=relative_path(args.box_run_dir),
                    ocr_json_path=relative_path(ocr_json_path),
                )
            )
        except Exception as exc:
            rows.append(
                ParseqCropRow(
                    engine="parseq_openocr_crops",
                    image_path=relative_path(image_path),
                    status="error",
                    total_ms=int((perf_counter() - started) * 1000),
                    avg_confidence=0.0,
                    block_count=0,
                    text_chars=0,
                    crop_count=0,
                    decode_ar=args.decode_ar,
                    refine_iters=args.refine_iters,
                    box_source_run=relative_path(args.box_run_dir),
                    error=str(exc),
                )
            )
            print(f"  error: {exc}")

    with (output_dir / "rows.csv").open("w", newline="", encoding="utf-8") as file:
        fieldnames = list(asdict(rows[0]).keys()) if rows else list(ParseqCropRow.__dataclass_fields__)
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for output_row in rows:
            writer.writerow(asdict(output_row))

    summary = summarize(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote PARSeq crop benchmark outputs to {output_dir}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
