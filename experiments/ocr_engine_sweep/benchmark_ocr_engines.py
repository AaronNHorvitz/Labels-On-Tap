#!/usr/bin/env python
"""Run small local OCR-engine smoke benchmarks.

This script is intentionally outside the application runtime. It lets the
project compare alternate local OCR engines without changing the deployed
FastAPI app or production dependency set.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.schemas.ocr import OCRResult
from app.services.ocr.doctr_engine import DoctrOCREngine


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "ocr-engine-sweep"


class SmokeEngine(Protocol):
    """Minimal OCR engine protocol used by the smoke benchmark."""

    name: str

    def run(self, image_path: Path) -> OCRResult:
        """Return normalized OCR output for one image."""

        ...


@dataclass(frozen=True)
class SmokeRow:
    """One OCR smoke benchmark result row.

    Attributes
    ----------
    engine:
        Engine identifier used for this run.
    image_path:
        Path to the image relative to the repository root when possible.
    status:
        ``ok`` when OCR completed; otherwise ``error``.
    total_ms:
        Wall-clock runtime for the engine call.
    avg_confidence:
        Engine confidence normalized to ``0.0`` through ``1.0`` when available.
    block_count:
        Number of normalized OCR blocks returned.
    text_chars:
        Character length of the full OCR text.
    error:
        Error message for failed calls.
    ocr_json_path:
        Relative path to the normalized OCR JSON artifact when available.
    """

    engine: str
    image_path: str
    status: str
    total_ms: int
    avg_confidence: float
    block_count: int
    text_chars: int
    error: str = ""
    ocr_json_path: str = ""


class DoctrSmokeEngine:
    """Smoke wrapper around the app's local docTR adapter."""

    name = "doctr"

    def __init__(self) -> None:
        """Initialize the lazy-loading docTR adapter."""

        self._engine = DoctrOCREngine()

    def run(self, image_path: Path) -> OCRResult:
        """Run the app's docTR OCR adapter."""

        return self._engine.run(image_path)


class PaddleOCRSmokeEngine:
    """Experimental PaddleOCR wrapper with defensive result normalization.

    Notes
    -----
    PaddleOCR has changed constructor and output shapes across releases. This
    wrapper keeps the smoke benchmark tolerant so the first install attempt can
    tell us whether the engine is viable without touching app runtime code.
    """

    name = "paddleocr"

    def __init__(self) -> None:
        """Import and initialize PaddleOCR lazily."""

        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(f"PaddleOCR is not installed: {exc}") from exc

        initialization_attempts = (
            {"lang": "en", "use_angle_cls": True, "show_log": False},
            {"lang": "en", "use_angle_cls": True},
            {"lang": "en"},
        )
        last_error: Exception | None = None
        for kwargs in initialization_attempts:
            try:
                self._engine = PaddleOCR(**kwargs)
                return
            except (TypeError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"Could not initialize PaddleOCR: {last_error}")

    def run(self, image_path: Path) -> OCRResult:
        """Run PaddleOCR and normalize common output shapes."""

        started = perf_counter()
        raw = self._run_raw(image_path)
        blocks = self._extract_blocks(raw)
        text = " ".join(block["text"] for block in blocks).strip()
        confidences = [float(block.get("confidence", 0.0)) for block in blocks]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        total_ms = int((perf_counter() - started) * 1000)
        return OCRResult(
            filename=image_path.name,
            full_text=text,
            avg_confidence=avg_confidence,
            blocks=blocks,
            source="local PaddleOCR",
            ocr_ms=total_ms,
            total_ms=total_ms,
        )

    def _run_raw(self, image_path: Path):
        """Run PaddleOCR using the available API surface."""

        if hasattr(self._engine, "ocr"):
            try:
                return self._engine.ocr(str(image_path), cls=True)
            except TypeError:
                return self._engine.ocr(str(image_path))
        if hasattr(self._engine, "predict"):
            return self._engine.predict(str(image_path))
        raise RuntimeError("PaddleOCR object has neither ocr() nor predict()")

    def _extract_blocks(self, raw) -> list[dict]:
        """Extract text/confidence/box dictionaries from PaddleOCR output."""

        blocks: list[dict] = []
        for result in raw if isinstance(raw, list) else [raw]:
            payload = getattr(result, "json", None)
            if payload is not None:
                blocks.extend(self._parse_json_payload(payload))
            elif isinstance(result, dict) and "res" in result:
                blocks.extend(self._parse_json_payload(result))
        if blocks:
            return blocks

        for item in self._flatten(raw):
            parsed = self._parse_item(item)
            if parsed is not None:
                blocks.append(parsed)
        return blocks

    def _parse_json_payload(self, payload: dict) -> list[dict]:
        """Parse PaddleOCR 3.x ``OCRResult.json`` payloads.

        Notes
        -----
        PaddleOCR 3.x returns a dict-like result object whose ``json`` property
        stores arrays such as ``rec_texts``, ``rec_scores``, and ``dt_polys``
        under a ``res`` key. That is different from older PaddleOCR versions
        that returned ``[box, (text, confidence)]`` rows.
        """

        result = payload.get("res", payload)
        texts = result.get("rec_texts") or result.get("texts") or []
        scores = result.get("rec_scores") or result.get("scores") or []
        boxes = result.get("rec_polys") or result.get("dt_polys") or result.get("boxes") or []
        blocks: list[dict] = []
        for index, text in enumerate(texts):
            if not text:
                continue
            confidence = scores[index] if index < len(scores) else 0.0
            bbox = boxes[index] if index < len(boxes) else None
            blocks.append({"text": str(text), "confidence": float(confidence), "bbox": bbox})
        return blocks

    def _flatten(self, value):
        """Yield nested OCR result items while preserving line-like entries."""

        if isinstance(value, dict):
            yield value
            return
        if not isinstance(value, (list, tuple)):
            return
        if self._looks_like_legacy_line(value):
            yield value
            return
        for item in value:
            yield from self._flatten(item)

    def _looks_like_legacy_line(self, value: list | tuple) -> bool:
        """Return whether a PaddleOCR item looks like ``[box, (text, conf)]``."""

        if len(value) != 2:
            return False
        maybe_text = value[1]
        return isinstance(maybe_text, (list, tuple)) and len(maybe_text) >= 2 and isinstance(maybe_text[0], str)

    def _parse_item(self, item) -> dict | None:
        """Parse common PaddleOCR line result shapes into a block dict."""

        if isinstance(item, dict):
            text = item.get("text") or item.get("rec_text") or item.get("label")
            confidence = item.get("confidence") or item.get("score") or item.get("rec_score") or 0.0
            bbox = item.get("bbox") or item.get("points") or item.get("box")
            if text:
                return {"text": str(text), "confidence": float(confidence), "bbox": bbox}
            return None

        if self._looks_like_legacy_line(item):
            bbox = item[0]
            text, confidence = item[1][0], item[1][1]
            return {"text": str(text), "confidence": float(confidence), "bbox": bbox}
        return None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        action="append",
        choices=["doctr", "paddleocr"],
        required=True,
        help="OCR engine to run. May be supplied more than once.",
    )
    parser.add_argument("--image", action="append", default=[], help="Image path to benchmark")
    parser.add_argument(
        "--image-glob",
        action="append",
        default=[],
        help="Glob pattern for image paths, e.g. 'data/work/public-cola/raw/images/*/*'",
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of images")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for benchmark CSV/JSON output",
    )
    parser.add_argument("--run-name", default="latest", help="Run directory name")
    return parser.parse_args()


def collect_images(args: argparse.Namespace) -> list[Path]:
    """Collect image paths from explicit arguments and glob patterns."""

    paths = [Path(path) for path in args.image]
    for pattern in args.image_glob:
        paths.extend(Path(path) for path in glob.glob(pattern, recursive=True))
    image_paths = [
        path
        for path in sorted({path.resolve() for path in paths})
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"} and path.exists()
    ]
    return image_paths[: args.limit]


def make_engine(name: str) -> SmokeEngine:
    """Create a smoke benchmark engine by name."""

    if name == "doctr":
        return DoctrSmokeEngine()
    if name == "paddleocr":
        return PaddleOCRSmokeEngine()
    raise ValueError(f"Unknown engine: {name}")


def relative_path(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def run_engine(engine: SmokeEngine, image_paths: list[Path], output_dir: Path) -> list[SmokeRow]:
    """Run one engine across all images."""

    rows: list[SmokeRow] = []
    for index, image_path in enumerate(image_paths, start=1):
        print(f"[{engine.name}] {index}/{len(image_paths)} {relative_path(image_path)}")
        started = perf_counter()
        try:
            result = engine.run(image_path)
            ocr_json_path = write_ocr_json(output_dir, engine.name, image_path, result)
            rows.append(
                SmokeRow(
                    engine=engine.name,
                    image_path=relative_path(image_path),
                    status="ok",
                    total_ms=result.total_ms or int((perf_counter() - started) * 1000),
                    avg_confidence=result.avg_confidence,
                    block_count=len(result.blocks),
                    text_chars=len(result.full_text),
                    ocr_json_path=relative_path(ocr_json_path),
                )
            )
        except Exception as exc:
            rows.append(
                SmokeRow(
                    engine=engine.name,
                    image_path=relative_path(image_path),
                    status="error",
                    total_ms=int((perf_counter() - started) * 1000),
                    avg_confidence=0.0,
                    block_count=0,
                    text_chars=0,
                    error=str(exc),
                )
            )
            print(f"  error: {exc}")
    return rows


def safe_artifact_stem(image_path: Path) -> str:
    """Return a filesystem-safe artifact stem for an image path."""

    relative = relative_path(image_path)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", relative).strip("._")


def write_ocr_json(output_dir: Path, engine_name: str, image_path: Path, result: OCRResult) -> Path:
    """Write normalized OCR JSON for later text/field inspection."""

    ocr_dir = output_dir / "ocr" / engine_name
    ocr_dir.mkdir(parents=True, exist_ok=True)
    path = ocr_dir / f"{safe_artifact_stem(image_path)}.json"
    try:
        payload = result.model_dump(mode="json")
    except Exception:
        payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def summarize(rows: list[SmokeRow]) -> dict:
    """Summarize benchmark rows by engine."""

    summary: dict[str, dict] = {}
    engines = sorted({row.engine for row in rows})
    for engine in engines:
        engine_rows = [row for row in rows if row.engine == engine]
        ok_rows = [row for row in engine_rows if row.status == "ok"]
        latencies = [row.total_ms for row in ok_rows]
        summary[engine] = {
            "image_count": len(engine_rows),
            "ok_count": len(ok_rows),
            "error_count": len(engine_rows) - len(ok_rows),
            "mean_ms": round(mean(latencies), 2) if latencies else None,
            "median_ms": round(median(latencies), 2) if latencies else None,
            "worst_ms": max(latencies) if latencies else None,
            "mean_confidence": round(mean(row.avg_confidence for row in ok_rows), 4) if ok_rows else None,
            "mean_block_count": round(mean(row.block_count for row in ok_rows), 2) if ok_rows else None,
            "mean_text_chars": round(mean(row.text_chars for row in ok_rows), 2) if ok_rows else None,
        }
    return summary


def write_outputs(output_dir: Path, rows: list[SmokeRow]) -> dict:
    """Write CSV row data and JSON summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)

    with (output_dir / "rows.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(rows[0]).keys()) if rows else list(SmokeRow.__dataclass_fields__))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    """Run requested OCR engine smoke benchmarks."""

    args = parse_args()
    image_paths = collect_images(args)
    if not image_paths:
        raise SystemExit("No images found. Pass --image or --image-glob.")

    output_dir = args.output_dir / args.run_name
    all_rows: list[SmokeRow] = []
    for engine_name in args.engine:
        engine = make_engine(engine_name)
        all_rows.extend(run_engine(engine, image_paths, output_dir))

    summary = write_outputs(output_dir, all_rows)
    print()
    print(f"Wrote OCR engine smoke outputs to {output_dir}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
