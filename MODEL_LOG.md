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
| COLA Cloud API | Development-only bridge for public label rasters | No | `1,500` selected records from `7,788` candidates |
| Cached docTR OCR | Baseline OCR box/text output | No | `100` applications, `169` label images |
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
- The next gate is a 100-application calibration run before any deployment decision.

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

The current best pure OCR ensemble smoke result is `E013`, using deterministic
government-safe arbitration across docTR, PaddleOCR, and OpenOCR. The current
best BERT-assisted smoke result is `E015`, using OSA market-domain NER plus the
government-safe ensemble. It improved F1 from `0.7416` to `0.7486` with
false-clear rate still `0.0000`, but this is not yet the deployed runtime path
because the lift came from one additional true positive in a small smoke sample.

## Known Limitations

- The current graph labels are weak labels from accepted application fields and shuffled negatives, not human-labeled OCR spans.
- The test split is drawn from the 100-application calibration set, not the planned locked 1,500 holdout.
- The graph scorer and deterministic ensemble cannot recover text no OCR engine detected.
- Class/type remains difficult and probably needs better product taxonomy handling, better OCR, or field-specific candidate generation.
- The current model processes variable-size graphs one at a time; batching/padding should be added before larger runs.
- GPU training works locally, but `.venv-gpu` is not part of the deployed app and is intentionally gitignored.

## Next Experiments

1. Run docTR, PaddleOCR, OpenOCR, the government-safe ensemble, and OSA hybrid evidence on the 100-application / 169-image calibration set.
2. Scale graph training to the full 1,500-record calibration split once details/images/OCR are available.
3. Freeze graph/ensemble settings after calibration and evaluate only once on the locked 1,500 holdout.
4. Add field-specific class/type taxonomy features to attack the weakest measured field.
5. Preserve BERT/LayoutLMv3 and the full HO-GNN/TPS/SVTR roadmap as future research paths after simpler post-OCR arbitration is fully measured.
