#!/usr/bin/env python
"""Train/evaluate a graph-aware OCR evidence scorer.

This is an experimental proof of concept. It trains on cached local OCR outputs
under ``data/work/public-cola`` and writes all model artifacts/metrics under
gitignored ``data/work/graph-ocr``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import torch
    from torch import nn
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local ML env.
    raise SystemExit(
        "PyTorch is required for this experiment. On this Fedora host, run it "
        "inside the existing app image:\n\n"
        "podman run --rm -v \"$PWD:/workspace:Z\" -w /workspace "
        "localhost/labels-on-tap-app:local "
        "python experiments/graph_ocr/train_graph_matcher.py\n"
    ) from exc

from experiments.graph_ocr.features import (
    FIELDS,
    build_examples,
    examples_to_feature_graphs,
    read_ttb_ids,
    split_ids,
)
from experiments.graph_ocr.model import GraphEvidenceScorer


DEFAULT_TTB_ID_FILE = (
    REPO_ROOT / "data/work/cola/official-sample-1500-balanced/api/selected-detail-ttb-ids.txt"
)
WORK_ROOT = REPO_ROOT / "data/work/graph-ocr"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id-file", type=Path, default=DEFAULT_TTB_ID_FILE)
    parser.add_argument("--run-name", default="calibration-100-poc")
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.10)
    parser.add_argument("--learning-rate", type=float, default=2e-3)
    parser.add_argument("--negative-per-positive", type=int, default=3)
    parser.add_argument(
        "--negative-loss-weight",
        type=float,
        default=1.0,
        help="Loss multiplier for shuffled negative examples; higher values punish false clears.",
    )
    parser.add_argument(
        "--false-clear-tolerance",
        type=float,
        default=0.0,
        help="Allowed dev false-clear increase over baseline when tuning the graph threshold.",
    )
    parser.add_argument("--max-nodes", type=int, default=192)
    parser.add_argument("--knn-k", type=int, default=5)
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    return parser.parse_args()


def output_dir(run_name: str) -> Path:
    """Return/create the gitignored output directory for one experiment run."""

    path = WORK_ROOT / run_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def choose_device(value: str) -> torch.device:
    """Return the requested torch device."""

    if value == "cuda":
        if not torch.cuda.is_available():
            raise SystemExit("CUDA was explicitly requested, but torch.cuda.is_available() is false.")
        return torch.device("cuda")
    if value == "auto" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def set_seed(seed: int) -> None:
    """Seed Python and PyTorch RNGs."""

    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def tensor_graph(
    graph: dict,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Convert one graph dictionary to PyTorch tensors."""

    x = torch.tensor(graph["x"], dtype=torch.float32, device=device)
    adj = torch.tensor(graph["adj"], dtype=torch.float32, device=device)
    summary_x = torch.tensor(graph["summary_x"], dtype=torch.float32, device=device)
    y = torch.tensor(float(graph["label"]), dtype=torch.float32, device=device)
    return x, adj, summary_x, y


def graph_logit(model: GraphEvidenceScorer, graph: dict, device: torch.device) -> torch.Tensor:
    """Run one graph through the model."""

    x, adj, summary_x, _ = tensor_graph(graph, device)
    return model(x, adj, summary_x)


def baseline_prediction(score: float, threshold: float = 90.0) -> int:
    """Return baseline support prediction from fuzzy score."""

    return int(score >= threshold)


def metrics_from_predictions(rows: list[dict], *, score_key: str, threshold: float) -> dict:
    """Compute binary support metrics for predictions."""

    tp = fp = tn = fn = 0
    for row in rows:
        label = int(row["label"])
        prediction = int(float(row[score_key]) >= threshold)
        if label == 1 and prediction == 1:
            tp += 1
        elif label == 0 and prediction == 1:
            fp += 1
        elif label == 0 and prediction == 0:
            tn += 1
        else:
            fn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / max(len(rows), 1)
    false_clear = fp / (fp + tn) if fp + tn else 0.0
    return {
        "threshold": threshold,
        "count": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall_positive_support": round(recall, 4),
        "specificity_negative_rejection": round(specificity, 4),
        "f1": round(f1, 4),
        "false_clear_rate": round(false_clear, 4),
    }


def tune_threshold(rows: list[dict], *, max_false_clear: float) -> float:
    """Tune a graph threshold on dev predictions under a false-clear cap."""

    best_threshold = 0.50
    best_score = -1.0
    fallback_threshold = 0.50
    fallback_score = -1.0
    for index in range(5, 96):
        threshold = index / 100.0
        metrics = metrics_from_predictions(rows, score_key="graph_score", threshold=threshold)
        score = metrics["f1"] + 0.25 * metrics["specificity_negative_rejection"]
        fallback_candidate = -metrics["false_clear_rate"] + 0.10 * metrics["f1"]
        if fallback_candidate > fallback_score:
            fallback_score = fallback_candidate
            fallback_threshold = threshold
        if metrics["false_clear_rate"] > max_false_clear:
            continue
        if score > best_score:
            best_score = score
            best_threshold = threshold
    return best_threshold if best_score >= 0 else fallback_threshold


def evaluate_rows(
    *,
    model: GraphEvidenceScorer,
    graphs: list[dict],
    device: torch.device,
    split_name: str,
) -> list[dict]:
    """Return prediction rows for one split."""

    model.eval()
    rows: list[dict] = []
    with torch.no_grad():
        for graph in graphs:
            logit = graph_logit(model, graph, device)
            score = torch.sigmoid(logit).item()
            rows.append(
                {
                    "split": split_name,
                    "ttb_id": graph["ttb_id"],
                    "field_name": graph["field_name"],
                    "expected": graph["expected"],
                    "label": graph["label"],
                    "source_ttb_id": graph["source_ttb_id"],
                    "node_count": graph["node_count"],
                    "baseline_score": round(float(graph["baseline_score"]), 4),
                    "baseline_prediction": baseline_prediction(float(graph["baseline_score"])),
                    "graph_score": round(score, 6),
                }
            )
    return rows


def positive_field_support(rows: list[dict], *, graph_threshold: float) -> dict[str, dict]:
    """Summarize positive-example support by field."""

    summary: dict[str, dict] = {}
    for field_name in FIELDS:
        field_rows = [row for row in rows if row["field_name"] == field_name and int(row["label"]) == 1]
        if not field_rows:
            continue
        baseline_hits = sum(1 for row in field_rows if int(row["baseline_prediction"]) == 1)
        graph_hits = sum(1 for row in field_rows if float(row["graph_score"]) >= graph_threshold)
        summary[field_name] = {
            "positive_count": len(field_rows),
            "baseline_support_rate": round(baseline_hits / len(field_rows), 4),
            "graph_support_rate": round(graph_hits / len(field_rows), 4),
            "delta": round((graph_hits - baseline_hits) / len(field_rows), 4),
        }
    return summary


def write_predictions(path: Path, rows: list[dict]) -> None:
    """Write prediction rows to CSV."""

    fieldnames = [
        "split",
        "ttb_id",
        "field_name",
        "expected",
        "label",
        "source_ttb_id",
        "node_count",
        "baseline_score",
        "baseline_prediction",
        "graph_score",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Train the graph-aware OCR evidence proof of concept."""

    args = parse_args()
    set_seed(args.seed)
    device = choose_device(args.device)
    run_dir = output_dir(args.run_name)

    ttb_ids = read_ttb_ids(args.ttb_id_file)
    splits = split_ids(ttb_ids, seed=args.seed)
    examples = build_examples(
        ttb_ids=ttb_ids,
        negative_per_positive=args.negative_per_positive,
        seed=args.seed,
    )
    graphs = examples_to_feature_graphs(examples, max_nodes=args.max_nodes, knn_k=args.knn_k)
    split_graphs = {
        split: [graph for graph in graphs if graph["ttb_id"] in split_ids]
        for split, split_ids in splits.items()
    }
    input_dim = len(graphs[0]["x"][0])
    summary_dim = len(graphs[0]["summary_x"])
    model = GraphEvidenceScorer(
        input_dim=input_dim,
        summary_dim=summary_dim,
        hidden_dim=args.hidden_dim,
        layers=args.layers,
        dropout=args.dropout,
    ).to(device)

    train_graphs = split_graphs["train"]
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)

    history: list[dict] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        random.shuffle(train_graphs)
        losses: list[float] = []
        for graph in train_graphs:
            x, adj, summary_x, y = tensor_graph(graph, device)
            optimizer.zero_grad()
            raw_loss = loss_fn(model(x, adj, summary_x).view(1), y.view(1))
            weight = args.negative_loss_weight if int(graph["label"]) == 0 else 1.0
            loss = raw_loss.mean() * weight
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        history.append({"epoch": epoch, "train_loss": round(mean(losses), 6)})
        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(f"epoch {epoch:03d} loss={history[-1]['train_loss']:.4f}")

    dev_rows = evaluate_rows(model=model, graphs=split_graphs["dev"], device=device, split_name="dev")
    dev_baseline_metrics = metrics_from_predictions(dev_rows, score_key="baseline_score", threshold=90.0)
    max_false_clear = dev_baseline_metrics["false_clear_rate"] + args.false_clear_tolerance
    graph_threshold = tune_threshold(dev_rows, max_false_clear=max_false_clear)
    all_rows = []
    for split_name in ("train", "dev", "test"):
        all_rows.extend(
            evaluate_rows(
                model=model,
                graphs=split_graphs[split_name],
                device=device,
                split_name=split_name,
            )
        )

    test_rows = [row for row in all_rows if row["split"] == "test"]
    baseline_metrics = metrics_from_predictions(test_rows, score_key="baseline_score", threshold=90.0)
    graph_metrics = metrics_from_predictions(test_rows, score_key="graph_score", threshold=graph_threshold)
    summary = {
        "run_name": args.run_name,
        "seed": args.seed,
        "device": str(device),
        "input_dim": input_dim,
        "summary_dim": summary_dim,
        "model": {
            "hidden_dim": args.hidden_dim,
            "layers": args.layers,
            "dropout": args.dropout,
            "learning_rate": args.learning_rate,
            "epochs": args.epochs,
            "negative_loss_weight": args.negative_loss_weight,
            "false_clear_tolerance": args.false_clear_tolerance,
        },
        "data": {
            "application_count": len(ttb_ids),
            "example_count": len(graphs),
            "positive_examples": sum(1 for graph in graphs if graph["label"] == 1),
            "negative_examples": sum(1 for graph in graphs if graph["label"] == 0),
            "split_application_counts": {split: len(ids) for split, ids in splits.items()},
            "split_example_counts": {split: len(items) for split, items in split_graphs.items()},
        },
        "thresholds": {
            "baseline": 90.0,
            "graph": graph_threshold,
            "graph_tuned_to_dev_false_clear_cap": max_false_clear,
        },
        "dev_metrics": {
            "baseline": dev_baseline_metrics,
            "graph": metrics_from_predictions(dev_rows, score_key="graph_score", threshold=graph_threshold),
        },
        "test_metrics": {
            "baseline": baseline_metrics,
            "graph": graph_metrics,
        },
        "positive_field_support_test": positive_field_support(test_rows, graph_threshold=graph_threshold),
        "history": history,
    }

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_predictions(run_dir / "predictions.csv", all_rows)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "summary": summary,
        },
        run_dir / "model.pt",
    )
    (run_dir / "config.json").write_text(
        json.dumps({**vars(args), "ttb_id_file": str(args.ttb_id_file)}, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"wrote {run_dir}")
    print(json.dumps(summary["test_metrics"], indent=2))
    print(json.dumps(summary["positive_field_support_test"], indent=2))


if __name__ == "__main__":
    main()
