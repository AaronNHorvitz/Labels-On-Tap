"""OpenCV feature extraction for isolated warning-heading crops.

Notes
-----
The production typography model is intentionally small and CPU-friendly. It
does not try to read arbitrary label text. It receives an already-isolated
``GOVERNMENT WARNING:`` heading crop and emits stroke, projection, component,
and HOG features for the boldness classifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


WIDTH = 160
HEIGHT = 48


@dataclass(frozen=True)
class FeatureConfig:
    """Configuration for fixed-size typography feature extraction.

    Attributes
    ----------
    width, height:
        Target crop canvas dimensions.
    projection_bins_x, projection_bins_y:
        Number of bins used for vertical and horizontal ink projections.
    """

    width: int = WIDTH
    height: int = HEIGHT
    projection_bins_x: int = 32
    projection_bins_y: int = 12


def extract_feature_vector(
    image: np.ndarray,
    config: FeatureConfig = FeatureConfig(),
) -> np.ndarray:
    """Extract a fixed-length feature vector from one heading crop.

    Parameters
    ----------
    image:
        Grayscale or BGR crop containing only the warning heading.
    config:
        Feature extraction configuration.

    Returns
    -------
    numpy.ndarray
        One-dimensional float32 vector. The deployed logistic model expects
        this exact feature order.
    """

    cv2.setNumThreads(1)
    gray = _to_gray(image)
    normalized = _normalize_canvas(gray, width=config.width, height=config.height)
    binary = _threshold_text(normalized)
    text_mask = binary > 0

    ink_density = float(text_mask.mean())
    edges = cv2.Canny(normalized, 50, 150)
    edge_density = float((edges > 0).mean())

    bbox_area, bbox_aspect = _bbox_features(text_mask, config)
    stroke_mean, stroke_std, stroke_p90, stroke_cv = _stroke_features(binary)
    component_features = _component_features(binary, config)
    contour_area_density = _contour_area_density(binary, config)
    dark_mean = _dark_pixel_mean(normalized, text_mask)
    projection_features = _projection_features(binary, config)
    hog_features = _hog_features(normalized, config)

    base_features = np.array(
        [
            ink_density,
            edge_density,
            bbox_area,
            bbox_aspect,
            stroke_mean,
            stroke_std,
            stroke_p90,
            stroke_cv,
            *component_features,
            contour_area_density,
            dark_mean,
        ],
        dtype=np.float32,
    )
    return np.concatenate(
        [base_features, projection_features.astype(np.float32), hog_features],
    ).astype(np.float32)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _normalize_canvas(gray: np.ndarray, *, width: int, height: int) -> np.ndarray:
    gray = gray.astype(np.uint8, copy=False)
    h, w = gray.shape[:2]
    if h <= 0 or w <= 0:
        return np.full((height, width), 255, dtype=np.uint8)

    scale = min(width / w, height / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width), 255, dtype=np.uint8)
    y = (height - new_h) // 2
    x = (width - new_w) // 2
    canvas[y : y + new_h, x : x + new_w] = resized
    return canvas


def _threshold_text(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    return binary


def _bbox_features(text_mask: np.ndarray, config: FeatureConfig) -> tuple[float, float]:
    ys, xs = np.where(text_mask)
    if len(xs) == 0 or len(ys) == 0:
        return 0.0, 0.0
    width = float(xs.max() - xs.min() + 1)
    height = float(ys.max() - ys.min() + 1)
    area = (width * height) / float(config.width * config.height)
    aspect = width / max(height, 1.0)
    return float(area), float(aspect)


def _stroke_features(binary: np.ndarray) -> tuple[float, float, float, float]:
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    values = dist[binary > 0]
    if values.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    mean = float(values.mean())
    std = float(values.std())
    p90 = float(np.percentile(values, 90))
    cv = std / max(mean, 1e-6)
    return mean, std, p90, cv


def _component_features(binary: np.ndarray, config: FeatureConfig) -> list[float]:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    del labels
    if num_labels <= 1:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    components = stats[1:]
    areas = components[:, cv2.CC_STAT_AREA].astype(np.float32)
    widths = components[:, cv2.CC_STAT_WIDTH].astype(np.float32)
    heights = components[:, cv2.CC_STAT_HEIGHT].astype(np.float32)
    aspects = widths / np.maximum(heights, 1.0)
    image_area = float(config.width * config.height)
    return [
        float(len(components) / max(config.width, 1)),
        float(areas.mean() / image_area),
        float(areas.std() / image_area),
        float(widths.mean() / max(config.width, 1)),
        float(heights.mean() / max(config.height, 1)),
        float(aspects.mean()),
    ]


def _contour_area_density(binary: np.ndarray, config: FeatureConfig) -> float:
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    area = sum(cv2.contourArea(contour) for contour in contours)
    return float(area / float(config.width * config.height))


def _dark_pixel_mean(gray: np.ndarray, text_mask: np.ndarray) -> float:
    values = gray[text_mask]
    if values.size == 0:
        return 1.0
    return float(values.mean() / 255.0)


def _projection_features(binary: np.ndarray, config: FeatureConfig) -> np.ndarray:
    mask = (binary > 0).astype(np.float32)
    x_proj = _bin_means(mask.sum(axis=0), config.projection_bins_x)
    y_proj = _bin_means(mask.sum(axis=1), config.projection_bins_y)
    if x_proj.max(initial=0) > 0:
        x_proj = x_proj / max(float(mask.shape[0]), 1.0)
    if y_proj.max(initial=0) > 0:
        y_proj = y_proj / max(float(mask.shape[1]), 1.0)
    return np.concatenate([x_proj, y_proj]).astype(np.float32)


def _bin_means(values: np.ndarray, bins: int) -> np.ndarray:
    chunks: Iterable[np.ndarray] = np.array_split(values.astype(np.float32), bins)
    return np.array([float(chunk.mean()) if chunk.size else 0.0 for chunk in chunks])


def _hog_features(gray: np.ndarray, config: FeatureConfig) -> np.ndarray:
    hog = cv2.HOGDescriptor(
        _winSize=(config.width, config.height),
        _blockSize=(16, 16),
        _blockStride=(8, 8),
        _cellSize=(8, 8),
        _nbins=9,
    )
    descriptor = hog.compute(gray)
    if descriptor is None:
        return np.zeros(_hog_length(config), dtype=np.float32)
    return descriptor.reshape(-1).astype(np.float32)


def _hog_length(config: FeatureConfig) -> int:
    blocks_x = ((config.width - 16) // 8) + 1
    blocks_y = ((config.height - 16) // 8) + 1
    cells_per_block = (16 // 8) * (16 // 8)
    return blocks_x * blocks_y * cells_per_block * 9

