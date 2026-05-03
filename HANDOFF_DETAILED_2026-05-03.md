# Labels On Tap Detailed Handoff - May 3, 2026

**Project:** Labels On Tap  
**Canonical URL:** `https://www.labelsontap.ai`  
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`  
**Purpose:** restart-grade handoff for a new Codex session or a human reviewer if the active chat context is lost.

This file is intentionally detailed. It records what was built, what was measured, what should not be confused, and what to do next.

---

## 1. Current Mission

Labels On Tap is a Treasury/TTB take-home prototype. The target workflow is:

```text
COLAs Online-style application data
  + submitted label artwork
  -> local OCR / parsing
  -> deterministic field/rule comparison
  -> Pass / Needs Review / Fail with evidence
```

The app is **not** intended to replace compliance agents. It is a triage assistant. Its job is to quickly identify applications that appear out of compliance or uncertain enough to need review.

The primary safety metric is the **false-clear rate**:

```text
known-bad or mismatched label marked Pass = false clear
```

The product posture is conservative:

```text
strong evidence matches       -> Pass
clear evidence-backed problem -> Fail
uncertain OCR/rule evidence   -> Needs Review
```

---

## 2. Non-Negotiables

- Canonical URL is `https://www.labelsontap.ai`, not `.com`.
- Runtime app must not use hosted OCR/ML APIs.
- Do not use OpenAI, Anthropic, Google Vision, Azure Vision, AWS Textract, hosted VLMs, or hosted OCR at runtime.
- Do not scrape private/authenticated COLAs Online data.
- Do not commit `.env`, API keys, raw API responses, raw bulk data, SQLite databases, downloaded images, OCR outputs, model checkpoints, or phone-photo data.
- Keep bulk/evaluation artifacts under gitignored `data/work/`.
- Keep the deployed FastAPI app stable unless a measured replacement passes promotion gates.
- Do not train graph/Transformer experiments on CPU if the user explicitly asks for GPU-only training.
- Do not claim production OCR accuracy from calibration/smoke data.
- Always distinguish direct TTB registry artifacts from COLA Cloud-derived public calibration data.

---

## 3. Deployed App State

The public app is live:

```text
https://www.labelsontap.ai
https://labelsontap.ai -> redirects to https://www.labelsontap.ai
```

Deployment stack:

```text
AWS Lightsail Ubuntu VM
Docker Compose
Caddy reverse proxy / TLS
FastAPI app container
filesystem job store
```

Runtime stack:

```text
FastAPI
Jinja2
HTMX
local CSS
docTR OCR adapter
fixture OCR fallback
RapidFuzz deterministic field matching
source-backed rule outputs
filesystem JSON result storage
```

Last known local test state:

```text
pytest -q
69 passed
```

Deployment smoke commands:

```bash
curl https://www.labelsontap.ai/health
curl -I https://labelsontap.ai
docker compose ps
docker compose logs --tail=100 app
```

---

## 4. Data Source Truth

There are three separate data streams. Do not blend them in documentation or metrics.

### 4.1 Synthetic Demo Fixtures

Path:

```text
data/fixtures/demo/
```

Purpose:

- deterministic one-click demos,
- repeatable unit/integration tests,
- synthetic known-bad cases,
- deployed app demo reliability.

Important note:

The Old River Brewing images are synthetic fixtures. They are not public COLA images and should not be described as such.

### 4.2 Direct TTB Public COLA Registry ETL

Primary local path:

```text
data/work/public-cola/
```

Purpose:

- preserve the official printable-form workflow,
- parse public registry search result CSVs,
- fetch public form HTML where possible,
- extract application fields and attachment links,
- eventually reconcile COLA Cloud records back to official printable forms when the endpoint is stable.

Current state observed locally:

```text
parsed applications: 1010 JSON files under data/work/public-cola/parsed/applications/
raw forms: 810 files under data/work/public-cola/raw/forms/
raw image-like files: 1569 files under data/work/public-cola/raw/images/
valid raster files under that image tree: 334
invalid/non-raster files under that image tree: 1235
search result CSVs: 68
```

Critical caveat:

The May 2 audit found that many direct registry attachment downloads were HTML/error responses rather than valid label rasters. Therefore, the **current OCR/model metrics are not based on the direct TTB attachment downloads**.

Scripts involved:

```text
scripts/init_public_cola_workspace.py
scripts/import_public_cola_search_results.py
scripts/fetch_public_cola_search_results.py
scripts/fetch_public_cola_forms.py
scripts/parse_public_cola_forms.py
scripts/download_public_cola_images.py
scripts/audit_public_cola_images.py
scripts/evaluate_public_cola_ocr.py
scripts/export_public_cola_fixtures.py
scripts/run_public_cola_sampling_job.py
scripts/select_public_cola_sample.py
```

### 4.3 COLA Cloud-Derived Public Calibration Data

Primary local path:

```text
data/work/cola/
```

Purpose:

- development-only bridge to obtain public COLA records and valid label images while TTBOnline.gov was unstable,
- local OCR and field-matching calibration,
- not a runtime dependency.

Current local counts after the staged May 3 acquisition:

```text
official-sample-3000-balanced:
  selected list IDs: 3000
  fetched detail/application records: 3000
  parsed application JSON files: 3000
  downloaded/mirrored label image files: 5353
  failures: 0

official-sample-next-3000-balanced:
  selected list IDs: 3000
  fetched detail/application records: 3000
  parsed application JSON files: 3000
  downloaded/mirrored label image files: 5082
  failures: 0

combined first + extension cohorts:
  unique fetched public COLA applications: 6000
  combined label image files: 10435
  overlap between cohorts: 0
```

Application-level split manifests were generated after acquisition:

```text
data/work/cola/evaluation-splits/field-support-v1/
  train_applications.csv
  train_ttb_ids.txt
  validation_applications.csv
  validation_ttb_ids.txt
  holdout_applications.csv
  holdout_ttb_ids.txt
  all_applications.csv
  split_summary.json
```

Split counts and local image coverage:

```text
train:
  applications: 2000
  local label images: 3564

validation:
  applications: 1000
  local label images: 1789

locked holdout:
  applications: 3000
  local label images: 5082

development-holdout overlap:
  0 TTB IDs
```

Field-support target and pair manifests were generated from those application
splits:

```text
data/work/cola/field-support-datasets/field-support-v1/
  train_field_targets.csv / .jsonl
  train_field_pairs.csv / .jsonl
  validation_field_targets.csv / .jsonl
  validation_field_pairs.csv / .jsonl
  holdout_field_targets.csv / .jsonl
  holdout_field_pairs.csv / .jsonl
  all_field_targets.csv / .jsonl
  all_field_pairs.csv / .jsonl
  dataset_summary.json
```

Field-support dataset counts:

```text
train:
  field targets: 10336
  pair examples: 31008
  labels: 10336 positive, 20672 shuffled negative

validation:
  field targets: 5139
  pair examples: 15417
  labels: 5139 positive, 10278 shuffled negative

locked holdout:
  field targets: 15664
  pair examples: 46992
  labels: 15664 positive, 31328 shuffled negative

combined:
  field targets: 31139
  pair examples: 93417
  labels: 31139 positive, 62278 shuffled negative
```

Included target fields:

```text
brand_name
fanciful_name
class_type
alcohol_content
net_contents
country_of_origin
```

Negative examples are generated only from same-split, same-field shuffled
values. This keeps the holdout locked and prevents application-level leakage.

BERT-family text-pair classifiers were trained on these generated manifests:

```text
data/work/field-support-models/distilroberta-field-support-v1-e1/
data/work/field-support-models/roberta-base-field-support-v1-e1/
```

Current locked-holdout text-pair results:

| Model | Holdout F1 | False-Clear Rate | FP | FN | CPU Mean / Pair |
|---|---:|---:|---:|---:|---:|
| DistilRoBERTa | 0.999872 | 0.000128 | 4 | 0 | 15.76 ms |
| RoBERTa-base | 0.999777 | 0.000223 | 7 | 0 | 33.35 ms |

Important: these are weak-supervision field-pair results. They prove the
text-pair arbiter can learn the support relation on the 6,000-record corpus.
They do **not** yet prove final OCR extraction accuracy because OCR candidate
evidence has not been attached to these pair manifests.

Important current sample folders:

```text
data/work/cola/colacloud-api-detail-probe/
data/work/cola/official-sample-1500/
data/work/cola/official-sample-1500-balanced/
data/work/cola/official-sample-3000-balanced/
data/work/cola/official-sample-next-3000-balanced/
data/work/cola/evaluation-splits/field-support-v1/
data/work/cola/field-support-datasets/field-support-v1/
```

Current measured calibration source before the full-corpus rerun:

```text
data/work/cola/official-sample-1500-balanced/
100 fetched detail records
169 label images
```

The 100-record metrics are now historical smoke/calibration results. They
should be superseded by a full-corpus rerun over the 6,000-record acquisition.

Metrics from OCR/model experiments should be described as:

```text
COLA Cloud-derived public COLA calibration metrics
```

Do **not** describe them as:

```text
direct TTB attachment-download metrics
```

---

## 5. Sampling And Statistical Design

Current framing:

- accepted public COLAs are positive ground truth for the application-field-to-label-artwork matching task,
- synthetic negative fixtures are required for mismatch/rejection/false-clear testing,
- confidential rejected or Needs Correction COLAs are not public and should not be claimed.

Sampling method:

```text
two-stage deterministic stratified sampling
primary strata: month
secondary balancing: product family, imported/domestic bucket, image-panel complexity
randomness: fixed seed
replacement: without replacement
```

Final current corpus design:

```text
development cohort:
  data/work/cola/official-sample-3000-balanced
  3000 unique public COLA applications

locked holdout cohort:
  data/work/cola/official-sample-next-3000-balanced
  3000 unique public COLA applications

overlap:
  0 TTB IDs
```

Actual model-selection split inside the development cohort:

```text
2000 train applications
1000 validation/calibration applications
3000 locked holdout applications in the second cohort
manifest path: data/work/cola/evaluation-splits/field-support-v1/
```

Important leakage rule:

Split by application/TTB ID **before** generating field-pair examples. The same TTB ID must never appear in train, validation, and test.

Recommended training/testing workflow:

```text
1. Use the existing split manifests under
   `data/work/cola/evaluation-splits/field-support-v1/`.
2. Generate field-support examples only after loading the application-level
   split manifests.
3. Train/tune BERT-family arbiters, graph scorer, deterministic ensemble, and
   OCR-engine policies on train/validation only.
4. Lock the final architecture, features, and thresholds.
5. Optional production refit: retrain the chosen learned scorer on all 3000
   development applications while preserving validation-derived or
   out-of-fold-calibrated thresholds.
6. Evaluate exactly once on the second 3000-record holdout cohort.
```

Margin-of-error notes:

```text
n = 3000 locked test -> about +/- 1.8 percentage points conservative 95% MOE
```

Those are sampling margins for binary proportion estimates, not promises of production accuracy.

---

## 6. Current OCR And Model Results

All current results are calibration/smoke results, not production claims.

### 6.1 docTR 100-Application Baseline

Input:

```text
100 COLA Cloud-derived public applications
169 label images
cached local docTR OCR
```

Corrected field support after mapping `abv`, `volume`, and `volume_unit`:

| Field | Attempted | Matched | Match Rate |
|---|---:|---:|---:|
| Brand name | 100 | 71 | 0.7100 |
| Fanciful name | 100 | 65 | 0.6500 |
| Class/type | 100 | 49 | 0.4900 |
| Alcohol content | 94 | 86 | 0.9149 |
| Net contents | 86 | 72 | 0.8372 |
| Country of origin | 38 | 30 | 0.7895 |
| Applicant/producer | 100 | 2 | 0.0200 |

Latency:

```text
mean per application: 1413 ms
max per application: 3620 ms
```

### 6.2 OCR Engine Sweep

30-image/20-application smoke comparison:

| Model | Accuracy | Precision | Recall | Specificity | F1 | False-Clear Rate |
|---|---:|---:|---:|---:|---:|---:|
| docTR | 0.7455 | 0.9825 | 0.5000 | 0.9911 | 0.6627 | 0.0089 |
| PaddleOCR | 0.7723 | 0.9552 | 0.5714 | 0.9732 | 0.7151 | 0.0268 |
| OpenOCR / SVTRv2 | 0.7143 | 0.9800 | 0.4375 | 0.9911 | 0.6049 | 0.0089 |
| PARSeq AR | 0.6875 | 0.9773 | 0.3839 | 0.9911 | 0.5513 | 0.0089 |
| PARSeq NAR | 0.6875 | 0.9773 | 0.3839 | 0.9911 | 0.5513 | 0.0089 |
| ASTER | 0.6920 | 1.0000 | 0.3839 | 1.0000 | 0.5548 | 0.0000 |
| FCENet + ASTER | 0.6205 | 0.9655 | 0.2500 | 0.9911 | 0.3972 | 0.0089 |
| ABINet | 0.6607 | 1.0000 | 0.3214 | 1.0000 | 0.4865 | 0.0000 |

Latency summary:

| Model | Mean / Image | Worst / Image | Notes |
|---|---:|---:|---|
| docTR | 800.53 ms | 1592 ms | cached baseline |
| PaddleOCR | 1105.00 ms | 1544 ms | promising F1, higher false-clear rate |
| OpenOCR / SVTRv2 | 563.77 ms | 1211 ms | fastest complete OCR candidate |
| PARSeq AR over crops | 293.47 ms | 870 ms | recognizer-stage only |
| PARSeq NAR over crops | 215.17 ms | 655 ms | recognizer-stage only |
| ASTER over crops | 119.87 ms | 275 ms | recognizer-stage only |
| FCENet + ASTER | 4526.70 ms | 10525 ms | too slow as tested |
| ABINet over crops | 458.83 ms | 1229 ms | recognizer-stage only |

Interpretation:

- PaddleOCR currently has the best single-engine F1 in the small smoke, but with higher false-clear risk.
- OpenOCR is operationally attractive because it is fast.
- PARSeq/ASTER/ABINet are recognizer-stage experiments over OpenOCR crops, not full OCR engines in the tested setup.
- FCENet exercised arbitrary-shape detection but missed the CPU latency target.
- Small sample sizes increase variance; do not overclaim from the 30-image smoke.

### 6.3 Government-Safe OCR Ensemble

Tested engines:

```text
docTR
PaddleOCR
OpenOCR
```

Best current policy:

```text
government-safe ensemble
```

Result:

```text
F1: 0.7416
false-clear rate: 0.0000
```

Interpretation:

This is the strongest small-sample engineering signal so far because it improves over single engines while preserving the government safety posture.

### 6.4 BERT/NER Arbiter Smoke Tests

Tested over combined docTR/PaddleOCR/OpenOCR text:

| Model | License Posture | Result |
|---|---|---|
| WineBERT/o labels | unknown | entity-only F1 0.4865; no lift over government-safe ensemble |
| WineBERT/o NER | unknown | entity-only F1 0.1176; pruned |
| OSA custom NER | Apache-2.0 | hybrid F1 0.7486; false-clear 0.0000; small lift |
| FoodBaseBERT-NER | MIT | entity-only F1 0.0522; no lift; pruned |

Interpretation:

- OSA is the only BERT-family smoke that improved the government-safe ensemble, but the lift was tiny and not enough for runtime promotion.
- WineBERT/o is interesting but not deployable now because of unknown license, wine-only semantics, and no ABV/net-contents coverage.
- FoodBaseBERT was a useful negative control.

### 6.5 Graph-Aware Evidence Scorer

This is post-OCR field-support scoring, not OCR replacement.

Current best run:

```text
data/work/graph-ocr/gpu-safety-neg2-e40/
device: cuda
epochs: 40
negative_loss_weight: 2.0
false_clear_tolerance: 0.0
```

Metrics:

| Metric | Baseline | Graph |
|---|---:|---:|
| Accuracy | 0.8947 | 0.9408 |
| Precision | 0.8438 | 0.9531 |
| Recall | 0.7105 | 0.8026 |
| F1 | 0.7714 | 0.8714 |
| False-clear rate | 0.0439 | 0.0132 |

Interpretation:

Promising proof of signal. Not deployable until larger calibration, locked-test evaluation, and CPU latency/packaging checks.

---

## 7. Model Architecture Direction

Current practical architecture:

```text
label artwork
  -> local OCR engines as noisy sensors
  -> normalized OCR boxes/text/confidence
  -> deterministic or learned field-support scorer
  -> source-backed deterministic rules
  -> Pass / Needs Review / Fail
```

Near-term candidate path:

```text
docTR + PaddleOCR + OpenOCR
  -> government-safe ensemble
  -> optional OSA/DistilRoBERTa/RoBERTa field-support classifier
  -> deterministic compliance rules
```

Future research paths documented but not built into runtime:

- LayoutLMv3 spatial arbiter,
- HO-GNN / hypergraph curved-text model,
- TPS/STN unwarping,
- SVTR/CRNN sequence recognition,
- ONNX/OpenVINO/INT8 CPU optimization on EC2 `m7i`.

Do not deploy a trained Transformer or graph model unless:

```text
validation improves,
locked test improves,
false-clear posture is preserved,
CPU latency fits,
rollback exists,
runtime dependencies are acceptable.
```

### 7.1 Full-Corpus Model Statistics Rerun

The project can now rerun the side-by-side statistics table on a much more
defensible corpus. The realistic rerun scope is:

```text
OCR sensors:
  docTR
  PaddleOCR
  OpenOCR / SVTRv2

Deterministic / learned arbiters:
  single-engine deterministic field support
  government-safe OCR ensemble
  OSA/domain NER hybrid if dependency path is stable
  DistilRoBERTa field-support classifier
  RoBERTa field-support classifier if time allows
  graph-aware post-OCR evidence scorer

Historical/pruned recognizer experiments:
  PARSeq
  ASTER
  FCENet + ASTER
  ABINet
```

The first group should be rerun end-to-end on the larger corpus. The historical
crop-recognizer and FCENet experiments can be rerun for completeness, but they
were already pruned from runtime promotion because the tested crop contract had
severe recall degradation or CPU-latency risk. Do not let those optional reruns
block the final model decision.

For every candidate that reaches the comparison table, report:

```text
accuracy
precision
recall
specificity
F1
false-clear rate
confusion counts
per-field F1
mean / median / p95 latency
application-level Pass / Needs Review / Fail rate
```

Important limitation:

```text
Official public COLA data provides weak supervision for field-support scoring.
It does not provide character-level, polygon-level, or word-level OCR ground
truth. Therefore, it supports training/tuning BERT-style field-support arbiters
and threshold policies, but not honest claims of fine-tuning OCR recognizers
unless separate OCR annotations are created.
```

### 7.2 Armored OCR Conveyor State

The armored OCR conveyor is now built and smoke-tested. It is the mechanism that
should run the full docTR + PaddleOCR + OpenOCR evidence extraction without
letting corrupt images or native OCR crashes kill the parent job.

What it does:

```text
image manifest
  -> file signature preflight
  -> Pillow decode validation
  -> valid/invalid split
  -> per-engine chunk jobs
  -> subprocess-isolated OCR execution
  -> per-job stdout/stderr/result JSON
  -> resumable output under data/work/ocr-conveyor/
```

Completed checks:

| Run | Output Path | Result |
|---|---|---|
| 3-image real smoke | `data/work/ocr-conveyor/tri-engine-smoke-3/` | 3 valid images; all three engines completed; 9 OCR rows; 0 row errors |
| 8-image real smoke | `data/work/ocr-conveyor/tri-engine-smoke-8/` | 8 valid images; all three engines completed; 24 OCR rows; 0 row errors |
| 16-request real smoke | `data/work/ocr-conveyor/tri-engine-smoke-16/` | 13 valid images; 3 invalid/corrupt skipped by preflight; all three engines completed; 39 OCR rows; 0 row errors |
| Train/validation dry run | `data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/` | 5,353 image rows; 5,179 valid images; 174 invalid/corrupt skipped; 975 planned jobs |

Active train/validation run snapshot:

```text
snapshot_time: 2026-05-03T12:20:42-05:00
container: 253b9caaf335
output_dir: data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/
planned_jobs: 975
completed_chunk_results: 975
completed_by_engine:
  docTR: 325
  PaddleOCR: 325
  OpenOCR: 325
ocr_row_errors_observed: 0
```

Interpretation:

- The train/validation run completed all planned chunks.
- There were no observed OCR row errors.
- Do not start a second full conveyor run against the same output directory.

Observed smoke timing:

| Run | Engine | Images Processed | Elapsed |
|---|---|---:|---:|
| `tri-engine-smoke-8` | docTR | 8 | 16.636 s |
| `tri-engine-smoke-8` | PaddleOCR | 8 | 50.295 s |
| `tri-engine-smoke-8` | OpenOCR | 8 | 16.686 s |
| `tri-engine-smoke-16` | docTR | 13 | 18.352 s |
| `tri-engine-smoke-16` | PaddleOCR | 13 | 70.629 s |
| `tri-engine-smoke-16` | OpenOCR | 13 | 15.861 s |

Current recommendation:

```text
Run the full train/validation conveyor next at chunk-size 16.
Do not run the holdout conveyor until the preprocessing, OCR-evidence
attachment, DistilRoBERTa threshold, graph scorer, and deterministic compliance
settings are frozen.
```

Estimated runtime for the full train/validation tri-engine run is roughly
10-12 hours, with PaddleOCR the slowest engine. The run should use the container
command in Section 9 so the heavy OCR dependencies stay out of the production
Python environment.

### 7.3 Government Warning Typography Preflight Plan

Jenny Park explicitly called out that the government warning heading must be
both all caps and bold. The all-caps requirement is already a deterministic
rule. Boldness is currently handled as `GOV_WARNING_HEADER_BOLD_REVIEW`, which
routes the issue to manual typography review.

The experiment is a classical OpenCV/SVM typography preflight. It does not touch
the OCR conveyor, does not use the GPU, and should not be integrated into
runtime authority until validated.

Target architecture:

```text
OCR isolates or approximates GOVERNMENT WARNING:
  -> crop heading region
  -> OpenCV normalization
  -> stroke/shape features
  -> CPU-only Support Vector Machine
  -> bold / non-bold / uncertain typography preflight
  -> deterministic compliance policy
```

Why SVM instead of a CNN/Transformer:

- The task is narrow and visual: classify stroke-weight evidence for one known
  phrase.
- Engineered features can directly describe the decision boundary.
- CPU inference is effectively negligible compared with OCR.
- Synthetic training data is appropriate for the controlled typography
  distinction.
- A margin-based classifier is easy to threshold conservatively around
  false-clear risk.

The statistical-learning citation to use:

```text
Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome.
The Elements of Statistical Learning: Data Mining, Inference, and Prediction.
2nd ed., Springer, 2009.
```

Do not overclaim the citation. Use it to justify why a margin-based classical
model is appropriate for compact engineered feature vectors, not to claim this
specific typography model is production-certified.

Implemented paths:

```text
experiments/typography_preflight/
  README.md
  generate_dataset.py
  features.py
  train_svm.py
  evaluate.py
  report.py

data/work/typography-preflight/
  synthetic/
  manifests/
  features/
  models/
  metrics/
  sample_crops/
```

Dataset:

```text
train:      20,000 synthetic warning-heading crops
validation: 5,000 synthetic warning-heading crops
test:       5,000 synthetic warning-heading crops
```

Split rule:

```text
Hold out font families and distortion recipes across train/validation/test.
Do not rely on a naive random image split.
```

Synthetic classes:

```text
acceptable_bold
regular_non_bold
medium_or_borderline
degraded_uncertain
```

Feature candidates:

```text
ink density
edge density
distance-transform mean stroke width
stroke-width variance
skeleton-to-ink ratio
connected-component statistics
horizontal and vertical projection profiles
HOG descriptors
crop aspect/area features
```

Primary safety metric:

```text
false clear = regular, medium, degraded, or uncertain heading classified as acceptable bold
```

Execution safety while the OCR conveyor runs:

```text
CUDA_VISIBLE_DEVICES=""
OMP_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
MKL_NUM_THREADS=2
NUMEXPR_NUM_THREADS=2
nice -n 15
ionice -c3
```

Also set `cv2.setNumThreads(1)` inside the experiment scripts if OpenCV is used.

Run output:

```text
data/work/typography-preflight/svm-v2/
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

Measured operating points:

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
mean SVM decision latency: about 0.09 ms/crop
```

Decision:

```text
Do not promote the SVM typography preflight to runtime authority yet.
It is computationally viable, but safe thresholds pass too few bold headings,
and useful-F1 thresholds false-clear too often.
Keep GOV_WARNING_HEADER_BOLD_REVIEW as Needs Review for submission.
```

Do not commit:

```text
generated crops
feature matrices
.joblib model files
metrics produced under data/work/
```

Commit only:

```text
experiment code
experiment README
documentation updates
```

Safe runtime policy after validation:

```text
strong bold evidence      -> typography preflight may pass
strong non-bold evidence  -> Needs Review or Fail Candidate only after validation
uncertain/degraded crop   -> Needs Review
```

Approved public COLA warning crops can be used as a positive smoke test, but
they cannot validate the dangerous negative case by themselves. Synthetic
non-bold and degraded examples are required for false-clear testing.

---

## 8. COLA Cloud Quota And Pull Strategy

The current source docs say:

- Pro tier: `10,000` detail views/month, `1,000,000` list records/month, `120` requests/minute.
- A detail view is viewing/fetching one record's full details via web, API, or MCP.
- List/search results count against list-record quota, not detail-view quota.
- The Python SDK exposes usage with `client.get_usage()`.
- The dataset schema says each COLA generally has associated `cola_images`, and each image row has an image URL/S3 key and metadata.

Operational interpretation:

- List/search pagination should mostly burn list-record quota.
- Fetching `client.colas.get(ttb_id)` should burn one detail view per COLA.
- Downloading image URLs may or may not be separately metered in the product UI, but it is not described as a separate "detail view" in the pricing page. Treat image download volume as bandwidth/time risk, not the primary quota risk, unless the usage endpoint proves otherwise.
- Always run `client.get_usage()` before and after a small pull to verify real quota movement.

Current quota after the completed staged acquisition:

```text
detail views: 6102 / 10000
list records: 42506 / 1000000
```

Completed stages:

```text
Stage A: 100-record safety pull
Stage B: 600-record checkpoint pull
Stage C: 1500-record checkpoint pull
Stage D: complete official-sample-3000-balanced to 3000 records
Stage E: plan no-overlap official-sample-next-3000-balanced extension
Stage F: 1000-record extension checkpoint
Stage G: complete extension to 3000 records
```

Why stop at 6000 for now:

- detail views are valuable and limited,
- OCR time grows quickly,
- a 6000-record corpus already supports a strong 3000/3000
  development/holdout story,
- the second 3000-record cohort gives a locked test with about `+/- 1.8`
  percentage-point conservative margin of error for binary proportions near 50%,
- remaining detail quota should be reserved for recovery pulls, spot checks,
  curated examples, and any failed-record repair.

Recommended current data policy:

```text
Do not pull more official data until full-corpus OCR/model evaluation proves
the next bottleneck.
```

The existing `official-sample-3000-balanced` and
`official-sample-next-3000-balanced` folders are now the primary official public
evaluation corpus.

---

## 9. Commands And Paths

Check local data counts:

```bash
python - <<'PY'
from pathlib import Path
base = Path("data/work/cola")
details = set()
apps = set()
images = []
for run in base.iterdir():
    if not run.is_dir():
        continue
    details.update(p.stem for p in (run / "api/details").glob("*.json") if (run / "api/details").exists())
    apps.update(p.stem for p in (run / "applications").glob("*.json") if (run / "applications").exists())
    if (run / "images").exists():
        images.extend([p for p in (run / "images").rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
print(len(details), "unique detail IDs")
print(len(apps), "unique application IDs")
print(len(images), "image files")
PY
```

Check COLA Cloud usage with SDK:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv
from colacloud import ColaCloud

load_dotenv()
client = ColaCloud(api_key=os.environ["COLACLOUD_API_KEY"])
usage = client.get_usage()
print(f"Detail views: {usage.detail_views.used} / {usage.detail_views.limit}")
print(f"List records: {usage.list_records.used} / {usage.list_records.limit}")
PY
```

Regenerate the current train/validation/holdout manifests:

```bash
python scripts/create_colacloud_evaluation_splits.py --force
```

Regenerate the field-support target/pair manifests:

```bash
python scripts/build_field_support_dataset.py --force
```

Run the full armored OCR conveyor for train/validation:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-conveyor/model-cache/hf \
  -e PADDLEOCR_HOME=/app/data/work/ocr-conveyor/model-cache/paddleocr \
  -v "$PWD":/app:Z \
  -w /app \
  localhost/labels-on-tap-app:local \
  bash -lc "python -m pip install paddlepaddle==3.2.0 paddleocr==3.3.3 openocr-python==0.1.5 >/tmp/tri-engine-pip.log && python scripts/run_ocr_conveyor.py --split train --split validation --engine doctr --engine paddleocr --engine openocr --chunk-size 16 --timeout-seconds 1200 --output-dir data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16"
```

Dry-run the holdout conveyor manifest only after train/validation is complete
and the final settings are nearly frozen:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-conveyor/model-cache/hf \
  -e PADDLEOCR_HOME=/app/data/work/ocr-conveyor/model-cache/paddleocr \
  -v "$PWD":/app:Z \
  -w /app \
  localhost/labels-on-tap-app:local \
  bash -lc "python -m pip install paddlepaddle==3.2.0 paddleocr==3.3.3 openocr-python==0.1.5 >/tmp/tri-engine-pip.log && python scripts/run_ocr_conveyor.py --split holdout --engine doctr --engine paddleocr --engine openocr --chunk-size 16 --dry-run --output-dir data/work/ocr-conveyor/tri-engine-holdout-dry-run"
```

Do not run the holdout OCR/evaluation until OCR preprocessing, evidence
attachment, DistilRoBERTa threshold, and graph/compliance settings are frozen.
The conveyor output is gitignored:

```text
data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/
  manifest/images.csv
  manifest/jobs.csv
  jobs/<job_id>/stdout.log
  jobs/<job_id>/stderr.log
  jobs/<job_id>/result.json
  runs/<job_id>/rows.csv
  runs/<job_id>/ocr/<engine>/*.json
  summary.json
```

Rerun the current BERT-family text-pair experiments:

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

Run current tests:

```bash
pytest -q
```

Run project bootstrap:

```bash
python scripts/bootstrap_project.py --if-missing
```

Rebuild app locally:

```bash
docker compose build
docker compose up -d
curl http://localhost:8000/health
```

---

## 10. Immediate Next Steps

1. Keep the public deployment stable.
2. Use `data/work/cola/evaluation-splits/field-support-v1/` as the canonical
   split source.
3. Completed: chunk-size 16 armored OCR conveyor finished for train/validation.
4. Completed: isolated OpenCV/SVM typography preflight was built and measured.
5. Attach conveyor OCR evidence to the generated field-support pair manifests.
6. Rerun DistilRoBERTa on OCR-backed candidate evidence.
7. Compare all serious candidates with identical statistics and latency tables.
8. Freeze thresholds and architecture.
9. Evaluate once on the 3000-record locked holdout cohort.
10. Convert final metrics into `docs/performance.md`, `MODEL_LOG.md`,
   `TRADEOFFS.md`, and README.
11. Build 300-500 synthetic negative cases from `PHASE1_REJECTION.md`.
12. Keep legal reasoning/guidance last; deterministic evidence first.

---

## 11. What To Tell A Reviewer

Safe phrasing:

> The deployed prototype is local-first and does not rely on hosted OCR/ML APIs at runtime. For evaluation, I built a deterministic public-data sampling workflow. Direct TTB printable forms were parsed successfully, but the direct attachment endpoint was unstable during the weekend sprint, so I used COLA Cloud as a development-only bridge for public label images. All measured OCR/model metrics are from local OCR over COLA Cloud-derived public label images, not from COLA Cloud's hosted OCR.

Do not say:

```text
The model is production accurate.
The public rejected-label corpus was available.
The app uses COLA Cloud at runtime.
The current OCR metrics came directly from TTB attachment downloads.
```

---

## 12. Latest Relevant Commits Before This Handoff

```text
387b3b9 fix: reuse cached COLA Cloud detail records
a55bb13 docs: clarify COLA Cloud calibration handoff
32b714c docs: add model architecture command center
c740280 test: add FoodBaseBERT NER control
24fb722 test: add OSA domain NER benchmark
0120ce3 test: add WineBERT entity benchmark
9d3e4f0 test: add deterministic OCR ensemble benchmark
45b8b26 docs: add LayoutLMv3 ensemble arbitration future path
8335682 docs: add OCR smoke synthesis to tradeoffs
10346dd docs: add OCR comparison tables to tradeoffs
f8fb22c test: add ABINet crop recognition benchmark
5df3da3 test: add FCENet ASTER benchmark
1dfbd59 test: add ASTER crop recognition benchmark
ddd8b1b test: add PARSeq crop recognition benchmark
```

---

## 13. If A New Codex Session Starts

Read these files in order:

```text
HANDOFF_DETAILED_2026-05-03.md
README.md
TASKS.md
MODEL_ARCHITECTURE.md
MODEL_LOG.md
TRADEOFFS.md
docs/performance.md
docs/public-cola-etl.md
```

Then run:

```bash
git status --short
pytest -q
```

Before any data pull, run the COLA Cloud usage check and confirm no live API key is in tracked files.
