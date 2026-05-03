"""Warning-heading location and crop normalization.

Notes
-----
The typography classifier is only useful when it receives the actual
``GOVERNMENT WARNING:`` heading. Real OCR engines often return a larger warning
line that includes regular-weight body text, so this module trims the crop to
the heading prefix before classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.schemas.ocr import OCRResult


@dataclass(frozen=True)
class HeadingEvidence:
    """Detected warning-heading crop and the OCR evidence used to find it."""

    crop: Image.Image
    matched_text: str
    match_score: float
    ocr_confidence: float | None
    crop_ms: float


def detect_warning_heading_crop(
    image_path: Path,
    ocr: OCRResult | dict[str, Any],
    *,
    min_heading_score: float = 0.72,
    crop_padding_x: float = 0.30,
    crop_padding_top: float = 0.20,
    crop_padding_bottom: float = 0.05,
    heading_width_factor: float = 1.08,
) -> HeadingEvidence | None:
    """Find and normalize a crop around ``GOVERNMENT WARNING:``.

    Parameters
    ----------
    image_path:
        Source label image path.
    ocr:
        OCR result containing text blocks and optional bounding boxes.
    min_heading_score:
        Minimum fuzzy heading score required before cropping.

    Returns
    -------
    HeadingEvidence | None
        Normalized heading crop and source metadata, or ``None`` when the
        warning heading cannot be isolated from OCR geometry.
    """

    started = perf_counter()
    candidate = best_warning_heading_candidate(ocr, min_heading_score=min_heading_score)
    if candidate is None:
        return None

    try:
        with Image.open(image_path) as image:
            crop = crop_candidate_heading(
                image.convert("L"),
                candidate["bbox"],
                candidate["text"],
                padding_x_factor=crop_padding_x,
                padding_top_factor=crop_padding_top,
                padding_bottom_factor=crop_padding_bottom,
                heading_width_factor=heading_width_factor,
            )
    except OSError:
        return None

    return HeadingEvidence(
        crop=crop,
        matched_text=candidate["text"],
        match_score=float(candidate["score"]),
        ocr_confidence=candidate["confidence"],
        crop_ms=(perf_counter() - started) * 1000,
    )


def best_warning_heading_candidate(
    ocr: OCRResult | dict[str, Any],
    *,
    min_heading_score: float,
) -> dict[str, Any] | None:
    """Return the best OCR block that looks like a warning heading."""

    candidates: list[dict[str, Any]] = []
    blocks = _ocr_blocks(ocr)
    for block in blocks:
        _append_candidate(candidates, [block], min_heading_score=min_heading_score)
    for start in range(len(blocks)):
        for end in range(start + 2, min(start + 7, len(blocks)) + 1):
            _append_candidate(candidates, blocks[start:end], min_heading_score=min_heading_score)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["score"], item["confidence"] or 0.0))


def _append_candidate(
    candidates: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    *,
    min_heading_score: float,
) -> None:
    """Append one single-block or merged word-window heading candidate."""

    usable = [block for block in blocks if block.get("bbox") is not None]
    if len(usable) != len(blocks):
        return
    text = " ".join(str(block.get("text") or "") for block in blocks).strip()
    score = heading_score(text)
    if score < min_heading_score:
        return
    bbox = merge_bboxes([block["bbox"] for block in blocks])
    if bbox is None:
        return
    confidences = [_parse_float(block.get("confidence")) for block in blocks]
    numeric = [value for value in confidences if value is not None]
    candidates.append(
        {
            "text": text,
            "score": score,
            "confidence": sum(numeric) / len(numeric) if numeric else None,
            "bbox": bbox,
        }
    )


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
    """Dependency-free longest-common-subsequence ratio for short strings."""

    if not left or not right:
        return 0.0
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
    """Crop only the visible warning-heading prefix from an OCR box."""

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
    """Return normalized min/max bounds for two-point boxes or polygons."""

    points: list[tuple[float, float]] = []
    for point in bbox:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if not points:
        return 0.0, 0.0, 1.0, 1.0
    if max(max(abs(x), abs(y)) for x, y in points) > 1.5:
        points = [(x / max(image_width, 1), y / max(image_height, 1)) for x, y in points]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys))


def merge_bboxes(bboxes: list[Any]) -> list[list[float]] | None:
    """Return a rectangular bbox enclosing several OCR boxes."""

    points: list[tuple[float, float]] = []
    for bbox in bboxes:
        if not isinstance(bbox, list):
            return None
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _ocr_blocks(ocr: OCRResult | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(ocr, OCRResult):
        return [block.model_dump() if hasattr(block, "model_dump") else block.dict() for block in ocr.blocks]
    blocks = ocr.get("blocks", [])
    return [block for block in blocks if isinstance(block, dict)]


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
