"""Feature builders for the graph-aware OCR evidence scorer.

The current experiment treats local OCR boxes as graph nodes. It does not train
an OCR model from pixels. Instead, it asks whether the detected text fragments
support a specific COLA application field such as brand name, ABV, net contents,
or country of origin.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.services.rules.field_matching import fuzzy_score, normalize_label_text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cola_etl.database import connect
from cola_etl.evaluation import expected_fields, field_candidates, registry_record
from cola_etl.paths import PARSED_APPLICATIONS_DIR, PARSED_OCR_DIR


FIELDS = (
    "brand_name",
    "fanciful_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "country_of_origin",
)
FIELD_INDEX = {field_name: index for index, field_name in enumerate(FIELDS)}
UNIT_TERMS = {
    "%": ("%", "alc", "vol", "alcohol", "proof"),
    "ml": ("ml", "milliliter", "milliliters"),
    "l": ("l", "liter", "liters"),
    "oz": ("oz", "fl", "fluid", "ounce", "ounces"),
    "pint": ("pint", "pints"),
    "gal": ("gal", "gallon", "gallons"),
}


@dataclass(frozen=True)
class OCRNode:
    """One OCR text box node.

    Parameters
    ----------
    text:
        OCR fragment text.
    confidence:
        OCR confidence normalized to 0 through 1.
    bbox:
        Normalized bounding box in ``[[x1, y1], [x2, y2]]`` form when present.
    panel_order:
        One-based label panel order within the COLA application.
    panel_count:
        Number of OCR panels available for the application.
    """

    text: str
    confidence: float
    bbox: object | None
    panel_order: int
    panel_count: int


@dataclass(frozen=True)
class GraphExample:
    """One field-to-OCR graph training/evaluation example."""

    ttb_id: str
    field_name: str
    expected: str
    label: int
    source_ttb_id: str
    nodes: list[OCRNode]
    baseline_score: float


def read_ttb_ids(path: Path) -> list[str]:
    """Read one TTB ID per line."""

    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_json(path: Path) -> dict:
    """Load a UTF-8 JSON object."""

    return json.loads(path.read_text(encoding="utf-8"))


def load_expected_fields(ttb_id: str, connection: sqlite3.Connection) -> dict[str, str]:
    """Load application field expectations for one parsed public COLA record."""

    parsed_path = PARSED_APPLICATIONS_DIR / f"{ttb_id}.json"
    if not parsed_path.exists():
        return {}
    parsed = load_json(parsed_path)
    registry = registry_record(connection, ttb_id)
    return expected_fields(parsed, registry)


def load_ocr_nodes(ttb_id: str) -> list[OCRNode]:
    """Load cached OCR boxes for all panels of one public COLA application."""

    panel_dir = PARSED_OCR_DIR / "panels" / ttb_id
    if not panel_dir.exists():
        return []

    panel_paths = sorted(panel_dir.glob("*.json"))
    panel_count = max(len(panel_paths), 1)
    nodes: list[OCRNode] = []
    for panel_index, path in enumerate(panel_paths, start=1):
        payload = load_json(path)
        for block in payload.get("blocks", []):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            try:
                confidence = float(block.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            nodes.append(
                OCRNode(
                    text=text,
                    confidence=max(0.0, min(confidence, 1.0)),
                    bbox=block.get("bbox"),
                    panel_order=panel_index,
                    panel_count=panel_count,
                )
            )
    return nodes


def aggregate_text(nodes: Iterable[OCRNode]) -> str:
    """Return OCR text joined in cache order."""

    return " ".join(node.text for node in nodes)


def baseline_field_score(field_name: str, expected: str, nodes: list[OCRNode]) -> float:
    """Return the current text-only baseline score for an expected field."""

    text = aggregate_text(nodes)
    candidates = field_candidates(field_name, expected)
    return max((fuzzy_score(candidate, text) for candidate in candidates), default=0.0)


def bbox_geometry(bbox: object | None) -> tuple[float, float, float, float, float, float]:
    """Return normalized ``x_center, y_center, width, height, area, aspect``."""

    try:
        (x1, y1), (x2, y2) = bbox  # type: ignore[misc]
        x1 = float(x1)
        y1 = float(y1)
        x2 = float(x2)
        y2 = float(y2)
    except (TypeError, ValueError):
        return 0.5, 0.5, 0.0, 0.0, 0.0, 0.0

    width = max(0.0, min(1.0, x2 - x1))
    height = max(0.0, min(1.0, y2 - y1))
    area = width * height
    aspect = width / height if height > 0 else 0.0
    return (
        max(0.0, min(1.0, x1 + width / 2)),
        max(0.0, min(1.0, y1 + height / 2)),
        width,
        height,
        area,
        min(aspect, 20.0) / 20.0,
    )


def first_number(value: str) -> str:
    """Return the first numeric token in text."""

    import re

    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return match.group(0) if match else ""


def token_overlap(expected: str, observed: str) -> float:
    """Return normalized token-overlap score."""

    expected_terms = set(normalize_label_text(expected).split())
    observed_terms = set(normalize_label_text(observed).split())
    if not expected_terms:
        return 0.0
    return len(expected_terms & observed_terms) / len(expected_terms)


def expected_unit_terms(expected: str) -> set[str]:
    """Return unit buckets implied by an expected field value."""

    text = normalize_label_text(expected)
    buckets: set[str] = set()
    for bucket, terms in UNIT_TERMS.items():
        if any(term in text for term in terms):
            buckets.add(bucket)
    return buckets


def unit_match(expected: str, observed: str) -> float:
    """Return 1 when observed text shares expected unit semantics."""

    expected_buckets = expected_unit_terms(expected)
    if not expected_buckets:
        return 0.0
    observed_text = normalize_label_text(observed)
    for bucket in expected_buckets:
        if any(term in observed_text for term in UNIT_TERMS[bucket]):
            return 1.0
    return 0.0


def node_similarity(field_name: str, expected: str, node: OCRNode) -> float:
    """Return the best fuzzy similarity between a field value and one OCR node."""

    candidates = field_candidates(field_name, expected)
    return max((fuzzy_score(candidate, node.text) / 100.0 for candidate in candidates), default=0.0)


def node_rank(field_name: str, expected: str, node: OCRNode) -> float:
    """Return a lightweight rank score used to cap very large OCR graphs."""

    number = first_number(expected)
    number_hit = 1.0 if number and number in normalize_label_text(node.text) else 0.0
    return (
        node_similarity(field_name, expected, node)
        + 0.25 * token_overlap(expected, node.text)
        + 0.20 * unit_match(expected, node.text)
        + 0.15 * number_hit
        + 0.05 * node.confidence
    )


def node_features(field_name: str, expected: str, node: OCRNode) -> list[float]:
    """Build numeric node features for one field-conditioned OCR node."""

    x_center, y_center, width, height, area, aspect = bbox_geometry(node.bbox)
    text_norm = normalize_label_text(node.text)
    number = first_number(expected)
    number_hit = 1.0 if number and number in text_norm else 0.0
    field_one_hot = [0.0] * len(FIELDS)
    field_one_hot[FIELD_INDEX[field_name]] = 1.0
    panel_ratio = node.panel_order / max(node.panel_count, 1)

    return [
        node.confidence,
        x_center,
        y_center,
        width,
        height,
        area,
        aspect,
        min(len(text_norm), 40) / 40.0,
        node_similarity(field_name, expected, node),
        token_overlap(expected, node.text),
        number_hit,
        unit_match(expected, node.text),
        panel_ratio,
        node.panel_count / 10.0,
        *field_one_hot,
    ]


def select_nodes(
    nodes: list[OCRNode],
    *,
    field_name: str,
    expected: str,
    max_nodes: int,
) -> list[OCRNode]:
    """Keep the most field-relevant nodes while preserving enough context."""

    if len(nodes) <= max_nodes:
        return nodes
    ranked = sorted(
        enumerate(nodes),
        key=lambda item: node_rank(field_name, expected, item[1]),
        reverse=True,
    )
    kept_indexes = {index for index, _ in ranked[:max_nodes]}
    return [node for index, node in enumerate(nodes) if index in kept_indexes]


def adjacency_matrix(nodes: list[OCRNode], *, k: int) -> list[list[float]]:
    """Build a row-normalized KNN adjacency matrix over OCR boxes."""

    n_nodes = len(nodes)
    if n_nodes == 0:
        return []

    centers = [bbox_geometry(node.bbox)[:2] for node in nodes]
    matrix = [[0.0 for _ in range(n_nodes)] for _ in range(n_nodes)]
    for index, (x1, y1) in enumerate(centers):
        distances: list[tuple[float, int]] = []
        for other_index, (x2, y2) in enumerate(centers):
            if index == other_index:
                continue
            panel_penalty = 2.0 if nodes[index].panel_order != nodes[other_index].panel_order else 0.0
            distance = math.hypot(x1 - x2, y1 - y2) + panel_penalty
            distances.append((distance, other_index))
        for _, neighbor_index in sorted(distances)[: min(k, len(distances))]:
            matrix[index][neighbor_index] = 1.0
            matrix[neighbor_index][index] = 1.0
        matrix[index][index] = 1.0

    for index, row in enumerate(matrix):
        total = sum(row) or 1.0
        matrix[index] = [value / total for value in row]
    return matrix


def build_feature_graph(
    example: GraphExample,
    *,
    max_nodes: int,
    knn_k: int,
) -> dict:
    """Convert one raw graph example to numeric features and adjacency."""

    nodes = select_nodes(
        example.nodes,
        field_name=example.field_name,
        expected=example.expected,
        max_nodes=max_nodes,
    )
    return {
        "ttb_id": example.ttb_id,
        "field_name": example.field_name,
        "expected": example.expected,
        "label": example.label,
        "source_ttb_id": example.source_ttb_id,
        "baseline_score": example.baseline_score,
        "x": [node_features(example.field_name, example.expected, node) for node in nodes],
        "adj": adjacency_matrix(nodes, k=knn_k),
        "summary_x": graph_summary_features(
            nodes,
            field_name=example.field_name,
            expected=example.expected,
            baseline_score=example.baseline_score,
        ),
        "node_count": len(nodes),
    }


def graph_summary_features(
    nodes: list[OCRNode],
    *,
    field_name: str,
    expected: str,
    baseline_score: float,
) -> list[float]:
    """Build graph-level evidence features.

    Notes
    -----
    These features give the model direct access to high-signal graph facts while
    the node path still learns how geometry and context change their weight.
    Without this summary path, tiny single-graph batches can collapse to a
    constant score during early POC training.
    """

    if not nodes:
        return [0.0] * 12

    similarities = [node_similarity(field_name, expected, node) for node in nodes]
    overlaps = [token_overlap(expected, node.text) for node in nodes]
    units = [unit_match(expected, node.text) for node in nodes]
    number = first_number(expected)
    number_hits = [
        1.0 if number and number in normalize_label_text(node.text) else 0.0
        for node in nodes
    ]
    confidences = [node.confidence for node in nodes]
    sorted_sims = sorted(similarities, reverse=True)
    top3_mean = sum(sorted_sims[:3]) / min(3, len(sorted_sims))
    top8_mean = sum(sorted_sims[:8]) / min(8, len(sorted_sims))
    panel_count = max(node.panel_count for node in nodes)
    high_similarity_count = sum(1 for value in similarities if value >= 0.80)

    return [
        baseline_score / 100.0,
        max(similarities),
        top3_mean,
        top8_mean,
        max(overlaps),
        max(units),
        max(number_hits),
        max(confidences),
        sum(confidences) / len(confidences),
        min(len(nodes), 256) / 256.0,
        min(panel_count, 10) / 10.0,
        min(high_similarity_count, 10) / 10.0,
    ]


def split_ids(
    ttb_ids: list[str],
    *,
    seed: int,
    train_ratio: float = 0.70,
    dev_ratio: float = 0.15,
) -> dict[str, set[str]]:
    """Split TTB IDs into train/dev/test buckets."""

    rng = random.Random(seed)
    shuffled = list(ttb_ids)
    rng.shuffle(shuffled)
    train_cut = int(len(shuffled) * train_ratio)
    dev_cut = train_cut + int(len(shuffled) * dev_ratio)
    return {
        "train": set(shuffled[:train_cut]),
        "dev": set(shuffled[train_cut:dev_cut]),
        "test": set(shuffled[dev_cut:]),
    }


def build_examples(
    *,
    ttb_ids: list[str],
    negative_per_positive: int,
    seed: int,
) -> list[GraphExample]:
    """Build positive and shuffled-negative field evidence examples."""

    rng = random.Random(seed)
    with connect() as connection:
        values_by_id = {ttb_id: load_expected_fields(ttb_id, connection) for ttb_id in ttb_ids}

    nodes_by_id = {ttb_id: load_ocr_nodes(ttb_id) for ttb_id in ttb_ids}
    field_pool: dict[str, list[tuple[str, str]]] = {field_name: [] for field_name in FIELDS}
    for ttb_id, fields in values_by_id.items():
        if not nodes_by_id.get(ttb_id):
            continue
        for field_name in FIELDS:
            value = str(fields.get(field_name) or "").strip()
            if value:
                field_pool[field_name].append((ttb_id, value))

    examples: list[GraphExample] = []
    for ttb_id in ttb_ids:
        nodes = nodes_by_id.get(ttb_id, [])
        if not nodes:
            continue
        fields = values_by_id.get(ttb_id, {})
        for field_name in FIELDS:
            expected = str(fields.get(field_name) or "").strip()
            if not expected:
                continue
            examples.append(
                GraphExample(
                    ttb_id=ttb_id,
                    field_name=field_name,
                    expected=expected,
                    label=1,
                    source_ttb_id=ttb_id,
                    nodes=nodes,
                    baseline_score=baseline_field_score(field_name, expected, nodes),
                )
            )

            negative_candidates = [
                (source_id, value)
                for source_id, value in field_pool[field_name]
                if source_id != ttb_id and normalize_label_text(value) != normalize_label_text(expected)
            ]
            rng.shuffle(negative_candidates)
            for source_id, negative_value in negative_candidates[:negative_per_positive]:
                examples.append(
                    GraphExample(
                        ttb_id=ttb_id,
                        field_name=field_name,
                        expected=negative_value,
                        label=0,
                        source_ttb_id=source_id,
                        nodes=nodes,
                        baseline_score=baseline_field_score(field_name, negative_value, nodes),
                    )
                )
    return examples


def examples_to_feature_graphs(
    examples: list[GraphExample],
    *,
    max_nodes: int,
    knn_k: int,
) -> list[dict]:
    """Convert raw examples into numeric graph dictionaries."""

    return [build_feature_graph(example, max_nodes=max_nodes, knn_k=knn_k) for example in examples]
