"""Train a CNN challenger on the audit-v6 typography image set.

This experiment is intentionally narrow: classify ``boldness_label`` from the
audit-v6 image crops. The output is an offline model comparison artifact, not a
runtime promotion. The primary safety metric remains false-clear rate:

``actual != bold`` predicted as ``bold``.

The default model is MobileNetV3-Small with ImageNet transfer learning. That is
large enough to learn typography/texture cues but small enough to benchmark for
CPU deployment risk.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageFile
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_DIR = ROOT / "data/work/typography-preflight/audit-v6"
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/cnn-audit-v6-mobilenet-v1"
CLASS_NAMES = ("bold", "not_bold", "unreadable_review", "not_applicable")
POSITIVE_CLASS = "bold"


@dataclass(frozen=True)
class ImageRow:
    """One audit-v6 image crop and its labels/provenance."""

    split: str
    sample_id: str
    crop_path: str
    boldness_label: str
    source_kind: str
    source_origin: str
    ttb_id: str


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--weights", choices=["imagenet", "none"], default="imagenet")
    parser.add_argument("--freeze-backbone-epochs", type=int, default=2)
    parser.add_argument("--cpu-latency-rows", type=int, default=256)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    return parser.parse_args()


def main() -> None:
    """Train, evaluate, and write model comparison artifacts."""

    args = parse_args()
    configure_reproducibility(args.seed)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ("metrics", "models"):
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    audit_dir = resolve_path(args.audit_dir)
    rows_by_split = load_manifest(audit_dir / "manifest.csv")
    device = choose_device(args.device)
    if device.type == "cpu":
        raise SystemExit("CUDA is not available or was not selected. Refusing to run CNN training on CPU.")

    train_loader, validation_loader, test_loader = build_loaders(audit_dir, rows_by_split, args)
    model = build_model(class_count=len(CLASS_NAMES), weights=args.weights).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    criterion = nn.CrossEntropyLoss(weight=class_weights(rows_by_split["train"]).to(device))

    best_state: dict[str, Any] | None = None
    best_score = -1.0
    history: list[dict[str, Any]] = []
    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        set_backbone_trainability(model, trainable=epoch > args.freeze_backbone_epochs)
        train_stats = run_train_epoch(model, train_loader, optimizer, criterion, device)
        validation_preds = run_inference(model, validation_loader, device)
        validation_metrics = compute_metrics(validation_preds["y_true"], validation_preds["y_pred"], CLASS_NAMES)
        score = validation_metrics["macro_f1"] - (validation_metrics["false_clear_rate"] * 4.0)
        row = {
            "epoch": epoch,
            "train": train_stats,
            "validation": validation_metrics,
            "selection_score": score,
            "backbone_trainable": epoch > args.freeze_backbone_epochs,
        }
        history.append(row)
        print(json.dumps(row, indent=2), flush=True)
        if score > best_score:
            best_score = score
            best_state = {
                "model": model.state_dict(),
                "epoch": epoch,
                "validation_metrics": validation_metrics,
                "class_names": CLASS_NAMES,
                "args": vars(args),
            }

    assert best_state is not None
    model.load_state_dict(best_state["model"])
    test_preds = run_inference(model, test_loader, device)
    test_metrics = compute_metrics(test_preds["y_true"], test_preds["y_pred"], CLASS_NAMES)
    test_breakdowns = compute_group_breakdowns(test_preds, CLASS_NAMES)
    gpu_latency = measure_latency(model, test_loader, device, rows=args.cpu_latency_rows)
    cpu_latency = measure_cpu_latency(model, test_loader, rows=args.cpu_latency_rows)
    elapsed_s = time.perf_counter() - started

    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "CNN challenger for audit-v6 boldness_label classification",
        "model": "mobilenet_v3_small",
        "weights": args.weights,
        "device": str(device),
        "class_names": list(CLASS_NAMES),
        "positive_class": POSITIVE_CLASS,
        "counts": {split: len(rows) for split, rows in rows_by_split.items()},
        "label_counts": {
            split: dict(sorted(Counter(row.boldness_label for row in rows).items()))
            for split, rows in rows_by_split.items()
        },
        "history": history,
        "best_epoch": best_state["epoch"],
        "best_validation": best_state["validation_metrics"],
        "test": test_metrics,
        "test_breakdowns": test_breakdowns,
        "latency": {
            "gpu": gpu_latency,
            "cpu": cpu_latency,
        },
        "elapsed_s": elapsed_s,
        "notes": [
            "False clear means actual class is not bold but prediction is bold.",
            "This experiment does not promote a runtime model.",
            "CPU latency is measured after moving the trained model to CPU.",
        ],
    }
    torch.save(best_state, output_dir / "models/mobilenet_v3_small_best.pt")
    write_json(output_dir / "metrics/summary.json", summary)
    write_report(output_dir / "metrics/report.md", summary)
    write_confusion_csv(output_dir / "metrics/test_confusion.csv", test_metrics["confusion"], CLASS_NAMES)
    write_predictions_csv(output_dir / "metrics/test_predictions.csv", test_preds)
    print(json.dumps(summary, indent=2), flush=True)


def resolve_path(path: Path) -> Path:
    """Resolve relative paths against the repo root."""

    return path if path.is_absolute() else ROOT / path


def configure_reproducibility(seed: int) -> None:
    """Set deterministic-ish seeds while allowing fast cuDNN kernels."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def choose_device(requested: str) -> torch.device:
    """Choose the training device."""

    if requested == "cuda":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_manifest(path: Path) -> dict[str, list[ImageRow]]:
    """Load audit-v6 rows grouped by split."""

    rows_by_split: dict[str, list[ImageRow]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row["boldness_label"]
            if label not in CLASS_NAMES:
                raise ValueError(f"Unexpected boldness_label={label!r}")
            item = ImageRow(
                split=row["split"],
                sample_id=row["sample_id"],
                crop_path=row["crop_path"],
                boldness_label=label,
                source_kind=row["source_kind"],
                source_origin=row["source_origin"],
                ttb_id=row["ttb_id"],
            )
            rows_by_split[item.split].append(item)
    for split in ("train", "validation", "test"):
        if not rows_by_split.get(split):
            raise ValueError(f"Missing split rows: {split}")
    return dict(rows_by_split)


def build_loaders(
    audit_dir: Path,
    rows_by_split: dict[str, list[ImageRow]],
    args: argparse.Namespace,
) -> tuple[DataLoader, DataLoader, DataLoader]:
    """Build train/validation/test loaders."""

    train_tf, eval_tf = build_transforms(args.image_size)
    train = AuditV6Dataset(audit_dir, rows_by_split["train"], transform=train_tf)
    validation = AuditV6Dataset(audit_dir, rows_by_split["validation"], transform=eval_tf)
    test = AuditV6Dataset(audit_dir, rows_by_split["test"], transform=eval_tf)
    return (
        DataLoader(train, batch_size=args.batch_size, shuffle=True, num_workers=args.workers, pin_memory=True),
        DataLoader(validation, batch_size=args.batch_size, shuffle=False, num_workers=args.workers, pin_memory=True),
        DataLoader(test, batch_size=args.batch_size, shuffle=False, num_workers=args.workers, pin_memory=True),
    )


def build_transforms(image_size: int) -> tuple[transforms.Compose, transforms.Compose]:
    """Create image transforms for transfer learning."""

    train_tf = transforms.Compose(
        [
            transforms.Grayscale(num_output_channels=3),
            transforms.Resize((image_size, image_size)),
            transforms.RandomApply([transforms.RandomAffine(degrees=4, translate=(0.02, 0.02), shear=2)], p=0.35),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.8))], p=0.15),
            transforms.ColorJitter(brightness=0.12, contrast=0.18),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )
    eval_tf = transforms.Compose(
        [
            transforms.Grayscale(num_output_channels=3),
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )
    return train_tf, eval_tf


class AuditV6Dataset(Dataset):
    """Torch dataset for audit-v6 image crops."""

    def __init__(self, audit_dir: Path, rows: list[ImageRow], transform: transforms.Compose):
        self.audit_dir = audit_dir
        self.rows = rows
        self.transform = transform
        self.class_to_idx = {name: idx for idx, name in enumerate(CLASS_NAMES)}

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self.rows[idx]
        image = Image.open(self.audit_dir / row.crop_path).convert("L")
        return {
            "image": self.transform(image),
            "label": torch.tensor(self.class_to_idx[row.boldness_label], dtype=torch.long),
            "sample_id": row.sample_id,
            "source_kind": row.source_kind,
            "source_origin": row.source_origin,
            "ttb_id": row.ttb_id,
        }


def build_model(*, class_count: int, weights: str) -> nn.Module:
    """Build MobileNetV3-Small with optional ImageNet transfer weights."""

    model_weights = None
    if weights == "imagenet":
        try:
            model_weights = models.MobileNet_V3_Small_Weights.DEFAULT
        except Exception:
            model_weights = None
    try:
        model = models.mobilenet_v3_small(weights=model_weights)
    except Exception as exc:
        if weights == "imagenet":
            print(f"ImageNet weights unavailable ({exc!r}); falling back to random initialization.", flush=True)
            model = models.mobilenet_v3_small(weights=None)
        else:
            raise
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, class_count)
    return model


def set_backbone_trainability(model: nn.Module, *, trainable: bool) -> None:
    """Freeze or unfreeze MobileNet features."""

    for parameter in model.features.parameters():
        parameter.requires_grad = trainable
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True


def class_weights(rows: list[ImageRow]) -> torch.Tensor:
    """Compute inverse-frequency class weights from training rows."""

    counts = Counter(row.boldness_label for row in rows)
    total = sum(counts.values())
    weights = [total / max(counts[name], 1) for name in CLASS_NAMES]
    weights = [weight / (sum(weights) / len(weights)) for weight in weights]
    return torch.tensor(weights, dtype=torch.float32)


def run_train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> dict[str, float]:
    """Train one epoch."""

    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        labels = batch["label"].to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += float(loss.item()) * labels.numel()
        pred = logits.argmax(dim=1)
        correct += int((pred == labels).sum().item())
        total += int(labels.numel())
    return {
        "loss": total_loss / max(total, 1),
        "accuracy": correct / max(total, 1),
        "examples": total,
    }


@torch.inference_mode()
def run_inference(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, list[Any]]:
    """Run inference and collect predictions plus provenance."""

    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    y_prob_bold: list[float] = []
    sample_ids: list[str] = []
    source_kinds: list[str] = []
    source_origins: list[str] = []
    ttb_ids: list[str] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        labels = batch["label"].to(device, non_blocking=True)
        logits = model(images)
        probs = torch.softmax(logits, dim=1)
        pred = probs.argmax(dim=1)
        y_true.extend(labels.cpu().tolist())
        y_pred.extend(pred.cpu().tolist())
        y_prob_bold.extend(probs[:, 0].cpu().tolist())
        sample_ids.extend(batch["sample_id"])
        source_kinds.extend(batch["source_kind"])
        source_origins.extend(batch["source_origin"])
        ttb_ids.extend(batch["ttb_id"])
    return {
        "y_true": y_true,
        "y_pred": y_pred,
        "y_prob_bold": y_prob_bold,
        "sample_id": sample_ids,
        "source_kind": source_kinds,
        "source_origin": source_origins,
        "ttb_id": ttb_ids,
    }


def compute_metrics(y_true: list[int], y_pred: list[int], class_names: tuple[str, ...]) -> dict[str, Any]:
    """Compute multiclass metrics and false-clear safety metric."""

    true = np.array(y_true)
    pred = np.array(y_pred)
    labels = list(range(len(class_names)))
    precision, recall, f1, support = precision_recall_fscore_support(
        true,
        pred,
        labels=labels,
        zero_division=0,
    )
    macro = precision_recall_fscore_support(true, pred, average="macro", zero_division=0)
    weighted = precision_recall_fscore_support(true, pred, average="weighted", zero_division=0)
    positive_idx = class_names.index(POSITIVE_CLASS)
    false_clear_denominator = true != positive_idx
    false_clear_rate = float(((pred == positive_idx) & false_clear_denominator).sum() / max(false_clear_denominator.sum(), 1))
    return {
        "accuracy": float((true == pred).mean()),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
        "false_clear_rate": false_clear_rate,
        "per_class": {
            class_name: {
                "precision": float(precision[idx]),
                "recall": float(recall[idx]),
                "f1": float(f1[idx]),
                "support": int(support[idx]),
            }
            for idx, class_name in enumerate(class_names)
        },
        "confusion": confusion_matrix(true, pred, labels=labels).astype(int).tolist(),
        "examples": int(len(true)),
    }


def compute_group_breakdowns(preds: dict[str, list[Any]], class_names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Compute metrics by source provenance groups."""

    result: dict[str, dict[str, Any]] = {}
    for group_name in ("source_kind", "source_origin"):
        by_group: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"true": [], "pred": []})
        for idx, group_value in enumerate(preds[group_name]):
            by_group[group_value]["true"].append(preds["y_true"][idx])
            by_group[group_value]["pred"].append(preds["y_pred"][idx])
        result[group_name] = {
            group: compute_metrics(values["true"], values["pred"], class_names)
            for group, values in sorted(by_group.items())
        }
    return result


@torch.inference_mode()
def measure_latency(model: nn.Module, loader: DataLoader, device: torch.device, *, rows: int) -> dict[str, float | int]:
    """Measure inference latency on a device."""

    model.eval()
    images = collect_latency_images(loader, rows).to(device)
    for _ in range(5):
        _ = model(images)
    if device.type == "cuda":
        torch.cuda.synchronize()
    started = time.perf_counter()
    _ = model(images)
    if device.type == "cuda":
        torch.cuda.synchronize()
    batch_ms = (time.perf_counter() - started) * 1000
    single_times: list[float] = []
    for image in images[: min(64, images.shape[0])]:
        if device.type == "cuda":
            torch.cuda.synchronize()
        started = time.perf_counter()
        _ = model(image.unsqueeze(0))
        if device.type == "cuda":
            torch.cuda.synchronize()
        single_times.append((time.perf_counter() - started) * 1000)
    return {
        "rows": int(images.shape[0]),
        "batch_ms_per_crop": float(batch_ms / max(images.shape[0], 1)),
        "single_row_mean_ms": float(np.mean(single_times)) if single_times else 0.0,
        "single_row_p95_ms": float(np.percentile(single_times, 95)) if single_times else 0.0,
        "single_row_max_ms": float(np.max(single_times)) if single_times else 0.0,
    }


def measure_cpu_latency(model: nn.Module, loader: DataLoader, *, rows: int) -> dict[str, float | int]:
    """Measure CPU inference latency after copying the trained model to CPU."""

    cpu_model = build_model(class_count=len(CLASS_NAMES), weights="none")
    cpu_model.load_state_dict({key: value.detach().cpu() for key, value in model.state_dict().items()})
    cpu_model.eval()
    return measure_latency(cpu_model, loader, torch.device("cpu"), rows=rows)


def collect_latency_images(loader: DataLoader, rows: int) -> torch.Tensor:
    """Collect a small tensor batch from a loader for latency checks."""

    chunks: list[torch.Tensor] = []
    total = 0
    for batch in loader:
        images = batch["image"]
        chunks.append(images)
        total += images.shape[0]
        if total >= rows:
            break
    return torch.cat(chunks, dim=0)[:rows]


def write_confusion_csv(path: Path, matrix: list[list[int]], class_names: tuple[str, ...]) -> None:
    """Write confusion matrix as CSV."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual", *class_names])
        for idx, row in enumerate(matrix):
            writer.writerow([class_names[idx], *row])


def write_predictions_csv(path: Path, preds: dict[str, list[Any]]) -> None:
    """Write test predictions for error inspection."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sample_id",
                "actual",
                "predicted",
                "prob_bold",
                "source_kind",
                "source_origin",
                "ttb_id",
            ],
        )
        writer.writeheader()
        for idx, sample_id in enumerate(preds["sample_id"]):
            writer.writerow(
                {
                    "sample_id": sample_id,
                    "actual": CLASS_NAMES[preds["y_true"][idx]],
                    "predicted": CLASS_NAMES[preds["y_pred"][idx]],
                    "prob_bold": f"{preds['y_prob_bold'][idx]:.8f}",
                    "source_kind": preds["source_kind"][idx],
                    "source_origin": preds["source_origin"][idx],
                    "ttb_id": preds["ttb_id"][idx],
                }
            )


def write_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a compact Markdown report."""

    test = summary["test"]
    gpu = summary["latency"]["gpu"]
    cpu = summary["latency"]["cpu"]
    rows = [
        f"| Accuracy | {test['accuracy']:.4f} |",
        f"| Macro F1 | {test['macro_f1']:.4f} |",
        f"| Weighted F1 | {test['weighted_f1']:.4f} |",
        f"| False-clear rate | {test['false_clear_rate']:.6f} |",
    ]
    per_class = [
        f"| {name} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1']:.4f} | {metrics['support']} |"
        for name, metrics in test["per_class"].items()
    ]
    path.write_text(
        f"""# Audit-v6 CNN Boldness Classifier

Model: `{summary['model']}`  
Weights: `{summary['weights']}`  
Best epoch: `{summary['best_epoch']}`  

## Test Metrics

| Metric | Value |
|---|---:|
{chr(10).join(rows)}

False clear means an actual non-bold, unreadable, or not-applicable image was
predicted as `bold`.

## Per-Class Test Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
{chr(10).join(per_class)}

## Latency

| Device | Batch ms/crop | Single mean ms | Single p95 ms |
|---|---:|---:|---:|
| GPU | {gpu['batch_ms_per_crop']:.4f} | {gpu['single_row_mean_ms']:.4f} | {gpu['single_row_p95_ms']:.4f} |
| CPU | {cpu['batch_ms_per_crop']:.4f} | {cpu['single_row_mean_ms']:.4f} | {cpu['single_row_p95_ms']:.4f} |

## Decision

This is an offline challenger result. Runtime promotion requires comparison
against the existing real-adapted logistic preflight and a policy threshold
tuned for false-clear safety.
""",
        encoding="utf-8",
    )


def write_json(path: Path, payload: object) -> None:
    """Write stable pretty JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
