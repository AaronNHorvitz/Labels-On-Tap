# HANDOFF.md - Labels On Tap Restart Guide

**Project:** Labels On Tap
**Canonical URL:** `https://www.labelsontap.ai`
**Repo:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Last updated:** May 3, 2026

Read this first if a new Codex session starts cold.

For the full restart-grade handoff, including today's experiment history,
data-source distinctions, COLA Cloud quota strategy, and next-step playbook,
read [HANDOFF_DETAILED_2026-05-03.md](HANDOFF_DETAILED_2026-05-03.md).

## Current Mission

Labels On Tap is a Treasury/TTB take-home prototype. The core proof is:

```text
COLAs Online-style application data
  + submitted label artwork
  -> local OCR / parsing
  -> deterministic field comparison
  -> raw Pass / Needs Review / Fail with evidence
  -> reviewer-policy queue where configured
```

The app is already deployed and working. The current sprint has shifted from app scaffolding to proving OCR/form matching quality with public COLA data and conservative statistics.

## Non-Negotiables

- Canonical URL is `https://www.labelsontap.ai`, not `.com`.
- Do not use hosted OCR/ML APIs at runtime.
- Do not commit `.env`, API keys, raw bulk data, SQLite databases, downloaded images, OCR outputs, or model checkpoints.
- Keep raw/bulk/evaluation data under gitignored `data/work/`.
- Keep the deployed FastAPI app stable; experiments live under `experiments/`.
- Do not train graph models on CPU. If CUDA is unavailable, stop and fix the GPU path.
- Do not claim production OCR accuracy from calibration data.
- False clears matter more than pretty recall.

## Important Files

| File | Purpose |
|---|---|
| `README.md` | Main submission readme and high-level project story |
| `TASKS.md` | Sprint command center |
| `MODEL_ARCHITECTURE.md` | End-to-end model architecture, split design, and promotion gates |
| `MODEL_LOG.md` | OCR/model experiment ledger |
| `docs/performance.md` | Measured performance and calibration metrics |
| `docs/ocr-conveyor.md` | Armored tri-engine OCR conveyor design |
| `TRADEOFFS.md` | Architecture and data trade-offs |
| `DEMO_SCRIPT.md` | Reviewer demo flow |
| `PHASE1_REJECTION.md` | Known-bad/rejection checklist |
| `experiments/graph_ocr/` | Experimental graph-aware OCR evidence scorer |
| `experiments/field_support/` | Experimental BERT-family field-support classifiers |
| `scripts/run_ocr_conveyor.py` | Resumable subprocess-isolated OCR runner |

## Current App State

- FastAPI + Jinja2/HTMX + local CSS.
- Docker Compose + Caddy deployment.
- AWS Lightsail deployment is live.
- Fixture demos work.
- Upload preflight exists.
- Photo OCR intake demo exists for real bottle/can/shelf photos without
  application fields.
- Batch upload exists.
- CSV export exists.
- `country_of_origin` and `imported` are first-class fields.
- Current runtime reports raw triage verdicts; configurable reviewer-policy
  queues are documented but not implemented yet.
- Runtime includes a narrow real-adapted typography preflight for
  `GOVERNMENT WARNING:` boldness. Confident heading crops can clear the
  boldness check; missing/uncertain crops still route to Needs Review.
- Tests last passed in the local app container with `78 passed`.

Useful verification:

```bash
pytest -q
python scripts/bootstrap_project.py --if-missing
curl https://www.labelsontap.ai/health
```

## Human Review Policy Layer

This is the newest product decision to preserve human judgment while still
supporting Sarah's 200-300 application batch workflow.

Planned settings:

```text
Send unknown government-warning cases to human review: Yes / No
Require reviewer approval before rejection: Yes / No
Require reviewer approval before acceptance: Yes / No
```

Default posture:

```text
Unknown government warning human review: No
Before rejection: No
Before acceptance: No
```

Routing:

```text
Pass + acceptance review off -> Ready to accept
Pass + acceptance review on  -> Acceptance review
Fail + rejection review off  -> Ready to reject
Fail + rejection review on   -> Rejection review
Warning unknown + warning review off -> Fail, then normal fail routing
Warning unknown + warning review on  -> Manual evidence review
Needs Review                 -> Manual evidence review
```

Warning-unknown cases are special: if the reviewer does not enable human review
for unknown/unverifiable government-warning evidence, the system should fail the
label because the warning is mandatory and the applicant must provide readable
evidence.

Reviewer actions:

```text
Accept
Reject
Request correction / better image
Override with note
Escalate
```

Implementation note: do not describe this as live runtime behavior until the app
stores `raw_verdict`, `policy_queue`, and reviewer action metadata in job
results/CSV exports.

## Current Data State

Direct TTB Registry ETL:

- `810` parsed public COLA forms.
- `1,433` discovered attachment records.
- Direct attachment endpoint was returning HTML error pages during May 2 audit.
- Invalid direct attachment rows were marked pending.

COLA Cloud development bridge:

- Used only because TTBOnline.gov was unstable.
- Not a runtime dependency.
- Full staged local corpus now contains `6,000` unique fetched public COLA
  applications across two non-overlapping cohorts.
- `official-sample-3000-balanced`: `3,000` application/detail JSONs and
  `5,353` label images.
- `official-sample-next-3000-balanced`: `3,000` application/detail JSONs and
  `5,082` label images.
- Combined official public label-image corpus: `10,435` local image files.
- Fetch failures: `0`.
- Overlap between the two 3,000-record cohorts: `0`.
- Application-level evaluation split manifests were generated under
  `data/work/cola/evaluation-splits/field-support-v1/`.
- Split counts: `2,000` train, `1,000` validation, `3,000` locked holdout.
- Field-support target/pair manifests were generated under
  `data/work/cola/field-support-datasets/field-support-v1/`.
- Field-support dataset counts: `31,139` positive field targets and `93,417`
  pair examples with a `1:2` positive-to-shuffled-negative design.
- Trained field-support text-pair experiments were run on the new split:
  DistilRoBERTa and RoBERTa-base, both outside the runtime app.
- Current OCR/model metrics remain COLA Cloud-derived public calibration
  metrics, not direct TTB attachment-download metrics.

Local public comparison demo:

- `/cola-cloud-demo` selects a deterministic local public example from
  `data/work/cola/` when that corpus exists.
- It copies all associated label panels into a normal `data/jobs/{job_id}/`
  upload workspace.
- It loads cached local OCR conveyor output when available, otherwise falls
  back to the local OCR adapter.
- It renders application fields beside OCR evidence, best panel, match score,
  and reviewer action.
- It does not call COLA Cloud, TTB, or hosted OCR at runtime. If the local
  corpus is missing, it shows a missing-data page.

Key local paths:

```text
data/work/cola/official-sample-3000-balanced/
data/work/cola/official-sample-next-3000-balanced/
data/work/cola/evaluation-splits/field-support-v1/
data/work/cola/field-support-datasets/field-support-v1/
data/work/public-cola/parsed/ocr/evaluations/
data/work/graph-ocr/
```

These are intentionally gitignored.

## Current OCR Metrics

Corrected 100-application baseline after mapping `abv`, `volume`, and `volume_unit`:

| Field | Match Rate |
|---|---:|
| Brand name | 0.7100 |
| Fanciful name | 0.6500 |
| Class/type | 0.4900 |
| Alcohol content | 0.9149 |
| Net contents | 0.8372 |
| Country of origin | 0.7895 |
| Applicant/producer | 0.0200 |

This is calibration only. It is not production accuracy.

## Graph OCR Experiment State

The current graph experiment is a post-OCR evidence scorer, not a pixel-to-text OCR model.

Architecture:

```text
cached OCR boxes
  -> KNN graph over OCR fragments
  -> PyTorch message-passing scorer
  -> field-support score
  -> deterministic triage layer
```

Current best run:

```text
run_name: gpu-safety-neg2-e40
device: cuda
epochs: 40
negative_loss_weight: 2.0
false_clear_tolerance: 0.0
```

Best POC metrics:

| Metric | Baseline | Graph |
|---|---:|---:|
| Accuracy | 0.8947 | 0.9408 |
| Precision | 0.8438 | 0.9531 |
| Recall | 0.7105 | 0.8026 |
| F1 | 0.7714 | 0.8714 |
| False-clear rate | 0.0439 | 0.0132 |

See `MODEL_LOG.md` for details.

## BERT Field-Support Experiment State

The current BERT-family runs are weak-supervision text-pair arbiters, not final
OCR-backed classifiers. They train on accepted public application field values
and same-split shuffled negative values.

Current runs:

| Model | Holdout F1 | False-Clear Rate | CPU Mean / Pair | Decision |
|---|---:|---:|---:|---|
| DistilRoBERTa | 0.999872 | 0.000128 | 15.76 ms | Preferred current text-pair arbiter |
| RoBERTa-base | 0.999777 | 0.000223 | 33.35 ms | Not worth extra latency yet |

Outputs:

```text
data/work/field-support-models/distilroberta-field-support-v1-e1/
data/work/field-support-models/roberta-base-field-support-v1-e1/
```

Next gate: attach docTR/PaddleOCR/OpenOCR candidate evidence to the same pair
manifests and rerun DistilRoBERTa before making any OCR-quality claim.

## OCR Conveyor Layer

The max-win architecture is still:

```text
docTR + PaddleOCR + OpenOCR
  -> DistilRoBERTa field-support arbiter
  -> graph-aware evidence scorer
  -> deterministic compliance
```

The armored conveyor is now built and smoke-tested. It preflights images, skips
corrupt files, runs OCR chunks in subprocesses, records stdout/stderr per chunk,
and resumes completed jobs.

Completed conveyor checks:

| Run | Result |
|---|---|
| `tri-engine-smoke-3` | 3 valid images; docTR, PaddleOCR, and OpenOCR all completed; 9 OCR rows; 0 row errors |
| `tri-engine-smoke-8` | 8 valid images; all three engines completed; 24 OCR rows; 0 row errors |
| `tri-engine-smoke-16` | 13 valid images; 3 invalid/corrupt images skipped by preflight; all three engines completed; 39 OCR rows; 0 row errors |
| `tri-engine-train-val-v1-chunk16` dry run | 5,353 image rows; 5,179 valid images; 174 invalid/corrupt skipped; 975 planned jobs |

Active train/validation run snapshot:

```text
snapshot_time: 2026-05-03T12:20:42-05:00
container: 253b9caaf335
output_dir: data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/
completed_chunk_results: 975 / 975
completed_by_engine:
  docTR: 325
  PaddleOCR: 325
  OpenOCR: 325
ocr_row_errors_observed: 0
```

Command used for the completed train/validation run:

```bash
podman run --rm \
  -e HF_HOME=/app/data/work/ocr-conveyor/model-cache/hf \
  -e PADDLEOCR_HOME=/app/data/work/ocr-conveyor/model-cache/paddleocr \
  -v "$PWD":/app:Z \
  -w /app \
  localhost/labels-on-tap-app:local \
  bash -lc "python -m pip install paddlepaddle==3.2.0 paddleocr==3.3.3 openocr-python==0.1.5 >/tmp/tri-engine-pip.log && python scripts/run_ocr_conveyor.py --split train --split validation --engine doctr --engine paddleocr --engine openocr --chunk-size 16 --timeout-seconds 1200 --output-dir data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16"
```

Estimated runtime for the full train/validation conveyor is roughly 10-12 hours,
with PaddleOCR the slowest engine. Do not run holdout yet. Holdout OCR should
remain sealed until preprocessing, OCR evidence attachment, DistilRoBERTa
threshold, graph scorer, and deterministic compliance settings are frozen.
Outputs stay under gitignored `data/work/ocr-conveyor/`.

## Typography Preflight Plan

Jenny Park's stakeholder note says `GOVERNMENT WARNING:` must be all caps and
bold. The all-caps requirement is deterministic. Boldness now has a narrow
runtime preflight under `GOV_WARNING_HEADER_BOLD_REVIEW`: confident real-adapted
heading crops can pass, while missing or uncertain crops still route to human
review.

The isolated OpenCV typography preflight is now implemented and measured:

```text
warning heading crop
  -> OpenCV stroke/shape features
  -> CPU-only SVM / LightGBM / Logistic Regression / MLP comparison
  -> strict-veto or learned stacker/reject-threshold ensemble
  -> bold / non-bold / uncertain preflight
  -> deterministic compliance layer
```

Do not touch the running OCR conveyor to build it. Use only:

```text
experiments/typography_preflight/
data/work/typography-preflight/
```

Synthetic dataset:

```text
train:      20,000 crops
validation: 5,000 crops
test:       5,000 crops
```

Hold out font families and distortion recipes across splits. The primary metric
is false-clear rate: non-bold, medium, degraded, or uncertain warning headings
incorrectly accepted as bold.

First binary result:

```text
run_output: data/work/typography-preflight/svm-v2/
model: StandardScaler + SGDClassifier hinge-loss linear SVM
feature_count: 3,480
mean_decision_latency: about 0.09 ms/crop
zero-validation-false-clear operating point:
  test F1: 0.0321
  test precision: 0.9737
  test recall: 0.0163
  test false-clear rate: 0.0004
0.25% validation false-clear operating point:
  test F1: 0.1170
  test false-clear rate: 0.0059
5% validation false-clear operating point:
  test F1: 0.7757
  test false-clear rate: 0.0733
```

Important correction:

```text
The svm-v2 run is now treated as a flawed-target baseline.
Manual inspection found that it mixed source font weight, image quality, and
auto-clearance policy into one binary label. That made some bold-but-degraded
crops negative and made some readable medium/semibold crops review cases.
```

Corrected audit data:

```text
builder: experiments/typography_preflight/build_audit_dataset.py
inspection_output: data/work/typography-preflight/audit-v5/
contact_sheet: data/work/typography-preflight/audit-v5/index.html
```

`audit-v5` separates labels:

```text
font_weight_label             bold / not_bold
header_text_label             correct / incorrect
quality_label
visual_font_decision_label
header_decision_label
```

The source `borderline` font class was removed. Generated bold fonts are bold;
medium/semibold/demibold/light/thin/book/regular faces are not bold.
`needs_review_unclear` is reserved for unreadable/degraded crops that require a
human to inspect or reject the submission quality.

Corrected side-by-side comparison:

```text
script: experiments/typography_preflight/compare_models.py
run_output: data/work/typography-preflight/model-comparison-v1/
train: 6,000 crops
validation: 1,500 crops
test: 1,500 crops
```

Test metrics:

| Task | Model | Accuracy | Macro F1 | False-Clear Rate | Batch ms/crop | Single-row ms |
|---|---|---:|---:|---:|---:|---:|
| Visual font decision | SVM | 0.9400 | 0.9396 | 0.0360 | 0.0048 | 0.0795 |
| Visual font decision | XGBoost | 0.9567 | 0.9567 | 0.0551 | 0.0032 | 0.1151 |
| Visual font decision | CatBoost | 0.9480 | 0.9479 | 0.0711 | 0.0054 | 1.9588 |
| Header text decision | SVM | 0.8420 | 0.8393 | 0.1101 | 0.0055 | 0.0801 |
| Header text decision | XGBoost | 0.8560 | 0.8546 | 0.1612 | 0.0033 | 0.1693 |
| Header text decision | CatBoost | 0.8447 | 0.8430 | 0.1702 | 0.0059 | 1.9376 |

Interpretation:

```text
XGBoost has the best raw F1/accuracy.
SVM has the lowest false-clear rate and fastest single-row latency.
CatBoost is viable but slower and not currently safer.
Hard-argmax false-clear rates are still too high for runtime authority.
Next step is validation-threshold tuning so weak bold/correct predictions
route to needs_review_unclear.
```

Extended 80/20 comparison:

```text
script: experiments/typography_preflight/compare_extended_models.py
run_output: data/work/typography-preflight/model-comparison-extended-80-20-v1/
train: 8,000 crops
test: 2,000 crops
models: SVM, XGBoost, LightGBM, Logistic Regression, MLP, strict-veto ensemble
```

| Task | Model | Accuracy | Macro F1 | False-Clear Rate | Single-row ms |
|---|---|---:|---:|---:|---:|
| Visual font decision | SVM | 0.9390 | 0.9385 | 0.0218 | 0.0780 |
| Visual font decision | XGBoost | 0.9720 | 0.9720 | 0.0293 | 0.1120 |
| Visual font decision | LightGBM | 0.9760 | 0.9760 | 0.0263 | 1.9275 |
| Visual font decision | Logistic Regression | 0.9655 | 0.9656 | 0.0195 | 0.0780 |
| Visual font decision | MLP | 0.9650 | 0.9650 | 0.0203 | 0.1463 |
| Visual font decision | Strict-veto ensemble | 0.9115 | 0.9131 | 0.0038 | 2.6810 |
| Header text decision | SVM | 0.8560 | 0.8539 | 0.0766 | 0.0792 |
| Header text decision | XGBoost | 0.8845 | 0.8832 | 0.1404 | 0.1144 |
| Header text decision | LightGBM | 0.8915 | 0.8911 | 0.1149 | 1.8772 |
| Header text decision | Logistic Regression | 0.8815 | 0.8811 | 0.1231 | 0.0789 |
| Header text decision | MLP | 0.8840 | 0.8841 | 0.0803 | 0.1466 |
| Header text decision | Strict-veto ensemble | 0.7505 | 0.7510 | 0.0360 | 2.7161 |

Interpretation:

```text
LightGBM wins raw F1.
Strict-veto wins safety by sharply reducing false clears.
The strict-veto model lowers F1 because it sends more cases to review.
That is acceptable for a government pilot posture, but still not runtime
authority until tested on real warning-heading crops.
```

Large 5x geometry-stress comparison:

```text
script: experiments/typography_preflight/compare_large_ensemble_models.py
run_output: data/work/typography-preflight/model-comparison-large-geometry-v1/
base_train: 32,000 crops
calibration: 8,000 crops
full_train: 40,000 crops
test: 10,000 crops
geometry: 50% normal, 50% rotated/bent
```

Models and policies:

```text
base models:
  SVM
  LightGBM
  Logistic Regression
  MLP

ensembles:
  strict-veto ensemble
  calibrated logistic-regression stacker
  LightGBM reject-threshold stacker
  XGBoost reject-threshold stacker
  CatBoost stacker
```

Headline test metrics:

| Task | Policy | Test F1 | False-Clear Rate | P95 ms |
|---|---|---:|---:|---:|
| Visual font decision | Strict-veto ensemble | 0.9440 | 0.0024 | 2.4952 |
| Visual font decision | CatBoost stacker | 0.9878 | 0.0080 | 3.0394 |
| Header text decision | XGBoost reject threshold | 0.6131 | 0.0027 | 3.0246 |
| Header text decision | CatBoost stacker | 0.9020 | 0.0857 | 3.8643 |

Interpretation:

```text
Visual boldness has a credible future reviewer-assist path.
Strict-veto is the visual safety winner.
CatBoost is the visual raw-F1 winner.
Header text correctness still false-clears too often for autonomous clearance
unless a reject-threshold policy sends many cases to review.
All learned stacker latency is end-to-end from raw engineered features.
```

Decision:

```text
Do not promote the synthetic-only typography stackers to runtime authority.
They remain useful historical experiments, but the runtime path is the
real-adapted logistic preflight described below.
```

Real approved COLA smoke:

```text
script: experiments/typography_preflight/real_cola_smoke.py
run_output: data/work/typography-preflight/real-cola-smoke-v1/
sample: 100 approved applications / 203 label images
cached_ocr_rows: 15,537
heading_crops: 124 across 68 applications
crop sources: PaddleOCR 62, OpenOCR 59, docTR 3
```

Real-smoke result:

```text
The trained typography stackers are fast enough, roughly 3-5 ms/crop p95 for
most policies, but they do not transfer cleanly enough from synthetic crops to
real approved COLA crops. Boldness policies clear only 1-8% of applications.
Warning-text policies clear only 0-3% of applications. Keep typography as
human review for the MVP.
```

Real-adapted runtime correction:

```text
script: experiments/typography_preflight/real_cola_smoke.py
runtime model: app/models/typography/boldness_logistic_v1.json
runtime services:
  app/services/typography/warning_heading.py
  app/services/typography/features.py
  app/services/typography/boldness.py

corrected cropper run:
  applications: 3,000 train/validation apps
  valid images: 5,179
  warning-heading crops: 4,362
  applications with heading crop: 2,356

model:
  real positive train crops: 3,083 approved COLA warning headings
  real positive holdout crops: 768 approved COLA warning headings
  synthetic negative/review crops: non-bold and degraded warning-heading crops
  model family: Logistic Regression exported to JSON coefficients
  runtime dependency: numpy + OpenCV only, no scikit-learn/joblib

selected threshold:
  threshold: 0.9545819397993311
  validation false-clear rate: 0.000624
  synthetic holdout false-clear rate: 0.001800
  synthetic holdout F1: 0.865570
  approved COLA real-positive holdout clear rate: 0.921875

sanity check:
  a real approved COLA PaddleOCR heading crop returned pass with probability
  0.999944 and about 37 ms combined crop/classify time in the app container.

test check:
  podman run --rm -v "$PWD":/app:Z -w /app \
    localhost/labels-on-tap-app:local pytest -q
  result: 78 passed
```

Interpretation:

```text
This solves the immediate MVP failure mode. The app no longer treats boldness
as impossible to automate; it uses real approved COLA warning headings to clear
strong bold evidence. It still sends weak/noisy/no-crop evidence to Needs
Review, which preserves the low false-clear posture.
```

Important statistical update:

```text
The bridge model is still the deployed MVP runtime path, but the v6 correction
has now been built and tested offline. The clean audit-v6 image set mixes real
approved COLA warning-heading crops, real-COLA-background synthetic mutations,
no-warning panels, synthetic bold positives, synthetic non-bold negatives,
synthetic incorrect headings, and unreadable/review crops.
```

Separate the problem into layers:

| Layer | Question | Labels |
|---|---|---|
| Panel warning detection | Does this image panel contain the government warning heading? | `warning_present`, `warning_absent`, `unreadable_review` |
| Heading text check | If a heading crop exists, is the heading text correct? | `correct_government_warning`, `incorrect_heading_text`, `unreadable_review` |
| Heading boldness | If a heading crop exists, is the heading bold? | `bold`, `not_bold`, `unreadable_review` |

Multi-panel application rule:

```text
Scan every label panel for the application.
Do not penalize a front/neck/side panel just because it lacks the warning.
Application-level warning evidence passes when at least one panel contains a
valid warning heading that clears text/caps/boldness requirements.
If no panel contains valid warning evidence, route to Needs Review or Fail
depending the configured policy.
```

Completed v6 requirements:

- Split by TTB ID/application ID, never by crop.
- Keep all generated crops, contact sheets, metrics, and trained checkpoints
  under gitignored `data/work/typography-preflight/audit-v6/` and related
  `data/work/typography-preflight/*audit-v6*` experiment directories.
- Commit code/docs/manifests only, not raw public images or model checkpoints,
  unless a tiny explicit runtime export is intentionally promoted.
- Generate HTML contact sheets for human inspection before trusting labels.
- Train classical models first: Logistic Regression, SVM, LightGBM, CatBoost.
- Train a small CNN baseline as a challenger: MobileNetV3-Small crop classifier
  for `bold`, `not_bold`, `unreadable_review`, and `not_applicable`.
- Compare false-clear rate, macro F1, real approved bold clear rate,
  review-routing rate, and CPU latency.
- Promote only if the v6 model beats or materially clarifies the current
  logistic bridge and stays safe on false clears.

Reference framing:

```text
Hastie, Tibshirani, and Friedman, The Elements of Statistical Learning,
2nd ed., Springer, 2009.
```

Use this as a classical statistical-learning preflight, not as a replacement
for OCR or as final compliance authority until validated.

## Current Typography Offline Result - Audit-v6 CNN-Inclusive Ensemble

The latest defensible comparison is:

```text
code:
  experiments/typography_preflight/compare_audit_v6_cnn_ensemble.py

output:
  data/work/typography-preflight/model-comparison-audit-v6-cnn-ensemble-v1/

dataset:
  audit-v6
  train / validation / test = 6,000 / 1,500 / 1,500

methodology:
  SVM, XGBoost, LightGBM, Logistic Regression, MLP, CatBoost, and MobileNetV3
  CNN all use the same audit-v6 target and split.
  Base learners produce 5-fold out-of-fold train probabilities.
  Stackers train on OOF probabilities from all bases, including CNN.
  Reject thresholds tune on validation only.
  Final metrics score once on untouched test.
```

Headline results:

| Model / policy | Train F1 | Train false-clear | Test F1 | Test false-clear |
|---|---:|---:|---:|---:|
| MobileNetV3 CNN base | 0.9523 | 0.0022 | 0.9686 | 0.0055 |
| Logistic stacker, all bases + CNN | 0.9932 | 0.0064 | 0.9908 | 0.0099 |
| LightGBM reject, all bases + CNN | 0.9683 | 0.0000 | 0.9552 | 0.0033 |
| XGBoost reject, all bases + CNN | 0.9784 | 0.0000 | 0.9656 | 0.0044 |

Decision:

```text
The CNN is the safest base learner. CNN-inclusive reject ensembles are the next
offline promotion candidates. Do not swap them into runtime yet. The MVP should
keep the real-adapted JSON logistic bridge unless/until a full app-level
promotion test is frozen and passed.
```

## GPU Setup

Host:

- Fedora Kinoite 43
- RTX 4090
- NVIDIA driver `580.142`
- CUDA reported by driver: `13.0`

If `nvidia-smi` fails after reboot, create the device nodes:

```bash
sudo /usr/bin/nvidia-modprobe -u -c=0
sudo /usr/bin/nvidia-modprobe -u -c=0 -m
ls -l /dev/nvidia*
nvidia-smi
```

The local CUDA venv is `.venv-gpu` and is gitignored.

Create or repair it:

```bash
python -m venv .venv-gpu
.venv-gpu/bin/python -m pip install --upgrade pip
.venv-gpu/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu130 torch torchvision
.venv-gpu/bin/python -m pip install rapidfuzz pydantic python-dotenv pillow
```

Verify CUDA:

```bash
.venv-gpu/bin/python - <<'PY'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0))
x = torch.randn(2048, 2048, device="cuda")
print((x @ x.T).shape)
PY
```

If `torch.cuda.is_available()` is false, stop. Do not train on CPU.

## Reproduce Current Best Graph Run

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 40 \
  --run-name gpu-safety-neg2-e40 \
  --device cuda \
  --negative-loss-weight 2.0 \
  --false-clear-tolerance 0.0
```

Outputs:

```text
data/work/graph-ocr/gpu-safety-neg2-e40/
  config.json
  model.pt
  predictions.csv
  summary.json
```

## Statistical Caution

The user is worried, correctly, that as sample size grows, performance estimates will converge toward the true value and may look weaker. Treat that as a strength of the submission, not a problem to hide.

Current language should be:

- The prototype is a reviewer-support triage tool.
- Raw `Pass`/`Fail` verdicts are evidence signals; final acceptance/rejection
  can be gated by reviewer-policy settings.
- Current OCR/model numbers are calibration signals until rerun on the full
  6,000-record corpus.
- Use `official-sample-3000-balanced` as the development cohort.
- Use `official-sample-next-3000-balanced` as the locked holdout cohort.
- Model-selection split manifests now exist:
  `data/work/cola/evaluation-splits/field-support-v1/`.
- The split uses `2,000` train and `1,000` validation/calibration
  applications from the development cohort.
- After model family, features, and thresholds are locked, optionally refit
  the chosen model on all `3,000` development applications and evaluate once
  on the untouched `3,000`-application holdout.
- A locked test of `3,000` gives about `+/- 1.8 percentage points`
  conservative 95% margin of error for binary proportions near 50%.
- If larger samples reveal weaker field performance, route uncertain cases to `Needs Review` and document limitations.

Do not say the app is production-ready. Say it demonstrates a measured, auditable path to production readiness.

## Full-Corpus Model Rerun Plan

Yes, the project can rerun the model-statistics table across the candidate
permutations, but do it in the right order:

1. Recompute cached OCR/evidence for docTR, PaddleOCR, and OpenOCR/SVTRv2 over
   the development cohort first.
2. Train/tune BERT-family field-support scorers on the `2,000`/`1,000`
   train/validation split.
3. Compare deterministic ensemble, OSA/DistilRoBERTa/RoBERTa-style arbiters,
   and graph-aware evidence scorer using the same validation examples.
4. Freeze the final scoring policy and thresholds before touching the locked
   holdout.
5. Report the same side-by-side statistics on the holdout: accuracy,
   precision, recall, specificity, F1, false-clear rate, confusion counts,
   per-field F1, and latency.

Do not claim OCR engines were fine-tuned unless true OCR labels exist. The
current official COLA data supports training/tuning the field-support arbiter,
not pixel-level OCR recognizers.

## Best Next Steps

1. Keep the deployed app stable.
2. Use `MODEL_LOG.md` as the experiment ledger for all OCR/model runs.
3. Run the full chunk-size 16 OCR conveyor over train/validation for docTR, PaddleOCR, and OpenOCR.
4. Completed: isolated OpenCV typography-preflight experiments, including the
   large 5x geometry-stress ensemble comparison.
5. Attach conveyor OCR evidence to the existing field-support pair manifests.
6. Rerun DistilRoBERTa on OCR-backed candidate evidence.
7. Compare them against deterministic ensemble and graph-aware evidence scorer.
8. Freeze thresholds, then evaluate once on the 3,000-record holdout cohort.
9. Convert final metrics into `MODEL_LOG.md`, `TRADEOFFS.md`,
   `docs/performance.md`, and the README.
