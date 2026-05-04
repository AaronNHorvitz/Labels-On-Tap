"""Evaluate safety thresholds for the audit-v6 CNN boldness model.

The hard-argmax CNN answers a four-class question. Runtime typography clearance
needs a narrower policy question:

```
When is the probability of bold high enough to clear the boldness check?
```

This script loads a trained checkpoint, computes validation/test bold
probabilities, and reports threshold policies tuned by validation false-clear
tolerance.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from experiments.typography_preflight.train_audit_v6_cnn import (
    CLASS_NAMES,
    DEFAULT_AUDIT_DIR,
    DEFAULT_OUTPUT_DIR,
    POSITIVE_CLASS,
    build_loaders,
    build_model,
    choose_device,
    load_manifest,
    resolve_path,
    run_inference,
    write_json,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_OUTPUT_DIR / "models/mobilenet_v3_small_best.pt")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    return parser.parse_args()


def main() -> None:
    """Run threshold selection and write reports."""

    args = parse_args()
    audit_dir = resolve_path(args.audit_dir)
    output_dir = resolve_path(args.output_dir)
    checkpoint_path = resolve_path(args.checkpoint)
    rows_by_split = load_manifest(audit_dir / "manifest.csv")
    loader_args = argparse.Namespace(
        batch_size=args.batch_size,
        workers=args.workers,
        image_size=args.image_size,
    )
    _, validation_loader, test_loader = build_loaders(audit_dir, rows_by_split, loader_args)
    device = choose_device(args.device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model = build_model(class_count=len(CLASS_NAMES), weights="none")
    model.load_state_dict(checkpoint["model"])
    model.to(device)
    validation = run_inference(model, validation_loader, device)
    test = run_inference(model, test_loader, device)

    thresholds = sorted({0.5, 0.7, 0.85, 0.9, 0.95, 0.975, 0.99, 0.995, *np.linspace(0.5, 0.999, 250)})
    threshold_grid = [
        {
            "threshold": float(threshold),
            "validation": compute_clear_metrics(validation, threshold),
            "test": compute_clear_metrics(test, threshold),
        }
        for threshold in thresholds
    ]
    selected = select_by_tolerance(threshold_grid, tolerances=[0.0, 0.001, 0.0025, 0.005, 0.01])
    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checkpoint": str(checkpoint_path.relative_to(resolve_path(Path(".")))),
        "positive_class": POSITIVE_CLASS,
        "threshold_grid": threshold_grid,
        "selected_by_validation_false_clear": selected,
        "notes": [
            "clear means prob_bold >= threshold.",
            "false clear means actual class is not bold but clear is true.",
            "bold_clear_rate is the share of true bold examples that would clear automatically.",
            "non_clear_rate is the share of all examples routed away from automatic bold clearance.",
        ],
    }
    write_json(output_dir / "metrics/threshold_sweep.json", summary)
    write_report(output_dir / "metrics/threshold_sweep.md", summary)
    print(json.dumps(summary["selected_by_validation_false_clear"], indent=2), flush=True)


def compute_clear_metrics(preds: dict[str, list[Any]], threshold: float) -> dict[str, float | int]:
    """Compute binary clear/not-clear metrics for one threshold."""

    true = np.array(preds["y_true"])
    prob_bold = np.array(preds["y_prob_bold"])
    bold_idx = CLASS_NAMES.index(POSITIVE_CLASS)
    actual_bold = true == bold_idx
    clear = prob_bold >= threshold
    non_bold = ~actual_bold
    tp = int((clear & actual_bold).sum())
    fp = int((clear & non_bold).sum())
    tn = int((~clear & non_bold).sum())
    fn = int((~clear & actual_bold).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall / max(precision + recall, 1e-12)) if (precision + recall) else 0.0
    negative_precision = tn / max(tn + fn, 1)
    negative_recall = tn / max(tn + fp, 1)
    negative_f1 = (
        2 * negative_precision * negative_recall / max(negative_precision + negative_recall, 1e-12)
        if (negative_precision + negative_recall)
        else 0.0
    )
    return {
        "threshold": float(threshold),
        "examples": int(len(true)),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": float((tp + tn) / max(len(true), 1)),
        "precision": float(precision),
        "bold_clear_rate": float(recall),
        "false_clear_rate": float(fp / max(non_bold.sum(), 1)),
        "non_clear_rate": float((~clear).sum() / max(len(clear), 1)),
        "f1": float(f1),
        "negative_precision": float(negative_precision),
        "negative_recall": float(negative_recall),
        "negative_f1": float(negative_f1),
        "binary_macro_f1": float((f1 + negative_f1) / 2),
    }


def select_by_tolerance(grid: list[dict[str, Any]], tolerances: list[float]) -> list[dict[str, Any]]:
    """Select the highest bold clear rate within each validation false-clear tolerance."""

    selected: list[dict[str, Any]] = []
    for tolerance in tolerances:
        candidates = [row for row in grid if row["validation"]["false_clear_rate"] <= tolerance]
        if not candidates:
            continue
        best = max(candidates, key=lambda row: (row["validation"]["bold_clear_rate"], row["validation"]["f1"]))
        selected.append(
            {
                "tolerance": tolerance,
                "threshold": best["threshold"],
                "validation": best["validation"],
                "test": best["test"],
            }
        )
    return selected


def write_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a compact Markdown threshold report."""

    rows = []
    for item in summary["selected_by_validation_false_clear"]:
        val = item["validation"]
        test = item["test"]
        rows.append(
            "| {tol:.4f} | {thr:.4f} | {val_fc:.6f} | {val_clear:.4f} | "
            "{test_macro:.4f} | {test_fc:.6f} | {test_clear:.4f} | {test_non_clear:.4f} |".format(
                tol=item["tolerance"],
                thr=item["threshold"],
                val_fc=val["false_clear_rate"],
                val_clear=val["bold_clear_rate"],
                test_macro=test["binary_macro_f1"],
                test_fc=test["false_clear_rate"],
                test_clear=test["bold_clear_rate"],
                test_non_clear=test["non_clear_rate"],
            )
        )
    path.write_text(
        f"""# Audit-v6 CNN Threshold Sweep

Clearance policy: `prob_bold >= threshold`.

| Validation false-clear tolerance | Threshold | Val false-clear | Val bold clear | Test binary macro F1 | Test false-clear | Test bold clear | Test non-clear |
|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
