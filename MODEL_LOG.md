# MODEL_LOG.md - OCR And Graph Evidence Experiments

**Project:** Labels On Tap
**Canonical URL:** `https://www.labelsontap.ai`
**Last updated:** May 2, 2026

This log records OCR, field-matching, and graph-aware evidence experiments. It is intentionally conservative: calibration results are not production claims, and anything not evaluated on a locked holdout stays labeled as experimental.

## Evaluation Posture

The product is designed to triage applications that may be out of compliance. The most important failure mode is a false clear: a problematic or mismatched example marked as safe/pass.

For model experiments, improvement only counts if it respects that posture:

```text
Good:
  higher field-support recall
  lower or unchanged false-clear rate
  clear provenance and repeatable run command

Not good enough:
  higher recall by accepting many bad shuffled negatives
  hidden threshold tuning on test data
  production claims from calibration data
```

As sample size grows, measured performance should be expected to move closer to the true value. That may make the numbers look less flattering. That is not a failure; it is the point of the evaluation design. The project should prefer honest lower-confidence claims over a polished but fragile demo metric.

## Current Data Sources

| Source | Purpose | Runtime Dependency | Current State |
|---|---|---:|---|
| Synthetic fixtures | Deterministic demo and known-bad checks | No | Committed under `data/fixtures/demo/` |
| TTB Public COLA Registry ETL | Official printable-form path and parser | No | `810` parsed forms, direct attachment endpoint was unstable |
| COLA Cloud API | Development-only bridge for public label rasters | No | `1,500` selected records from `7,788` candidates |
| Cached docTR OCR | Baseline OCR box/text output | No | `100` applications, `169` label images |
| Local graph scorer | Experimental post-OCR evidence model | No | Best POC run improved F1 and false-clear rate |

All bulk/raw artifacts, OCR outputs, API responses, model checkpoints, and run outputs stay under gitignored `data/work/`.

## Experiment Ledger

### E001 - Remapped OCR Field-Matching Baseline

**Date:** May 2, 2026
**Run output:** `data/work/public-cola/parsed/ocr/evaluations/official-sample-1500-balanced-calibration-100-remapped/`
**Input:** 100 COLA Cloud public records, 169 cached local docTR OCR label images
**Purpose:** Establish the corrected baseline after mapping `abv`, `volume`, and `volume_unit`.

Command:

```bash
python scripts/evaluate_public_cola_ocr.py \
  --ttb-id-file data/work/cola/official-sample-1500-balanced/api/selected-detail-ttb-ids.txt \
  --run-name official-sample-1500-balanced-calibration-100-remapped \
  --cached-only
```

Field support:

| Field | Attempted | Matched | Match Rate |
|---|---:|---:|---:|
| Brand name | 100 | 71 | 0.7100 |
| Fanciful name | 100 | 65 | 0.6500 |
| Class/type | 100 | 49 | 0.4900 |
| Alcohol content | 94 | 86 | 0.9149 |
| Net contents | 86 | 72 | 0.8372 |
| Country of origin | 38 | 30 | 0.7895 |
| Applicant/producer | 100 | 2 | 0.0200 |

Notes:

- ABV and net contents became measurable only after detail mapping was fixed.
- Class/type remains weak even after synonym expansion.
- Applicant/producer is not reliable from current label OCR and should remain a review-only field.

### E002 - First Graph Scorer CPU Attempt

**Date:** May 2, 2026
**Run output:** `data/work/graph-ocr/calibration-100-poc/`
**Input:** Same 100-application calibration set
**Purpose:** Mechanical proof that OCR boxes can be converted to graph examples and trained.

Outcome:

- The first graph-only model collapsed to a constant score.
- It was not useful as a model result.
- This exposed the need for graph-level summary features and safety-constrained thresholding.

Decision:

- Do not use this run in reporting except as an engineering lesson.
- Keep the code path only after adding summary features and CUDA execution.

### E003 - GPU Smoke, 5 Epochs

**Date:** May 2, 2026
**Run output:** `data/work/graph-ocr/gpu-smoke-5/`
**Input:** Same 100-application calibration set
**Purpose:** Confirm the local RTX 4090 and CUDA PyTorch stack can train the graph scorer.

Command:

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 5 \
  --run-name gpu-smoke-5 \
  --device cuda
```

Result:

| Metric | Baseline | Graph |
|---|---:|---:|
| F1 | 0.7714 | 0.7895 |
| False-clear rate | 0.0439 | 0.0702 |

Decision:

- CUDA training works.
- Model signal exists.
- False clears increased, so this run is not acceptable for the product posture.

### E004 - Safety-Weighted Graph Scorer, Negative Weight 2.0

**Date:** May 2, 2026
**Run output:** `data/work/graph-ocr/gpu-safety-neg2-e40/`
**Input:** Same 100-application calibration set
**Purpose:** Test graph scoring with a higher loss penalty for shuffled negative examples and a dev-tuned false-clear cap.

Command:

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 40 \
  --run-name gpu-safety-neg2-e40 \
  --device cuda \
  --negative-loss-weight 2.0 \
  --false-clear-tolerance 0.0
```

Test split result:

| Metric | Baseline | Graph |
|---|---:|---:|
| Accuracy | 0.8947 | 0.9408 |
| Precision | 0.8438 | 0.9531 |
| Positive-support recall | 0.7105 | 0.8026 |
| Specificity / negative rejection | 0.9561 | 0.9868 |
| F1 | 0.7714 | 0.8714 |
| False-clear rate | 0.0439 | 0.0132 |

Positive field support:

| Field | Baseline | Graph | Delta |
|---|---:|---:|---:|
| Brand name | 0.8000 | 0.8667 | +0.0667 |
| Fanciful name | 0.5333 | 0.8667 | +0.3333 |
| Class/type | 0.4667 | 0.4667 | 0.0000 |
| Alcohol content | 0.9231 | 0.9231 | 0.0000 |
| Net contents | 0.8333 | 0.9167 | +0.0833 |
| Country of origin | 0.8333 | 0.8333 | 0.0000 |

Decision:

- This is the best current graph POC.
- It improves F1 and lowers false clears on shuffled negatives.
- It is still a 100-application calibration result, not a production claim.

### E005 - Safety-Weighted Graph Scorer, Negative Weight 3.0

**Date:** May 2, 2026
**Run output:** `data/work/graph-ocr/gpu-safety-neg3-e40/`
**Input:** Same 100-application calibration set
**Purpose:** Check whether stronger negative weighting improves safety further.

Command:

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 40 \
  --run-name gpu-safety-neg3-e40 \
  --device cuda \
  --negative-loss-weight 3.0 \
  --false-clear-tolerance 0.0
```

Test split result:

| Metric | Baseline | Graph |
|---|---:|---:|
| F1 | 0.7714 | 0.8333 |
| False-clear rate | 0.0439 | 0.0351 |

Decision:

- Still better than baseline.
- Weaker than E004.
- Keep E004 as the current best POC.

## Current Best Result

The current best graph-aware evidence result is `E004`, using:

```text
run_name: gpu-safety-neg2-e40
device: cuda
epochs: 40
negative_loss_weight: 2.0
false_clear_tolerance: 0.0
```

This result supports a careful claim:

> A first experimental graph-aware evidence scorer improved field-support classification on the 100-application calibration test split while lowering false clears on shuffled negative examples.

This result does not support a production claim:

> The app is production-ready or has final OCR accuracy.

## Known Limitations

- The current graph labels are weak labels from accepted application fields and shuffled negatives, not human-labeled OCR spans.
- The test split is drawn from the 100-application calibration set, not the planned locked 1,500 holdout.
- The graph scorer cannot recover text the OCR engine never detected.
- Class/type remains difficult and probably needs better product taxonomy handling, better OCR, or field-specific candidate generation.
- The current model processes variable-size graphs one at a time; batching/padding should be added before larger runs.
- GPU training works locally, but `.venv-gpu` is not part of the deployed app and is intentionally gitignored.

## Next Experiments

1. Scale graph training to the full 1,500-record calibration split once details/images/OCR are available.
2. Freeze graph settings after calibration and evaluate only once on the locked 1,500 holdout.
3. Add PaddleOCR as an alternate OCR engine and compare baseline docTR vs PaddleOCR vs combined OCR boxes.
4. Add field-specific class/type taxonomy features to attack the weakest measured field.
5. Preserve the full HO-GNN/TPS/SVTR roadmap as a future research path after post-OCR graph scoring is fully measured.

