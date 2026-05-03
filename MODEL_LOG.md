# MODEL_LOG.md - OCR And Graph Evidence Experiments

**Project:** Labels On Tap
**Canonical URL:** `https://www.labelsontap.ai`
**Last updated:** May 3, 2026

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
| COLA Cloud API | Development-only bridge for public label rasters | No | Source of current measured OCR/model calibration work; `6,000` unique applications and `10,435` local label images across two non-overlapping cohorts |
| Cached docTR OCR | Baseline OCR box/text output | No | `100` COLA Cloud-derived public applications, `169` label images |
| Local graph scorer | Experimental post-OCR evidence model | No | Best POC run improved F1 and false-clear rate |
| PaddleOCR sweep | Experimental alternate local OCR candidate | No | 30-image smoke improved F1/accuracy/recall, with higher false-clear rate |
| OpenOCR / SVTRv2 sweep | Experimental alternate local OCR candidate | No | 30-image smoke was fastest, with lower F1 in first field-support test |
| PARSeq crop recognizer | Experimental recognizer over detected crops | No | Fast on CPU, but lower field-support F1 in first crop-recognition smoke |
| ASTER crop recognizer | Experimental rectifying recognizer over detected crops | No | Very fast on CPU, zero false clears, but low recall/F1 in first crop-recognition smoke |
| FCENet + ASTER | Experimental arbitrary-shape detector plus recognizer | No | Successful run, but too slow on CPU and low F1 in first detector-recognizer smoke |
| ABINet crop recognizer | Experimental recognizer over detected crops | No | Fast on CPU, zero false clears, but low recall/F1 in first crop-recognition smoke |
| Deterministic OCR ensemble | Combines docTR, PaddleOCR, and OpenOCR field evidence | No | Government-safe smoke improved F1 to 0.7416 with zero shuffled-negative false clears |
| WineBERT/o domain NER | Experimental token-classification arbiter over OCR text | No | Fast CPU inference, but no lift over government-safe ensemble and unknown public model license |
| OSA market-domain NER | Experimental Apache-2.0 token-classification arbiter over OCR text | No | Small lift over government-safe ensemble: F1 0.7486, false-clear rate 0.0000 |
| FoodBaseBERT-NER | Culinary-domain token-classification control | No | Fast and MIT-licensed, but no lift over government-safe ensemble and standalone F1 0.0522 |
| OpenCV typography preflight | Warning-heading boldness classifier | Limited | Synthetic-only models were not promoted; real-adapted logistic boldness preflight is now runtime evidence with Needs Review fallback |

All bulk/raw artifacts, OCR outputs, API responses, model checkpoints, and run outputs stay under gitignored `data/work/`.

## Experiment Ledger

### E013 - OpenCV/SVM Government Warning Boldness Preflight

**Date added:** May 3, 2026
**Code path:** `experiments/typography_preflight/`
**Run output:** `data/work/typography-preflight/svm-v2/`
**Purpose:** Add a low-latency typography preflight for Jenny Park's requirement that `GOVERNMENT WARNING:` be bold, while keeping the current deployed rule conservative.

**May 3 correction:** Manual inspection found that the first `svm-v2` binary
target mixed source font weight, crop quality, and auto-clearance policy. That
made the score difficult to interpret: some visually bold crops were labeled
negative because they were degraded, and some readable medium/semibold crops
were routed to review even though the requirement is explicit bold type. Treat
the `svm-v2` numbers as a flawed-target baseline, not as a final verdict on
SVM viability.

**Corrected audit dataset:** `data/work/typography-preflight/audit-v5/`

The corrected generator is `experiments/typography_preflight/build_audit_dataset.py`.
It produces a human-inspection dataset with separate labels:

```text
font_weight_label             -> bold / not_bold
header_text_label             -> correct / incorrect
quality_label                 -> clean / mild / degraded
visual_font_decision_label    -> clearly_bold / clearly_not_bold / needs_review_unclear
header_decision_label         -> correct / incorrect / needs_review_unclear
```

`audit-v5` removes the source `borderline` font class. Generated bold fonts are
bold. Medium, semibold, demibold, light, thin, book, and regular fonts are not
bold for this regulatory target. `needs_review_unclear` is reserved for
unreadable/degraded crops that require a human to inspect or reject the
submission quality.

Current runtime behavior:

```text
GOV_WARNING_EXACT_TEXT          -> deterministic strict text check
GOV_WARNING_HEADER_CAPS         -> deterministic capitalization check
GOV_WARNING_HEADER_BOLD_REVIEW  -> real-adapted boldness preflight; Needs Review if uncertain
```

Model:

```text
heading crop
  -> OpenCV stroke/shape features
  -> StandardScaler
  -> Support Vector Machine
  -> bold / non-bold / uncertain decision
```

Synthetic dataset:

| Split | Planned Crops | Split Discipline |
|---|---:|---|
| Train | 20,000 | Training font families and distortion recipes |
| Validation | 5,000 | Held-out font families / distortion recipes |
| Test | 5,000 | Separate held-out font families and harder distortions |

Feature set:

```text
ink density
edge density
distance-transform mean stroke width
stroke-width variance
skeleton-to-ink ratio
connected-component statistics
projection profiles
HOG descriptors
```

Primary metric:

```text
false clear = regular, medium, degraded, or uncertain warning heading
classified as acceptable bold
```

Execution constraint used:

```text
CPU-only, low-priority, no GPU, no Podman changes, no writes to
data/work/ocr-conveyor/.
```

Run command:

```bash
CUDA_VISIBLE_DEVICES="" \
OMP_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
NUMEXPR_NUM_THREADS=2 \
nice -n 15 ionice -c3 \
data/work/typography-preflight/.venv/bin/python \
  -m experiments.typography_preflight.train_svm \
  --output-dir data/work/typography-preflight/svm-v2 \
  --classifier sgd-svm \
  --max-iter 2000 \
  --false-clear-tolerance 0.0025
```

Threshold sweep:

| Validation false-clear tolerance | Test F1 | Test precision | Test recall | Test false-clear rate |
|---:|---:|---:|---:|---:|
| 0.0000 | 0.0321 | 0.9737 | 0.0163 | 0.0004 |
| 0.0025 | 0.1170 | 0.8987 | 0.0626 | 0.0059 |
| 0.0050 | 0.1736 | 0.9008 | 0.0960 | 0.0088 |
| 0.0100 | 0.4492 | 0.9052 | 0.2987 | 0.0260 |
| 0.0200 | 0.5780 | 0.9027 | 0.4251 | 0.0381 |
| 0.0500 | 0.7757 | 0.8867 | 0.6894 | 0.0733 |

Latency:

```text
mean decision latency: about 0.09 ms/crop
```

Interpretation:

- The model class is computationally excellent.
- The first synthetic classifier used a noisy binary target and is not strong
  enough for autonomous boldness passing under a government false-clear posture.
- At the safest threshold, it false-clears almost nothing but passes almost no
  bold headings either.
- At useful recall/F1 thresholds, the false-clear rate is too high.
- Keep boldness as `Needs Review` for the submission.
- Next improvement is validation-threshold tuning on the side-by-side
  SVM/XGBoost/CatBoost comparison, then a positive smoke test against approved
  public COLA warning-heading crops if those crops can be isolated cleanly.

Reference:

```text
Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome.
The Elements of Statistical Learning: Data Mining, Inference, and Prediction.
2nd ed., Springer, 2009.
```

Decision:

- Do not promote to runtime Pass/Fail authority from this run.
- Approved public COLA crops may be used as positive smoke evidence only.
- Synthetic non-bold/degraded examples remain required for negative validation.
- Ambiguous typography remains `Needs Review`.

### E014 - SVM vs. XGBoost vs. CatBoost Typography Comparison

**Date added:** May 3, 2026
**Code path:** `experiments/typography_preflight/compare_models.py`
**Run output:** `data/work/typography-preflight/model-comparison-v1/`
**Purpose:** Compare three CPU-friendly classical/tabular model families on the
corrected `audit-v5` typography targets before deciding whether a boldness
preflight is worth promoting.

Dataset:

| Split | Crops |
|---|---:|
| Train | 6,000 |
| Validation | 1,500 |
| Test | 1,500 |

Targets:

| Target | Classes | False-clear definition |
|---|---|---|
| `visual_font_decision_label` | `clearly_bold`, `clearly_not_bold`, `needs_review_unclear` | non-bold or unreadable heading predicted as `clearly_bold` |
| `header_decision_label` | `correct`, `incorrect`, `needs_review_unclear` | incorrect or unreadable heading predicted as `correct` |

Test metrics:

| Task | Model | Accuracy | Macro F1 | Weighted F1 | False-Clear Rate | Batch ms/crop | Single-row ms |
|---|---|---:|---:|---:|---:|---:|---:|
| Visual font decision | SVM | 0.9400 | 0.9396 | 0.9396 | 0.0360 | 0.0048 | 0.0795 |
| Visual font decision | XGBoost | 0.9567 | 0.9567 | 0.9566 | 0.0551 | 0.0032 | 0.1151 |
| Visual font decision | CatBoost | 0.9480 | 0.9479 | 0.9478 | 0.0711 | 0.0054 | 1.9588 |
| Header text decision | SVM | 0.8420 | 0.8393 | 0.8392 | 0.1101 | 0.0055 | 0.0801 |
| Header text decision | XGBoost | 0.8560 | 0.8546 | 0.8544 | 0.1612 | 0.0033 | 0.1693 |
| Header text decision | CatBoost | 0.8447 | 0.8430 | 0.8428 | 0.1702 | 0.0059 | 1.9376 |

Interpretation:

- XGBoost is the raw accuracy/F1 winner.
- SVM is the false-clear and single-row latency winner.
- CatBoost does not currently justify its slower single-row prediction path in
  this numeric-feature experiment.
- None of the hard-argmax models is safe enough to become runtime authority.
  The next improvement is validation-threshold tuning so weak `clearly_bold` or
  `correct` predictions become `needs_review_unclear` instead of false clears.

Decision:

- Keep these synthetic-only models out of the deployed app.
- Treat the SVM and XGBoost results as viable candidates for a later thresholded
  typography preflight.
- Do not add XGBoost/CatBoost to runtime dependencies unless this layer is
  promoted behind a feature flag.

### E015 - Extended Typography 80/20 Comparison And Strict-Veto Ensemble

**Date added:** May 3, 2026
**Code path:** `experiments/typography_preflight/compare_extended_models.py`
**Run output:** `data/work/typography-preflight/model-comparison-extended-80-20-v1/`
**Purpose:** Compare SVM and XGBoost against LightGBM, Logistic Regression, MLP,
and a strict-veto ensemble using an 80/20 train/test split.

Dataset:

| Split | Crops |
|---|---:|
| Train | 8,000 |
| Test | 2,000 |

Test metrics:

| Task | Model | Accuracy | Macro F1 | False-Clear Rate | Batch ms/crop | Single-row ms |
|---|---|---:|---:|---:|---:|---:|
| Visual font decision | SVM | 0.9390 | 0.9385 | 0.0218 | 0.0048 | 0.0780 |
| Visual font decision | XGBoost | 0.9720 | 0.9720 | 0.0293 | 0.0034 | 0.1120 |
| Visual font decision | LightGBM | 0.9760 | 0.9760 | 0.0263 | 0.0115 | 1.9275 |
| Visual font decision | Logistic Regression | 0.9655 | 0.9656 | 0.0195 | 0.0048 | 0.0780 |
| Visual font decision | MLP | 0.9650 | 0.9650 | 0.0203 | 0.0076 | 0.1463 |
| Visual font decision | Strict-veto ensemble | 0.9115 | 0.9131 | 0.0038 | 0.0320 | 2.6810 |
| Header text decision | SVM | 0.8560 | 0.8539 | 0.0766 | 0.0041 | 0.0792 |
| Header text decision | XGBoost | 0.8845 | 0.8832 | 0.1404 | 0.0033 | 0.1144 |
| Header text decision | LightGBM | 0.8915 | 0.8911 | 0.1149 | 0.0136 | 1.8772 |
| Header text decision | Logistic Regression | 0.8815 | 0.8811 | 0.1231 | 0.0045 | 0.0789 |
| Header text decision | MLP | 0.8840 | 0.8841 | 0.0803 | 0.0071 | 0.1466 |
| Header text decision | Strict-veto ensemble | 0.7505 | 0.7510 | 0.0360 | 0.0338 | 2.7161 |

Strict-veto policy:

```text
positive class clears only when all base models predict positive
unanimous non-positive predictions are preserved
all disagreements route to needs_review_unclear
```

Interpretation:

- LightGBM is the raw-F1 winner.
- Logistic Regression and MLP are strong visual-font candidates, but Logistic
  Regression hit the configured iteration limit during the run and should not be
  treated as fully optimized.
- The strict-veto ensemble is the best safety posture because it sharply lowers
  false clears while preserving sub-3 ms single-crop CPU inference.
- The ensemble's lower F1 is expected: it creates a larger review queue.

Decision:

- Keep typography as reviewer-support evidence only.
- If this layer is promoted later, prefer the strict-veto policy or a
  validation-tuned reject option over a single hard-argmax model.

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
**Input:** Same COLA Cloud-derived 100-application calibration set
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
**Input:** Same COLA Cloud-derived 100-application calibration set
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
**Input:** Same COLA Cloud-derived 100-application calibration set
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
- It is still a COLA Cloud-derived 100-application calibration result, not a production claim.

### E005 - Safety-Weighted Graph Scorer, Negative Weight 3.0

**Date:** May 2, 2026
**Run output:** `data/work/graph-ocr/gpu-safety-neg3-e40/`
**Input:** Same COLA Cloud-derived 100-application calibration set
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

### E006 - PaddleOCR CPU Smoke Benchmark

**Date:** May 2, 2026
**Run output:** `data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json/`
**Input:** 30 real public COLA label images with matching cached docTR OCR
**Purpose:** Test whether PaddleOCR is a viable alternate local OCR engine for latency and extraction coverage before changing runtime architecture.

Environment:

```text
container: python:3.11-slim
paddlepaddle: 3.2.0
paddleocr: 3.3.3
models: PP-OCRv5 server detector + English mobile recognizer
runtime: CPU
```

Notes:

- The host Python is 3.14, so the smoke run used an isolated Python 3.11 container.
- PaddleOCR 3.5.0 with PaddlePaddle 3.3.1 installed but hit a known CPU oneDNN/PIR runtime error.
- Disabling MKLDNN allowed PaddleOCR 3.5.0 to run, but latency averaged about five seconds per image.
- Pinning to PaddleOCR 3.3.3 and PaddlePaddle 3.2.0 restored usable CPU latency.

Successful 30-image smoke result:

| Metric | PaddleOCR 3.3.3 / PaddlePaddle 3.2.0 |
|---|---:|
| Images processed | 30 |
| Error count | 0 |
| Mean latency | 1,105.00 ms/image |
| Median latency | 1,096.50 ms/image |
| Worst latency | 1,544 ms/image |
| Images under 1.5s | 29 / 30 |
| Mean confidence | 0.9346 |
| Mean text blocks | 20.8 |
| Mean extracted chars | 431.67 |

Cached docTR comparison on the same 30 images:

| Metric | docTR Cached Baseline | PaddleOCR Smoke |
|---|---:|---:|
| Mean latency | 800.53 ms/image | 1,105.00 ms/image |
| Median latency | 804.50 ms/image | 1,096.50 ms/image |
| Worst latency | 1,592 ms/image | 1,544 ms/image |
| Mean extracted chars | 436.00 | 431.67 |
| Mean text blocks | 79.3 | 20.8 |
| Images with more chars than other engine | 21 / 30 | 9 / 30 |

Decision:

- PaddleOCR is viable enough to keep testing; it nearly meets the 1.5-second local CPU target on this small smoke sample.
- PaddleOCR did not clearly extract more text than docTR by simple character count.
- Do not promote PaddleOCR to runtime default yet.
- Next step is field-level comparison, because fewer blocks may still produce cleaner text even when total character count is similar.

### E007 - PaddleOCR vs docTR Field-Support Metrics

**Date:** May 2, 2026
**Run output:** `data/work/ocr-engine-sweep/field-support-metrics/paddle-vs-doctr-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006
**Purpose:** Compare docTR and PaddleOCR as binary field-support classifiers rather than by raw extracted-character count.

Method:

```text
Positive examples:
  accepted application field value vs OCR text for the same TTB ID

Controlled negative examples:
  same-field values shuffled from other TTB IDs vs current OCR text

Prediction threshold:
  fuzzy field-support score >= 90
```

Overall result across all fields:

| Metric | docTR | PaddleOCR |
|---|---:|---:|
| Examples | 224 | 224 |
| Accuracy | 0.7455 | 0.7723 |
| Precision | 0.9825 | 0.9552 |
| Recall | 0.5000 | 0.5714 |
| Specificity | 0.9911 | 0.9732 |
| F1 | 0.6627 | 0.7151 |
| False-clear rate | 0.0089 | 0.0268 |

Excluding `applicant_or_producer`, which is already known to be a weak OCR evidence field:

| Metric | docTR | PaddleOCR |
|---|---:|---:|
| Examples | 184 | 184 |
| Accuracy | 0.7989 | 0.8315 |
| Precision | 0.9825 | 0.9552 |
| Recall | 0.6087 | 0.6957 |
| Specificity | 0.9891 | 0.9674 |
| F1 | 0.7517 | 0.8050 |
| False-clear rate | 0.0109 | 0.0326 |

Decision:

- PaddleOCR improves recall, accuracy, and F1 on this small field-support task.
- docTR is safer on precision, specificity, and false-clear rate.
- PaddleOCR should not replace docTR as the default yet, but it is not rejected.
- The next practical path is combined evidence with field-specific safety thresholds, especially for alcohol content where PaddleOCR false clears were higher.
- Small sample sizes increase variance. This 20-application / 30-image smoke is directional only; the F1 gap is promising but not stable enough to declare a final OCR winner.

### E008 - OpenOCR / SVTRv2 CPU Smoke Benchmark

**Date:** May 3, 2026
**Run output:** `data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30/`
**Field-support output:** `data/work/ocr-engine-sweep/field-support-metrics/doctr-vs-paddle-vs-openocr-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006 and E007
**Purpose:** Test OpenOCR/SVTRv2, the research-backed curved/irregular-text candidate, against docTR and PaddleOCR using the same normalized OCR schema and field-support metric.

Environment:

```text
container: python:3.11-slim
openocr-python: 0.1.5
backend: ONNX
mode: mobile
det_box_type: poly
runtime: CPU
```

OpenOCR timing / extraction smoke:

| Metric | OpenOCR / SVTRv2 |
|---|---:|
| Images processed | 30 |
| Error count | 0 |
| Mean latency | 563.77 ms/image |
| Median latency | 582.50 ms/image |
| Worst latency | 1,211 ms/image |
| Mean confidence | 0.9356 |
| Mean text blocks | 20.0 |
| Mean extracted chars | 376.63 |

Overall field-support result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR |
|---|---:|---:|---:|
| Examples | 224 | 224 | 224 |
| Accuracy | 0.7455 | 0.7723 | 0.7143 |
| Precision | 0.9825 | 0.9552 | 0.9800 |
| Recall | 0.5000 | 0.5714 | 0.4375 |
| Specificity | 0.9911 | 0.9732 | 0.9911 |
| F1 | 0.6627 | 0.7151 | 0.6049 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 |

Excluding `applicant_or_producer`:

| Metric | docTR | PaddleOCR | OpenOCR |
|---|---:|---:|---:|
| Accuracy | 0.7989 | 0.8315 | 0.7609 |
| Precision | 0.9825 | 0.9552 | 0.9800 |
| Recall | 0.6087 | 0.6957 | 0.5326 |
| Specificity | 0.9891 | 0.9674 | 0.9891 |
| F1 | 0.7517 | 0.8050 | 0.6901 |
| False-clear rate | 0.0109 | 0.0326 | 0.0109 |

Decision:

- OpenOCR is operationally interesting because it is very fast on this CPU smoke and supports a polygon detection mode.
- It did not beat docTR or PaddleOCR on F1 in this first small field-support test.
- It matched docTR's low false-clear rate in the shuffled-negative smoke.
- It remains a candidate for larger samples and possible supplemental evidence, but the current evidence does not justify replacing docTR or PaddleOCR.
- Small sample sizes increase variance; this is a calibration checkpoint, not a final engine selection.

### E009 - PARSeq Recognition Over OpenOCR Crops

**Date:** May 3, 2026
**Autoregressive run output:** `data/work/ocr-engine-sweep/parseq-openocr-crops-ar-smoke-30/`
**Non-autoregressive run output:** `data/work/ocr-engine-sweep/parseq-openocr-crops-nar-r2-smoke-30/`
**Field-support output:** `data/work/ocr-engine-sweep/field-support-metrics/doctr-vs-paddle-vs-openocr-vs-parseq-ar-nar-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006-E008
**Purpose:** Test PARSeq, a scene-text recognizer for irregular text, while keeping the evaluation honest about the fact that PARSeq is not a full detector-plus-recognizer label OCR pipeline by itself.

Method:

```text
1. Reuse OpenOCR-detected text boxes from E008.
2. Crop each detected box with small padding.
3. Run PARSeq recognition on the crops.
4. Aggregate recognized crop text by original label image and TTB ID.
5. Score field support with the same shuffled-negative metric.
```

Environment:

```text
container: python:3.11-slim
model source: torch.hub baudm/parseq
runtime: CPU
box source: OpenOCR 0.1.5 / SVTRv2 smoke output
AR run: decode_ar=true, refine_iters=1
NAR run: decode_ar=false, refine_iters=2
```

Timing / extraction smoke:

| Metric | PARSeq AR Crops | PARSeq NAR/refine-2 Crops |
|---|---:|---:|
| Images processed | 30 | 30 |
| Error count | 0 | 0 |
| Mean latency | 293.47 ms/image | 215.17 ms/image |
| Median latency | 212.00 ms/image | 168.50 ms/image |
| Worst latency | 870 ms/image | 655 ms/image |
| Mean confidence | 0.9519 | 0.9158 |
| Mean crop count | 20.0 | 20.0 |
| Mean extracted chars | 303.37 | 325.50 |

Overall field-support result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR | PARSeq AR | PARSeq NAR |
|---|---:|---:|---:|---:|---:|
| Accuracy | 0.7455 | 0.7723 | 0.7143 | 0.6875 | 0.6875 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 0.9773 | 0.9773 |
| Recall | 0.5000 | 0.5714 | 0.4375 | 0.3839 | 0.3839 |
| Specificity | 0.9911 | 0.9732 | 0.9911 | 0.9911 | 0.9911 |
| F1 | 0.6627 | 0.7151 | 0.6049 | 0.5513 | 0.5513 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 | 0.0089 | 0.0089 |

Decision:

- PARSeq did not fail the CPU latency concern in this crop-recognition setup. Even autoregressive decoding stayed well below the five-second target.
- PARSeq did not improve field-support F1 when paired with OpenOCR boxes and rectangular crop extraction.
- The result should not be read as "PARSeq is bad." It means this quick crop contract is not better than current full OCR candidates.
- A fairer future test would pair PARSeq with a detector/rectifier that produces high-quality word/line crops, or test MMOCR's detector-plus-PARSeq recipe if the dependency stack is acceptable.
- Small sample sizes increase variance, but this first result does not justify promoting PARSeq over PaddleOCR/OpenOCR/docTR.

### E010 - ASTER Recognition Over OpenOCR Crops

**Date:** May 3, 2026
**Run output:** `data/work/ocr-engine-sweep/aster-openocr-crops-smoke-30/`
**Field-support output:** `data/work/ocr-engine-sweep/field-support-metrics/doctr-vs-paddle-vs-openocr-vs-parseq-vs-aster-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006-E009
**Purpose:** Test ASTER, an attentional scene-text recognizer with flexible rectification, because it directly targets warped/irregular text crops.

Method:

```text
1. Reuse OpenOCR-detected text boxes from E008.
2. Crop each detected box with small padding.
3. Run MMOCR ASTER recognition on the crops.
4. Aggregate recognized crop text by original label image and TTB ID.
5. Score field support with the same shuffled-negative metric.
```

Environment:

```text
container: python:3.10-slim
model source: MMOCR 1.0.1 TextRecInferencer(model="ASTER")
runtime: CPU
box source: OpenOCR 0.1.5 / SVTRv2 smoke output
dependency pins: torch 2.0.1 CPU, mmcv 2.0.1, mmdet 3.0.0, numpy<2
```

Timing / extraction smoke:

| Metric | ASTER Crops |
|---|---:|
| Images processed | 30 |
| Error count | 0 |
| Mean latency | 119.87 ms/image |
| Median latency | 111.00 ms/image |
| Worst latency | 275 ms/image |
| Mean confidence | 0.7663 |
| Mean crop count | 20.0 |
| Mean extracted chars | 281.43 |

Overall field-support result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR | PARSeq AR | PARSeq NAR | ASTER |
|---|---:|---:|---:|---:|---:|---:|
| Accuracy | 0.7455 | 0.7723 | 0.7143 | 0.6875 | 0.6875 | 0.6920 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 0.9773 | 0.9773 | 1.0000 |
| Recall | 0.5000 | 0.5714 | 0.4375 | 0.3839 | 0.3839 | 0.3839 |
| Specificity | 0.9911 | 0.9732 | 0.9911 | 0.9911 | 0.9911 | 1.0000 |
| F1 | 0.6627 | 0.7151 | 0.6049 | 0.5513 | 0.5513 | 0.5548 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 | 0.0089 | 0.0089 | 0.0000 |

Decision:

- ASTER is the fastest recognizer-stage experiment so far over OpenOCR crops.
- ASTER produced zero false clears in this small smoke, which is attractive for the conservative product posture.
- ASTER recall and F1 were still lower than docTR and PaddleOCR, so it is not promoted as the default OCR path.
- The result does not invalidate ASTER; it says this quick OpenOCR-box + rectangular-crop contract did not recover more field evidence.
- A fairer future test would use ASTER in an end-to-end MMOCR detector-plus-recognizer pipeline or with better rotated/curved crop generation.
- Small sample sizes increase variance, so this remains directional calibration evidence.

### E011 - FCENet Detection Plus ASTER Recognition

**Date:** May 3, 2026
**Run output:** `data/work/ocr-engine-sweep/fcenet-aster-smoke-30/`
**Field-support output:** `data/work/ocr-engine-sweep/field-support-metrics/doctr-vs-paddle-vs-openocr-vs-parseq-vs-aster-vs-fcenet-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006-E010
**Purpose:** Test FCENet, a Fourier-contour arbitrary-shape text detector, paired with ASTER recognition.

Method:

```text
1. Run MMOCR FCENet on each full label image.
2. Keep detections with score >= 0.5, capped at 128 crops per image.
3. Crop each detected polygon's rectangular bounds.
4. Run MMOCR ASTER recognition on the crops.
5. Aggregate recognized crop text by original label image and TTB ID.
6. Score field support with the same shuffled-negative metric.
```

Environment:

```text
container: python:3.10-slim
detector: MMOCR 1.0.1 TextDetInferencer(model="FCENet")
recognizer: MMOCR 1.0.1 TextRecInferencer(model="ASTER")
runtime: CPU
dependency pins: torch 2.0.1 CPU, mmcv 2.0.1, mmdet 3.0.0, numpy<2
```

Timing / extraction smoke:

| Metric | FCENet + ASTER |
|---|---:|
| Images processed | 30 |
| Error count | 0 |
| Mean latency | 4,526.70 ms/image |
| Median latency | 4,073.50 ms/image |
| Worst latency | 10,525 ms/image |
| Mean detector latency | 4,297.03 ms/image |
| Mean recognizer latency | 210.70 ms/image |
| Mean confidence | 0.8538 |
| Mean detected/crop count | 62.63 |
| Mean extracted chars | 398.23 |

Overall field-support result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR | ASTER | FCENet + ASTER |
|---|---:|---:|---:|---:|---:|
| Accuracy | 0.7455 | 0.7723 | 0.7143 | 0.6920 | 0.6205 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 1.0000 | 0.9655 |
| Recall | 0.5000 | 0.5714 | 0.4375 | 0.3839 | 0.2500 |
| Specificity | 0.9911 | 0.9732 | 0.9911 | 1.0000 | 0.9911 |
| F1 | 0.6627 | 0.7151 | 0.6049 | 0.5548 | 0.3972 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 | 0.0000 | 0.0089 |

Decision:

- FCENet + ASTER successfully exercised arbitrary-shape detection and generated normalized OCR artifacts.
- The detector dominated latency: mean detector time was 4,297.03 ms/image, before application-level aggregation.
- The worst image took 10,525 ms, missing the five-second operational target for a single label image.
- Field-support F1 dropped to 0.3972, mainly because recall fell to 0.2500.
- FCENet remains a useful research checkpoint for curved text detection, but this CPU implementation is not a near-term runtime candidate.
- Small sample sizes increase variance, but this result is directionally negative enough that FCENet should not displace the current OCR candidates before submission.

### E012 - ABINet Recognition Over OpenOCR Crops

**Date:** May 3, 2026
**Run output:** `data/work/ocr-engine-sweep/abinet-openocr-crops-smoke-30/`
**Field-support output:** `data/work/ocr-engine-sweep/field-support-metrics/doctr-vs-paddle-vs-openocr-vs-parseq-vs-aster-vs-fcenet-vs-abinet-smoke-30/`
**Input:** The same 20-application / 30-image smoke set from E006-E011
**Purpose:** Test ABINet, a scene-text recognizer with autonomous bidirectional iterative language modeling, before making an OCR architecture decision.

Method:

```text
1. Reuse OpenOCR-detected text boxes from E008.
2. Crop each detected region from the original label image.
3. Run MMOCR ABINet recognition on the crops.
4. Write normalized OCRResult JSON artifacts.
5. Aggregate recognized crop text by original label image and TTB ID.
6. Score field support with the same shuffled-negative metric.
```

Environment:

```text
container: python:3.10-slim
model source: MMOCR 1.0.1 TextRecInferencer(model="ABINet")
box source: OpenOCR 0.1.5 / SVTRv2 smoke output
runtime: CPU
dependency pins: torch 2.0.1 CPU, mmcv 2.0.1, mmdet 3.0.0, numpy<2
```

Timing / extraction smoke:

| Metric | ABINet Crops |
|---|---:|
| Images processed | 30 |
| Error count | 0 |
| Mean latency | 458.83 ms/image |
| Median latency | 369.00 ms/image |
| Worst latency | 1,229 ms/image |
| Mean confidence | 0.7398 |
| Mean crop count | 20.00 |
| Mean extracted chars | 285.77 |

Overall field-support result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR | ASTER | ABINet |
|---|---:|---:|---:|---:|---:|
| Accuracy | 0.7455 | 0.7723 | 0.7143 | 0.6920 | 0.6607 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 1.0000 | 1.0000 |
| Recall | 0.5000 | 0.5714 | 0.4375 | 0.3839 | 0.3214 |
| Specificity | 0.9911 | 0.9732 | 0.9911 | 1.0000 | 1.0000 |
| F1 | 0.6627 | 0.7151 | 0.6049 | 0.5548 | 0.4865 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 | 0.0000 | 0.0000 |

Decision:

- ABINet loaded successfully and generated normalized OCR artifacts.
- ABINet was fast enough on CPU in this recognizer-stage setup: 458.83 ms/image mean and 1,229 ms worst case.
- ABINet produced zero false clears on the shuffled-negative smoke, matching the conservative safety posture.
- Recall fell to 0.3214 and F1 fell to 0.4865, below docTR, PaddleOCR, OpenOCR, PARSeq, and ASTER in this crop contract.
- This result should not be read as "ABINet is bad." It means full ABINet over OpenOCR rectangular crops did not recover enough field evidence to justify runtime promotion.
- Small sample sizes increase variance, but this first ABINet result does not justify replacing the current OCR path before submission.

### E013 - Deterministic OCR Ensemble Arbitration

**Date:** May 3, 2026
**Run output:** `data/work/ocr-engine-sweep/ensemble-field-support/doctr-paddle-openocr-ensemble-smoke-30-govsafe/`
**Input:** The same 20-application / 30-image smoke set from E006-E012
**Purpose:** Test whether docTR, PaddleOCR, and OpenOCR can be combined as noisy sensors before moving to a learned BERT/LayoutLM-style arbiter.

Method:

```text
1. Aggregate OCR text by TTB ID for docTR, PaddleOCR, and OpenOCR.
2. Score each expected application field against each OCR engine.
3. Create controlled negatives by shuffling same-field values across applications.
4. Evaluate deterministic ensemble policies using the same accuracy, F1, and false-clear metrics.
```

Command:

```bash
python experiments/ocr_engine_sweep/ensemble_field_support_metrics.py \
  --run-name doctr-paddle-openocr-ensemble-smoke-30-govsafe
```

Overall result:

| Policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate |
|---|---:|---:|---:|---:|---:|---:|
| docTR single engine | 0.7455 | 0.9825 | 0.5000 | 0.9911 | 0.6627 | 0.0089 |
| PaddleOCR single engine | 0.7723 | 0.9552 | 0.5714 | 0.9732 | 0.7151 | 0.0268 |
| OpenOCR single engine | 0.7143 | 0.9800 | 0.4375 | 0.9911 | 0.6049 | 0.0089 |
| Any engine | 0.7902 | 0.9452 | 0.6161 | 0.9643 | 0.7459 | 0.0357 |
| Majority vote | 0.7411 | 0.9821 | 0.4911 | 0.9911 | 0.6548 | 0.0089 |
| Unanimous vote | 0.7009 | 1.0000 | 0.4018 | 1.0000 | 0.5732 | 0.0000 |
| Safety weighted | 0.7902 | 0.9710 | 0.5982 | 0.9821 | 0.7403 | 0.0179 |
| Government safe | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 |

Latency note:

- Sequential three-engine sum: mean 3,703.95 ms/application, max 6,940 ms/application.
- Parallel OCR execution has not been implemented; it should be measured before any runtime promotion.

Decision:

- Do not choose the naive highest-F1 "any engine" policy because it increases false clears.
- The government-safe policy is the best current ensemble smoke result because it improves F1 over every single engine while reducing shuffled-negative false clears to zero.
- The key field-specific guardrail is alcohol content: non-unanimous ABV evidence routes to review instead of automatic support.
- This is still a 20-application / 30-image smoke result. It justifies a larger calibration run, not a production claim.

### E014 - WineBERT/o Domain NER Over Combined OCR Text

**Date:** May 3, 2026
**Run outputs:**

```text
data/work/ocr-engine-sweep/wineberto-entity/wineberto-labels-combined-smoke-30/
data/work/ocr-engine-sweep/wineberto-entity/wineberto-ner-combined-smoke-30/
```

**Input:** The same 20-application / 30-image smoke set from E006-E013
**Purpose:** Test whether a wine-domain BERT token classifier can serve as a post-OCR entity arbiter before deployment consideration.

Models tested:

| Model | Purpose | License posture |
|---|---|---|
| `panigrah/wineberto-labels` | Token classifier trained on wine labels, with entities such as producer, wine, region, subregion, country, vintage, and classification. | Public model card lists license as unknown. |
| `panigrah/wineberto-ner` | Token classifier trained on wine labels plus review-style text. | Public model card lists license as unknown. |

Command pattern:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-engine-sweep/wineberto-cache/hf \
  -e HF_HUB_DISABLE_XET=1 \
  -v "$PWD":/app:Z \
  -w /app \
  --entrypoint bash \
  localhost/labels-on-tap-app:local \
  -lc "pip install --no-cache-dir 'transformers==4.57.1' safetensors >/tmp/wineberto-pip.log && \
       python experiments/ocr_engine_sweep/wineberto_entity_benchmark.py \
         --run-name wineberto-labels-combined-smoke-30"
```

Overall result:

| Model / policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate | Mean BERT / app | Max BERT / app |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WineBERT/o labels, entities only | 0.6607 | 1.0000 | 0.3214 | 1.0000 | 0.4865 | 0.0000 | 261.25 ms | 660 ms |
| WineBERT/o labels + government-safe ensemble | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 | 261.25 ms | 660 ms |
| WineBERT/o NER, entities only | 0.5312 | 1.0000 | 0.0625 | 1.0000 | 0.1176 | 0.0000 | 189.30 ms | 432 ms |
| WineBERT/o NER + government-safe ensemble | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 | 189.30 ms | 432 ms |

Threshold sensitivity for `panigrah/wineberto-labels`:

| Threshold | Strategy | F1 | Recall | False-clear rate |
|---:|---|---:|---:|---:|
| 80 | WineBERT/o labels + government-safe ensemble | 0.7302 | 0.6161 | 0.0714 |
| 85 | WineBERT/o labels + government-safe ensemble | 0.7374 | 0.5893 | 0.0089 |
| 90 | WineBERT/o labels + government-safe ensemble | 0.7416 | 0.5893 | 0.0000 |
| 95 | WineBERT/o labels + government-safe ensemble | 0.7416 | 0.5893 | 0.0000 |

Decision:

- Do not promote public WineBERT/o to deployment.
- It is fast enough on CPU to keep as a research option.
- It does not improve the measured government-safe ensemble.
- It does not support ABV or net-contents extraction, two core compliance fields.
- It is wine-specific and does not cover the full beer/wine/spirits domain.
- The public license is unknown; a production path would require a clearly licensed or internally trained token classifier.

### E015 - OSA Market-Domain NER Over Combined OCR Text

**Date:** May 3, 2026
**Run outputs:**

```text
data/work/ocr-engine-sweep/wineberto-entity/osa-custom-ner-combined-smoke-30/
data/work/ocr-engine-sweep/wineberto-entity/osa-custom-ner-combined-smoke-30-t80/
data/work/ocr-engine-sweep/wineberto-entity/osa-custom-ner-combined-smoke-30-t85/
data/work/ocr-engine-sweep/wineberto-entity/osa-custom-ner-combined-smoke-30-t95/
```

**Input:** The same 20-application / 30-image smoke set from E006-E014
**Purpose:** Test whether a lightweight market-domain token classifier can add useful lower-risk field evidence on top of the government-safe OCR ensemble.

Model tested:

| Model | Purpose | License posture |
|---|---|---|
| `AnanthanarayananSeetharaman/osa-custom-ner-model` | Token classifier with `FACT`, `PRDC_CHAR`, and `MRKT_CHAR` labels. `PRDC_CHAR` was mapped to brand/fanciful/class-style support; `MRKT_CHAR` was mapped to origin/market support. | Public model card lists Apache-2.0. |

Command pattern:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-engine-sweep/domain-ner-cache/hf \
  -e HF_HUB_DISABLE_XET=1 \
  -v "$PWD":/app:Z \
  -w /app \
  --entrypoint bash \
  localhost/labels-on-tap-app:local \
  -lc "pip install --no-cache-dir 'transformers==4.57.1' safetensors >/tmp/domain-ner-pip.log && \
       python experiments/ocr_engine_sweep/wineberto_entity_benchmark.py \
         --model-id AnanthanarayananSeetharaman/osa-custom-ner-model \
         --model-label osa-custom-ner-model \
         --model-license apache-2.0 \
         --entity-preset osa \
         --run-name osa-custom-ner-combined-smoke-30"
```

Overall result:

| Model / policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate | Mean BERT / app | Max BERT / app |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OSA NER, entities only | 0.6741 | 1.0000 | 0.3482 | 1.0000 | 0.5166 | 0.0000 | 102.55 ms | 323 ms |
| OSA NER + government-safe ensemble | 0.7991 | 1.0000 | 0.5982 | 1.0000 | 0.7486 | 0.0000 | 102.55 ms | 323 ms |

Threshold sensitivity:

| Threshold | Strategy | F1 | Recall | False-clear rate |
|---:|---|---:|---:|---:|
| 80 | OSA + government-safe ensemble | 0.7302 | 0.6161 | 0.0714 |
| 85 | OSA + government-safe ensemble | 0.7444 | 0.5982 | 0.0089 |
| 90 | OSA + government-safe ensemble | 0.7486 | 0.5982 | 0.0000 |
| 95 | OSA + government-safe ensemble | 0.7486 | 0.5982 | 0.0000 |

Decision:

- Do not promote OSA to runtime from this small smoke alone.
- It is the first tested BERT-family arbiter to improve the government-safe ensemble while preserving zero false clears.
- The lift is small: one additional true positive in `224` field-support examples.
- Thresholds below `90` are unsafe for the current government triage posture because false clears reappear.
- The Apache-2.0 license is materially cleaner than WineBERT/o's unknown license, but the entity taxonomy is still market/sales oriented rather than TTB regulatory.
- The next gate is a COLA Cloud-derived 100-application calibration run before any deployment decision.

### E016 - FoodBaseBERT-NER Culinary-Domain Control

**Date:** May 3, 2026
**Run outputs:**

```text
data/work/ocr-engine-sweep/wineberto-entity/foodbasebert-ner-combined-smoke-30/
data/work/ocr-engine-sweep/wineberto-entity/foodbasebert-ner-combined-smoke-30-t80/
data/work/ocr-engine-sweep/wineberto-entity/foodbasebert-ner-combined-smoke-30-t85/
data/work/ocr-engine-sweep/wineberto-entity/foodbasebert-ner-combined-smoke-30-t95/
```

**Input:** The same 20-application / 30-image smoke set from E006-E015
**Purpose:** Test whether a culinary-domain token classifier can add useful post-OCR field evidence, and use it as a negative-control check against domain-adjacent but non-regulatory models.

Model tested:

| Model | Purpose | License posture |
|---|---|---|
| `Dizex/FoodBaseBERT-NER` | Token classifier trained to recognize one entity type: `FOOD`. `FOOD` was mapped only to brand/fanciful/class-style support. | Public model card lists MIT. |

Command pattern:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-engine-sweep/domain-ner-cache/hf \
  -e HF_HUB_DISABLE_XET=1 \
  -v "$PWD":/app:Z \
  -w /app \
  --entrypoint bash \
  localhost/labels-on-tap-app:local \
  -lc "pip install --no-cache-dir 'transformers==4.57.1' safetensors >/tmp/domain-ner-pip.log && \
       python experiments/ocr_engine_sweep/wineberto_entity_benchmark.py \
         --model-id Dizex/FoodBaseBERT-NER \
         --model-label FoodBaseBERT-NER \
         --model-license mit \
         --entity-preset food \
         --run-name foodbasebert-ner-combined-smoke-30"
```

Overall result:

| Model / policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate | Mean BERT / app | Max BERT / app |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FoodBaseBERT-NER, entities only | 0.5134 | 1.0000 | 0.0268 | 1.0000 | 0.0522 | 0.0000 | 286.65 ms | 547 ms |
| FoodBaseBERT-NER + government-safe ensemble | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 | 286.65 ms | 547 ms |

Threshold sensitivity:

| Threshold | Strategy | F1 | Recall | False-clear rate |
|---:|---|---:|---:|---:|
| 80 | FoodBaseBERT-NER + government-safe ensemble | 0.7166 | 0.5982 | 0.0714 |
| 85 | FoodBaseBERT-NER + government-safe ensemble | 0.7374 | 0.5893 | 0.0089 |
| 90 | FoodBaseBERT-NER + government-safe ensemble | 0.7416 | 0.5893 | 0.0000 |
| 95 | FoodBaseBERT-NER + government-safe ensemble | 0.7345 | 0.5804 | 0.0000 |

Decision:

- Prune FoodBaseBERT-NER from Monday runtime consideration.
- It is fast enough and cleanly licensed, but it has almost no standalone recall on alcohol regulatory fields.
- It does not improve the government-safe ensemble at the safe threshold.
- Lower thresholds reintroduce false clears, so the model fails the government triage posture.

### E017 - DistilRoBERTa / RoBERTa Field-Support Classifiers on the 6,000-Application Corpus

**Date:** May 3, 2026
**Run outputs:**

```text
data/work/field-support-models/distilroberta-field-support-v1-e1/
data/work/field-support-models/roberta-base-field-support-v1-e1/
```

**Purpose:** Train the first BERT-family field-support classifiers on the new
6,000-application public COLA corpus. This run uses the locked application-level
split created before field-pair generation.

Split design:

| Split | Applications | Pair Examples |
|---|---:|---:|
| Train | 2,000 | 31,008 |
| Validation | 1,000 | 15,417 |
| Locked holdout | 3,000 | 46,992 |

Important limitation:

This is a weak-supervision field-pair run, not a final OCR run. Positive
candidate text comes from the same accepted public COLA application field.
Negative candidate text is a same-field value shuffled from another application
in the same split. OCR evidence still needs to be attached before claiming OCR
pipeline accuracy.

Commands:

```bash
.venv-gpu/bin/python experiments/field_support/train_transformer_pair_classifier.py \
  --model-id distilroberta-base \
  --run-name distilroberta-field-support-v1-e1 \
  --epochs 1 \
  --batch-size 64 \
  --eval-batch-size 128 \
  --max-length 128 \
  --device cuda \
  --false-clear-tolerance 0.005 \
  --cpu-latency-rows 512

.venv-gpu/bin/python experiments/field_support/train_transformer_pair_classifier.py \
  --model-id roberta-base \
  --run-name roberta-base-field-support-v1-e1 \
  --epochs 1 \
  --batch-size 48 \
  --eval-batch-size 96 \
  --max-length 128 \
  --device cuda \
  --false-clear-tolerance 0.005 \
  --cpu-latency-rows 512
```

Validation threshold selection:

```text
threshold: 0.99
policy: false_clear_constrained_max_f1
false_clear_tolerance: 0.005
```

Locked-holdout results:

| Model | Train Time | Accuracy | Precision | Recall | Specificity | F1 | False-Clear Rate | FP | FN | CPU Mean / Pair |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DistilRoBERTa | 36.5 s | 0.999915 | 0.999745 | 1.000000 | 0.999872 | 0.999872 | 0.000128 | 4 | 0 | 15.76 ms |
| RoBERTa-base | 73.7 s | 0.999851 | 0.999553 | 1.000000 | 0.999777 | 0.999777 | 0.000223 | 7 | 0 | 33.35 ms |

Per-field locked-holdout false-clear observations:

| Model | Alcohol | Brand | Class/Type | Country | Fanciful | Net Contents |
|---|---:|---:|---:|---:|---:|---:|
| DistilRoBERTa F1 | 1.000000 | 1.000000 | 0.999667 | 1.000000 | 0.999832 | 0.999809 |
| DistilRoBERTa false-clear | 0.000000 | 0.000000 | 0.000333 | 0.000000 | 0.000168 | 0.000191 |
| RoBERTa-base F1 | 0.999646 | 1.000000 | 0.999667 | 1.000000 | 0.999665 | 0.999809 |
| RoBERTa-base false-clear | 0.000354 | 0.000000 | 0.000333 | 0.000000 | 0.000335 | 0.000191 |

Decision:

- DistilRoBERTa is the current preferred trained arbiter candidate. It is
  faster than RoBERTa-base and slightly better on the locked holdout in this
  run.
- RoBERTa-base does not currently justify its additional latency/capacity.
- Do not promote either model to runtime yet. The next gate is to attach real
  docTR/PaddleOCR/OpenOCR evidence as `candidate_text` and rerun the same
  train/validation/locked-holdout evaluation.

### E018 - Large Typography Geometry-Stress Ensemble Sweep

**Date:** May 3, 2026
**Run output:**

```text
data/work/typography-preflight/model-comparison-large-geometry-v1/
```

**Purpose:** Multiply the corrected typography data by five, rotate and bend
half of the crops, retrain SVM/LightGBM/Logistic Regression/MLP, and compare
five ensemble policies:

```text
strict-veto ensemble
calibrated logistic-regression stacker
LightGBM stacker with reject threshold
XGBoost stacker with reject threshold
CatBoost stacker
```

Split design:

| Split | Crops |
|---|---:|
| Base train | 32,000 |
| Calibration | 8,000 |
| Full train | 40,000 |
| Test | 10,000 |

Half of every split uses normal crops and half uses rotation plus sinusoidal
bending. Learned stacker latency is measured end-to-end from raw engineered
crop features, including all base-model predictions plus the stacker.

Test results:

| Task | Model | Test Acc | Test F1 | Test False-Clear | Single ms | P95 ms |
|---|---|---:|---:|---:|---:|---:|
| Visual font decision | SVM | 0.9595 | 0.9593 | 0.0188 | 0.0768 | 0.0803 |
| Visual font decision | LightGBM | 0.9834 | 0.9834 | 0.0186 | 1.9093 | 2.0387 |
| Visual font decision | Logistic Regression | 0.9717 | 0.9717 | 0.0141 | 0.0820 | 0.1183 |
| Visual font decision | MLP | 0.9729 | 0.9729 | 0.0144 | 0.1458 | 0.1570 |
| Visual font decision | Strict-veto ensemble | 0.9433 | 0.9440 | 0.0024 | 2.3431 | 2.4952 |
| Visual font decision | Calibrated logistic stacker | 0.9862 | 0.9862 | 0.0087 | 2.3690 | 2.5141 |
| Visual font decision | LightGBM reject threshold | 0.9867 | 0.9867 | 0.0083 | 2.6037 | 3.0201 |
| Visual font decision | XGBoost reject threshold | 0.9876 | 0.9876 | 0.0086 | 2.5687 | 2.8528 |
| Visual font decision | CatBoost stacker | 0.9878 | 0.9878 | 0.0080 | 2.6713 | 3.0394 |
| Header text decision | SVM | 0.8658 | 0.8648 | 0.0993 | 0.0770 | 0.0799 |
| Header text decision | LightGBM | 0.8937 | 0.8931 | 0.1199 | 1.8445 | 2.0318 |
| Header text decision | Logistic Regression | 0.8793 | 0.8794 | 0.1046 | 0.0786 | 0.0822 |
| Header text decision | MLP | 0.8848 | 0.8850 | 0.0830 | 0.1444 | 0.1530 |
| Header text decision | Strict-veto ensemble | 0.7796 | 0.7794 | 0.0462 | 2.3791 | 2.4831 |
| Header text decision | Calibrated logistic stacker | 0.9007 | 0.9007 | 0.0819 | 2.4700 | 2.7285 |
| Header text decision | LightGBM reject threshold | 0.7428 | 0.7226 | 0.0164 | 2.6253 | 2.8409 |
| Header text decision | XGBoost reject threshold | 0.6656 | 0.6131 | 0.0027 | 2.6884 | 3.0246 |
| Header text decision | CatBoost stacker | 0.9020 | 0.9020 | 0.0857 | 2.7073 | 3.8643 |

Decision:

- Visual boldness has a viable reviewer-assist path. CatBoost has the best
  raw test F1, while the strict-veto ensemble has the best safety posture.
- Header text correctness remains a separate problem. Raw-F1 stackers still
  false-clear too often; reject-threshold policies reduce false clears by
  routing many more crops to review.
- Do not promote typography automation to final runtime authority yet. Keep the
  deployed rule as `Needs Review`, and use this run as evidence for a future
  optional preflight/control-board feature.

### E019 - Real Approved COLA Typography Smoke Test

**Date:** May 3, 2026
**Run output:**

```text
data/work/typography-preflight/real-cola-smoke-v1/
```

**Purpose:** Test whether the trained typography classifiers from `E018`
transfer to real approved COLA warning-heading crops. This run used cached
train/validation OCR conveyor output only; it did not run new OCR, touch the
locked holdout, call external services, or modify the deployed app.

Inputs:

| Input | Value |
|---|---:|
| Approved COLA applications selected | 100 |
| Label images selected | 203 |
| Cached OCR rows loaded | 15,537 |
| OCR engines | docTR, PaddleOCR, OpenOCR |
| Heading crops found | 124 |
| Applications with at least one heading crop | 68 |

Heading crops by engine:

| Engine | Heading crops |
|---|---:|
| PaddleOCR | 62 |
| OpenOCR | 59 |
| docTR | 3 |

Real-COLA smoke results:

| Classifier | Model | App clear rate | Crop clear rate | Crop review rate | Mean ms/crop | P95 ms/crop |
|---|---|---:|---:|---:|---:|---:|
| Boldness | Strict-veto ensemble | 0.01 | 0.0081 | 0.9919 | 4.29 | 13.93 |
| Boldness | Logistic stacker | 0.08 | 0.0726 | 0.8952 | 3.23 | 3.72 |
| Boldness | LightGBM reject | 0.06 | 0.0484 | 0.9032 | 3.31 | 3.78 |
| Boldness | XGBoost reject | 0.07 | 0.0565 | 0.9032 | 3.42 | 3.88 |
| Boldness | CatBoost stacker | 0.08 | 0.0645 | 0.8871 | 3.31 | 3.83 |
| Warning text | Strict-veto ensemble | 0.00 | 0.0000 | 1.0000 | 3.24 | 3.70 |
| Warning text | Logistic stacker | 0.02 | 0.0161 | 0.9194 | 3.15 | 3.78 |
| Warning text | LightGBM reject | 0.01 | 0.0081 | 0.9597 | 3.32 | 3.94 |
| Warning text | XGBoost reject | 0.00 | 0.0000 | 0.9677 | 3.49 | 5.08 |
| Warning text | CatBoost stacker | 0.03 | 0.0242 | 0.9435 | 3.38 | 5.23 |

Decision:

- Do not promote the typography classifiers into the MVP runtime.
- The compute cost is acceptable, so latency is not the blocker.
- The blocker is real-crop transfer: synthetic-trained typography classifiers
  route most approved real warning crops to review.
- The heading-isolation layer also needs work. PaddleOCR and OpenOCR found
  most crops; docTR found very few with the current block-matching method.
- Keep `GOV_WARNING_HEADER_BOLD_REVIEW` as a human-review check for tonight's
  MVP.

Important limitation:

Approved public COLA records are positive examples. They are useful for testing
crop location, pass-through behavior, and latency. They cannot estimate the
dangerous false-clear case. Synthetic non-bold, incorrect, and unreadable
negative crops remain necessary for false-clear testing.

### E020 - Real-Adapted Runtime Warning Boldness Preflight

**Date:** 2026-05-03
**Status:** Promoted as conservative runtime evidence
**Code path:** `app/services/typography/`
**Model export:** `app/models/typography/boldness_logistic_v1.json`
**Source experiment:** `experiments/typography_preflight/real_cola_smoke.py`

Purpose:

Fix the flawed real-COLA smoke by correcting the evidence, not by adding a
heavier model. The earlier stackers saw contaminated crops: headings mixed with
body text, tiny partial crops, and split word boxes. The corrected cropper trims
OCR lines to the `GOVERNMENT WARNING:` prefix, groups docTR-style split boxes,
and normalizes crops toward black text on white before feature extraction.

Training/evaluation design:

```text
real positive train crops: 3,083 approved COLA warning headings
real positive holdout crops: 768 approved COLA warning headings
synthetic negative/review crops: non-bold and degraded warning headings
model family: Logistic Regression over OpenCV/HOG features
runtime dependency profile: JSON coefficients + numpy + OpenCV
```

Selected threshold:

| Threshold policy | Threshold | Validation false-clear | Synthetic test false-clear | Synthetic test F1 | Real positive holdout clear |
|---|---:|---:|---:|---:|---:|
| `<= 0.001` validation false-clear tolerance | 0.954582 | 0.000624 | 0.001800 | 0.865570 | 0.921875 |

Operational behavior:

```text
probability >= 0.9546 -> GOV_WARNING_HEADER_BOLD_REVIEW passes
probability <  0.9546 -> Needs Review
missing/noisy crop       -> Needs Review
```

Runtime sanity check:

```text
real approved COLA heading crop:
  probability: 0.999944
  verdict: pass
  crop + classify time in container: about 37 ms

container tests:
  podman run --rm -v "$PWD":/app:Z -w /app \
    localhost/labels-on-tap-app:local pytest -q
  result: 78 passed
```

Decision:

- Promote this model only as a warning-heading boldness preflight.
- Do not use it to automatically reject labels.
- Confident bold evidence can clear the boldness check.
- Uncertain, unreadable, or unisolated evidence remains `Needs Review`.

### E021 - Audit-v6 Typography Image Set With Real COLA Seeding

**Date:** 2026-05-03
**Status:** Dataset generated for inspection; not a trained model
**Code path:** `experiments/typography_preflight/build_v6_dataset.py`
**Local output:** `data/work/typography-preflight/audit-v6/`

Purpose:

Correct the statistical weakness in the emergency typography bridge model by
creating an `audit-v5`-style image set that mixes real COLA visual context with
synthetic and mutated known-bad examples. This is the dataset we inspect before
training the next boldness/text/panel classifiers.

Artifact shape:

```text
data/work/typography-preflight/audit-v6/
  README.md
  font_inventory.json
  index.html
  manifest.csv
  summary.json
  crops/
  by_split/
  by_source_kind/
  by_source_origin/
  by_panel_warning/
  by_heading_text/
  by_boldness/
  by_quality/
  by_font_weight/
```

Split counts:

| Split | Images |
|---|---:|
| Train | 6,000 |
| Validation | 1,500 |
| Test | 1,500 |
| Total | 9,000 |

The split is by real `ttb_id` for COLA-derived rows. The generated audit set
has `0` TTB ID overlap between train, validation, and test.

Source-origin breakdown:

| Source origin | Images | Meaning |
|---|---:|---|
| `real_cola_heading` | 1,800 | Real approved COLA warning-heading crops |
| `real_cola_background` | 2,257 | Real COLA warning-heading backgrounds with controlled synthetic overlays |
| `real_cola_panel` | 900 | Real COLA label panels with no detected warning heading |
| `synthetic` | 4,043 | Fully synthetic bold, non-bold, incorrect, and unreadable/review crops |

Broad mix:

| Bucket | Images | Share |
|---|---:|---:|
| COLA-derived visual context | 4,957 | 55.08% |
| Synthetic-only | 4,043 | 44.92% |

Source-kind breakdown:

| Source kind | Images |
|---|---:|
| `real_heading_positive` | 1,800 |
| `real_background_non_bold` | 1,800 |
| `real_no_warning_panel` | 900 |
| `synthetic_bold_positive` | 1,350 |
| `synthetic_non_bold` | 1,350 |
| `synthetic_incorrect` | 900 |
| `review_unreadable` | 900 |

Task-label breakdown:

| Label family | Values |
|---|---|
| `panel_warning_label` | `warning_present`: 7,200; `warning_absent`: 900; `unreadable_review`: 900 |
| `heading_text_label` | `correct_government_warning`: 6,300; `incorrect_heading_text`: 900; `not_applicable`: 900; `unreadable_review`: 900 |
| `boldness_label` | `bold`: 3,584; `not_bold`: 3,616; `not_applicable`: 900; `unreadable_review`: 900 |

Important design notes:

- This is an image inspection set, not an Excel/spreadsheet deliverable.
- `manifest.csv` is a machine-readable manifest, analogous to `audit-v5`.
- `index.html` and `by_*` directories are for human inspection.
- No-warning panels are panel-level negatives, not application-level failures.
- Real-background mutations are intentionally included because approved public
  COLAs rarely provide true non-bold rejected examples.
- The prior training-style `data/work/typography-preflight/v6/` folder is a
  byproduct; the intended inspection artifact is `audit-v6/`.

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

> A first experimental graph-aware evidence scorer improved field-support classification on the COLA Cloud-derived 100-application calibration test split while lowering false clears on shuffled negative examples.

This result does not support a production claim:

> The app is production-ready or has final OCR accuracy.

The current best pure OCR ensemble smoke result is `E013`, using deterministic
government-safe arbitration across docTR, PaddleOCR, and OpenOCR. The current
best BERT-assisted OCR-smoke result is `E015`, using OSA market-domain NER plus
the government-safe ensemble. The current best trained text-pair arbiter result
is `E017`, where DistilRoBERTa beat RoBERTa-base on the 3,000-application
locked holdout with lower CPU latency. The current best typography-preflight
result is `E020`: the real-adapted logistic model can clear strong
`GOVERNMENT WARNING:` boldness evidence while preserving Needs Review fallback
for weak crops.

## Known Limitations

- The current graph and BERT text-pair labels are weak labels from accepted application fields and shuffled negatives, not human-labeled OCR spans.
- The earlier graph scorer test split is drawn from the COLA Cloud-derived 100-application calibration set, not the 3,000-application locked holdout.
- The graph scorer and deterministic ensemble cannot recover text no OCR engine detected.
- Class/type remains difficult and probably needs better product taxonomy handling, better OCR, or field-specific candidate generation.
- The current model processes variable-size graphs one at a time; batching/padding should be added before larger runs.
- GPU training works locally, but `.venv-gpu` is not part of the deployed app and is intentionally gitignored.

## Next Experiments

1. Run docTR, PaddleOCR, OpenOCR, the government-safe ensemble, and OSA hybrid evidence on the COLA Cloud-derived 100-application / 169-image calibration set.
2. Attach docTR/PaddleOCR/OpenOCR evidence to the existing 6,000-record field-support pair manifests.
3. Rerun DistilRoBERTa on OCR-backed candidate text using train/validation only for tuning.
4. Compare OCR-backed DistilRoBERTa against the deterministic government-safe ensemble and OSA hybrid.
5. Freeze graph/ensemble/classifier settings after calibration and evaluate only once on the locked test split.
6. Add field-specific class/type taxonomy features to attack the weakest measured OCR-backed field.
7. Preserve LayoutLMv3 and the full HO-GNN/TPS/SVTR roadmap as future research paths after simpler post-OCR arbitration is fully measured.
