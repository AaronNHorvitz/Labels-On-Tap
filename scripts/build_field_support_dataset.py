#!/usr/bin/env python
"""Build field-support training/evaluation manifests from split applications.

This script does not run OCR and does not train a model. It creates the stable
application-field targets and controlled same-split negative examples that later
OCR engines, BERT arbiters, and graph scorers can consume.

Important leakage rule:

* split at the COLA application level first,
* generate field examples second,
* generate negatives only from the same split.

All generated outputs live under gitignored ``data/work/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.rules.field_matching import normalize_label_text

DEFAULT_SPLIT_DIR = REPO_ROOT / "data" / "work" / "cola" / "evaluation-splits" / "field-support-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "work" / "cola" / "field-support-datasets" / "field-support-v1"

CORE_FIELDS = (
    "brand_name",
    "fanciful_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "country_of_origin",
)
OPTIONAL_FIELDS = ("applicant_or_producer",)
FIELD_TARGET_FIELDS = [
    "target_id",
    "split",
    "ttb_id",
    "field_name",
    "expected",
    "expected_normalized",
    "source_run",
    "application_path",
    "image_dir",
    "local_image_count",
    "product_type",
    "origin_bucket",
    "image_bucket",
    "month_key",
    "imported",
]
PAIR_FIELDS = [
    "pair_id",
    "split",
    "ttb_id",
    "field_name",
    "label",
    "expected",
    "expected_normalized",
    "source_ttb_id",
    "source_target_id",
    "negative_strategy",
    "application_path",
    "image_dir",
    "local_image_count",
    "product_type",
    "origin_bucket",
    "image_bucket",
    "month_key",
    "imported",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--negative-per-positive", type=int, default=2)
    parser.add_argument("--include-applicant-producer", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    """Resolve a repo-relative or absolute path."""

    return path if path.is_absolute() else REPO_ROOT / path


def clean_cell(value: object) -> str:
    """Return a one-line CSV/JSONL-safe text value."""

    if value is None:
        return ""
    return " ".join(str(value).split())


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object."""

    return json.loads(path.read_text(encoding="utf-8"))


def read_manifest(path: Path) -> list[dict[str, str]]:
    """Read a split application manifest."""

    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write CSV rows with stable columns."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean_cell(row.get(field, "")) for field in fieldnames})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSON Lines rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {key: clean_cell(value) for key, value in row.items()}
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_id(*parts: object) -> str:
    """Return a stable short SHA-256 identifier."""

    raw = "|".join(clean_cell(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def field_names(include_applicant_producer: bool) -> tuple[str, ...]:
    """Return fields to include in the target dataset."""

    return (*CORE_FIELDS, *OPTIONAL_FIELDS) if include_applicant_producer else CORE_FIELDS


def imported_from_application(payload: dict[str, Any], manifest_row: dict[str, str]) -> str:
    """Return a stable imported flag as true/false text."""

    application = payload.get("application", {})
    if isinstance(application.get("imported"), bool):
        return str(application["imported"]).lower()
    return "true" if manifest_row.get("origin_bucket") == "imported" else "false"


def applicant_or_producer(payload: dict[str, Any]) -> str:
    """Extract applicant/producer when the parsed application exposes it.

    COLA Cloud detail records often map this to permit-like values rather than
    a human-readable producer. This field is intentionally optional.
    """

    form_fields = payload.get("form_fields", {})
    candidate = clean_cell(form_fields.get("applicant_name_address", ""))
    if "(Used on label)" in candidate:
        before_marker = candidate.split("(Used on label)", 1)[0]
        return clean_cell(before_marker.split()[-1])
    return candidate


def expected_fields(payload: dict[str, Any], *, include_applicant_producer: bool) -> dict[str, str]:
    """Extract expected application fields from one parsed application JSON."""

    application = payload.get("application", {})
    form_fields = payload.get("form_fields", {})
    fields = {
        "brand_name": application.get("brand_name") or form_fields.get("brand_name") or "",
        "fanciful_name": application.get("fanciful_name") or form_fields.get("fanciful_name") or "",
        "class_type": application.get("class_type") or form_fields.get("class_type_description") or "",
        "alcohol_content": application.get("alcohol_content") or form_fields.get("alcohol_content") or "",
        "net_contents": application.get("net_contents") or form_fields.get("net_contents") or "",
        "country_of_origin": application.get("country_of_origin") or "",
    }
    if include_applicant_producer:
        fields["applicant_or_producer"] = applicant_or_producer(payload)
    return {key: clean_cell(value) for key, value in fields.items()}


def target_row(
    *,
    split: str,
    manifest_row: dict[str, str],
    application_payload: dict[str, Any],
    field_name: str,
    expected: str,
) -> dict[str, Any]:
    """Build one expected field target row."""

    ttb_id = manifest_row["ttb_id"]
    return {
        "target_id": stable_id(split, ttb_id, field_name, expected),
        "split": split,
        "ttb_id": ttb_id,
        "field_name": field_name,
        "expected": expected,
        "expected_normalized": normalize_label_text(expected),
        "source_run": manifest_row.get("source_run", ""),
        "application_path": manifest_row.get("application_path", ""),
        "image_dir": manifest_row.get("image_dir", ""),
        "local_image_count": manifest_row.get("local_image_count", ""),
        "product_type": manifest_row.get("product_type", ""),
        "origin_bucket": manifest_row.get("origin_bucket", ""),
        "image_bucket": manifest_row.get("image_bucket", ""),
        "month_key": manifest_row.get("month_key", ""),
        "imported": imported_from_application(application_payload, manifest_row),
    }


def build_targets(
    split: str,
    rows: list[dict[str, str]],
    *,
    include_applicant_producer: bool,
) -> list[dict[str, Any]]:
    """Build field target rows for one split."""

    targets: list[dict[str, Any]] = []
    allowed_fields = set(field_names(include_applicant_producer))
    for row in rows:
        app_path = resolve_path(Path(row["application_path"]))
        payload = load_json(app_path)
        for field_name, expected in expected_fields(
            payload,
            include_applicant_producer=include_applicant_producer,
        ).items():
            if field_name not in allowed_fields or not expected:
                continue
            targets.append(
                target_row(
                    split=split,
                    manifest_row=row,
                    application_payload=payload,
                    field_name=field_name,
                    expected=expected,
                )
            )
    return targets


def positive_pair(target: dict[str, Any]) -> dict[str, Any]:
    """Return one positive pair example for a target."""

    return {
        "pair_id": stable_id("positive", target["target_id"]),
        "split": target["split"],
        "ttb_id": target["ttb_id"],
        "field_name": target["field_name"],
        "label": 1,
        "expected": target["expected"],
        "expected_normalized": target["expected_normalized"],
        "source_ttb_id": target["ttb_id"],
        "source_target_id": target["target_id"],
        "negative_strategy": "",
        "application_path": target["application_path"],
        "image_dir": target["image_dir"],
        "local_image_count": target["local_image_count"],
        "product_type": target["product_type"],
        "origin_bucket": target["origin_bucket"],
        "image_bucket": target["image_bucket"],
        "month_key": target["month_key"],
        "imported": target["imported"],
    }


def negative_pair(target: dict[str, Any], source: dict[str, Any], index: int) -> dict[str, Any]:
    """Return one same-field, same-split shuffled negative pair."""

    return {
        "pair_id": stable_id("negative", target["target_id"], source["target_id"], index),
        "split": target["split"],
        "ttb_id": target["ttb_id"],
        "field_name": target["field_name"],
        "label": 0,
        "expected": source["expected"],
        "expected_normalized": source["expected_normalized"],
        "source_ttb_id": source["ttb_id"],
        "source_target_id": source["target_id"],
        "negative_strategy": "same_split_same_field_shuffle",
        "application_path": target["application_path"],
        "image_dir": target["image_dir"],
        "local_image_count": target["local_image_count"],
        "product_type": target["product_type"],
        "origin_bucket": target["origin_bucket"],
        "image_bucket": target["image_bucket"],
        "month_key": target["month_key"],
        "imported": target["imported"],
    }


def build_pairs(
    targets: list[dict[str, Any]],
    *,
    negative_per_positive: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Build positive and same-split shuffled-negative examples."""

    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        pools[(target["split"], target["field_name"])].append(target)

    pairs: list[dict[str, Any]] = []
    for target in targets:
        pairs.append(positive_pair(target))
        candidates = [
            candidate
            for candidate in pools[(target["split"], target["field_name"])]
            if candidate["ttb_id"] != target["ttb_id"]
            and candidate["expected_normalized"] != target["expected_normalized"]
        ]
        rng.shuffle(candidates)
        for index, source in enumerate(candidates[:negative_per_positive], start=1):
            pairs.append(negative_pair(target, source, index))
    return pairs


def load_split_rows(split_dir: Path, split: str) -> list[dict[str, str]]:
    """Load one split application manifest."""

    return read_manifest(split_dir / f"{split}_applications.csv")


def counts_by(rows: list[dict[str, Any]], *fields: str) -> dict[str, int]:
    """Return sorted counts by a joined key."""

    counts = Counter(" | ".join(clean_cell(row.get(field, "")) for field in fields) for row in rows)
    return dict(sorted(counts.items()))


def summary(
    *,
    args: argparse.Namespace,
    targets_by_split: dict[str, list[dict[str, Any]]],
    pairs_by_split: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build a summary JSON object."""

    all_targets = [row for rows in targets_by_split.values() for row in rows]
    all_pairs = [row for rows in pairs_by_split.values() for row in rows]
    target_ids_by_split = {
        split: {row["ttb_id"] for row in rows}
        for split, rows in targets_by_split.items()
    }
    overlaps = {
        "train_validation": len(target_ids_by_split["train"] & target_ids_by_split["validation"]),
        "train_holdout": len(target_ids_by_split["train"] & target_ids_by_split["holdout"]),
        "validation_holdout": len(target_ids_by_split["validation"] & target_ids_by_split["holdout"]),
    }
    if any(overlaps.values()):
        raise AssertionError(f"Split leakage detected: {overlaps}")

    return {
        "dataset_name": args.output_dir.name,
        "created_by": "scripts/build_field_support_dataset.py",
        "split_dir": str(args.split_dir.relative_to(REPO_ROOT) if args.split_dir.is_relative_to(REPO_ROOT) else args.split_dir),
        "seed": args.seed,
        "negative_per_positive": args.negative_per_positive,
        "included_fields": list(field_names(args.include_applicant_producer)),
        "target_counts": {split: len(rows) for split, rows in targets_by_split.items()},
        "pair_counts": {split: len(rows) for split, rows in pairs_by_split.items()},
        "label_counts": {
            split: counts_by(rows, "label")
            for split, rows in pairs_by_split.items()
        },
        "field_counts": {
            split: counts_by(rows, "field_name")
            for split, rows in targets_by_split.items()
        },
        "pair_field_label_counts": {
            split: counts_by(rows, "field_name", "label")
            for split, rows in pairs_by_split.items()
        },
        "split_ttb_overlap": overlaps,
        "total_targets": len(all_targets),
        "total_pairs": len(all_pairs),
        "notes": [
            "Targets contain expected application fields only; OCR evidence is attached in later stages.",
            "Negative pairs are same-split same-field shuffled values to avoid cross-split leakage.",
            "Applicant/producer is excluded by default because current public metadata is inconsistent for that target.",
        ],
    }


def write_split_outputs(
    *,
    output_dir: Path,
    targets_by_split: dict[str, list[dict[str, Any]]],
    pairs_by_split: dict[str, list[dict[str, Any]]],
) -> None:
    """Write all split-specific and combined outputs."""

    all_targets = [row for split in ("train", "validation", "holdout") for row in targets_by_split[split]]
    all_pairs = [row for split in ("train", "validation", "holdout") for row in pairs_by_split[split]]

    for split in ("train", "validation", "holdout"):
        write_csv(output_dir / f"{split}_field_targets.csv", targets_by_split[split], FIELD_TARGET_FIELDS)
        write_jsonl(output_dir / f"{split}_field_targets.jsonl", targets_by_split[split])
        write_csv(output_dir / f"{split}_field_pairs.csv", pairs_by_split[split], PAIR_FIELDS)
        write_jsonl(output_dir / f"{split}_field_pairs.jsonl", pairs_by_split[split])

    write_csv(output_dir / "all_field_targets.csv", all_targets, FIELD_TARGET_FIELDS)
    write_jsonl(output_dir / "all_field_targets.jsonl", all_targets)
    write_csv(output_dir / "all_field_pairs.csv", all_pairs, PAIR_FIELDS)
    write_jsonl(output_dir / "all_field_pairs.jsonl", all_pairs)


def main() -> None:
    """Build field target and pair manifests."""

    args = parse_args()
    args.split_dir = resolve_path(args.split_dir)
    args.output_dir = resolve_path(args.output_dir)
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"Output directory already has files; pass --force: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    split_rows = {
        "train": load_split_rows(args.split_dir, "train"),
        "validation": load_split_rows(args.split_dir, "validation"),
        "holdout": load_split_rows(args.split_dir, "holdout"),
    }
    targets_by_split = {
        split: build_targets(split, rows, include_applicant_producer=args.include_applicant_producer)
        for split, rows in split_rows.items()
    }
    pairs_by_split = {
        split: build_pairs(
            targets,
            negative_per_positive=args.negative_per_positive,
            seed=args.seed + index,
        )
        for index, (split, targets) in enumerate(targets_by_split.items())
    }
    write_split_outputs(
        output_dir=args.output_dir,
        targets_by_split=targets_by_split,
        pairs_by_split=pairs_by_split,
    )
    payload = summary(args=args, targets_by_split=targets_by_split, pairs_by_split=pairs_by_split)
    write_json(args.output_dir / "dataset_summary.json", payload)

    print(f"Dataset directory: {args.output_dir.relative_to(REPO_ROOT)}")
    for split in ("train", "validation", "holdout"):
        print(
            f"{split}: {len(targets_by_split[split])} target(s), "
            f"{len(pairs_by_split[split])} pair(s)"
        )
    print(f"Total targets: {payload['total_targets']}")
    print(f"Total pairs: {payload['total_pairs']}")
    print(f"Split TTB overlap: {payload['split_ttb_overlap']}")


if __name__ == "__main__":
    main()
