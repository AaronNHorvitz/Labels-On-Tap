# Model Log

This is the chronological model and experiment ledger for Labels On Tap. The
goal is to make the modeling process inspectable: what was tested, what worked,
what failed, what shipped, and what was deliberately deferred.

Raw experiment outputs, model artifacts, OCR caches, and downloaded public data
are intentionally gitignored under `data/work/`. This file records the useful
results without committing bulk data.

## Executive Summary

Labels On Tap started as a straightforward local OCR and rule-checking app. The
discovery notes changed the target: the prototype needed to compare COLAs
Online-style application fields against submitted label artwork, process
multi-panel applications, respect a 5-second-per-label usability constraint, and
route uncertainty to human review.

The final runtime is intentionally conservative:

```text
application fields + label artwork
  -> local OCR / fixture OCR
  -> optional DistilRoBERTa field-support evidence
  -> warning-heading crop + boldness preflight
  -> deterministic compliance rules
  -> reviewer policy queue
```

The production-facing app does **not** let an LLM make compliance decisions. The
ML pieces support evidence extraction and triage. The final compliance outcome
is source-backed and deterministic.

The strongest shipped decisions:

- Use local OCR because stakeholder notes warned that outbound cloud ML calls
  may fail in a government network.
- Keep docTR as the stable deployed OCR path because alternate OCR engines did
  not clear the accuracy/safety/runtime bar strongly enough before deadline.
- Use DistilRoBERTa only as optional field-support evidence, not as OCR and not
  as the compliance decision maker.
- Add a narrow warning-heading boldness preflight because the interview notes
  explicitly called out `GOVERNMENT WARNING:` capitalization and boldness.
- Keep graph scoring, LayoutLMv3, tri-engine OCR arbitration, and CNN-inclusive
  typography ensembles documented as promotion candidates rather than rushing
  them into the live app.

## Metric Definitions

Several experiments use different labels. To avoid word soup, this is the
plain-English reading used throughout the project.

### Field-Support Metrics

Field-support rows ask: does this OCR/application text fragment support this
expected application field?

| Term | Meaning |
|---|---|
| True positive | A correct supporting text fragment is marked as supporting the field. |
| True negative | A wrong/shuffled text fragment is rejected as not supporting the field. |
| False positive / false clear | A wrong text fragment is incorrectly accepted as supporting the field. |
| False negative | A correct supporting text fragment is missed. |

For government triage, the dangerous case is the false clear: the system says
the evidence supports the application when it should not.

### Typography Boldness Metrics

The typography task asks: is the isolated `GOVERNMENT WARNING:` heading
confidently bold?

| Term | Meaning |
|---|---|
| Bold | The heading has strong bold evidence. |
| Not bold | The heading is readable but not bold. |
| Unreadable review | Image quality is too poor to decide. |
| Not applicable | The crop/panel does not contain the warning heading. |
| False clear | A not-bold, unreadable, or not-applicable crop is incorrectly cleared as bold. |

The runtime safety posture is asymmetric: strong evidence can clear; weak or
uncertain evidence routes to review.

## Evaluation Corpus

Direct public TTBOnline image access became unreliable during the sprint, so the
official evaluation corpus was built from COLA Cloud public COLA data. This is
still public COLA data; it is not private COLAs Online data.

Source artifacts:

```text
data/work/cola/evaluation-splits/field-support-v1/split_summary.json
data/work/cola/field-support-datasets/field-support-v1/dataset_summary.json
```

Sampling method:

```text
Two-stage deterministic sample:
1. random business-day clusters within month strata,
2. without-replacement secondary balancing by product type, import bucket,
   and single-panel vs multi-panel image complexity.
```

Seed:

```text
20260503
```

The split unit is the COLA application / TTB ID. No TTB ID overlaps exist across
train, validation, and holdout.

| Split | Applications | Images |
|---|---:|---:|
| Train | 2,000 | 3,564 |
| Validation | 1,000 | 1,789 |
| Locked holdout | 3,000 | 5,082 |
| Total | 6,000 | 10,435 |

Distribution checks from the split summary:

| Split | Domestic | Imported | Wine | Distilled spirits | Malt beverage | Single-panel | Multi-panel |
|---|---:|---:|---:|---:|---:|---:|---:|
| Train | 1,301 | 699 | 913 | 729 | 358 | 877 | 1,123 |
| Validation | 647 | 353 | 458 | 365 | 177 | 437 | 563 |
| Locked holdout | 1,774 | 1,226 | 1,283 | 1,151 | 566 | 1,503 | 1,497 |

## Field-Support Dataset

Script:

```text
scripts/build_field_support_dataset.py
```

Included fields:

```text
brand_name
fanciful_name
class_type
alcohol_content
net_contents
country_of_origin
```

Applicant/producer was excluded from this first clean field-support training
set because the public metadata was inconsistent for that target.

The dataset creates positive pairs from accepted public COLA application fields
and same-split, same-field negative pairs by shuffling values. This prevents
cross-split leakage.

| Split | Positive pairs | Negative pairs | Total pairs |
|---|---:|---:|---:|
| Train | 10,336 | 20,672 | 31,008 |
| Validation | 5,139 | 10,278 | 15,417 |
| Locked holdout | 15,664 | 31,328 | 46,992 |
| Total | 31,139 | 62,278 | 93,417 |

Important limitation: this is clean weak supervision from application fields.
It proves the text-pair bridge can learn field support. It does not prove OCR
extraction accuracy by itself.

## Chronological Experiment Ledger

### 2026-05-01: Requirements Correction

The core insight was that the app is not just a label checklist. It needs to
duplicate the agent's routine matching workflow:

```text
COLA application data
+ submitted label artwork
-> extract text from all label panels
-> compare label evidence against form fields
-> Pass / Needs Review / Fail with evidence
```

Requirements pulled from the interviews:

- 5-second usability target per label.
- Batch pressure from importers submitting 200-300 applications.
- Agents need a clean interface, not a complicated research tool.
- `GOVERNMENT WARNING:` must be exact, all caps, and bold.
- Weird angles, glare, curved text, vertical text, and multiple label panels are
  real-world problems.
- Prototype should be standalone and local-first; direct COLAs Online
  integration is out of scope.

Decision made: keep compliance deterministic and treat OCR/modeling as evidence
generation.

### 2026-05-01: Public COLA Registry Pilot

The first official-data strategy used the TTB Public COLA Registry directly.
The five-record pilot used these public TTB IDs:

```text
25337001000464
26035001000229
26035001000237
26035001000256
26035001000300
```

Outcome:

- public form HTML fetched,
- application fields parsed,
- label-image references discovered,
- 15 label images downloaded,
- parsing was hardened to preserve accents such as `CORAZÓN`, `ESPADÍN`, and
  `TOBALÁ`.

Why it did not remain the only data source: TTBOnline access became unreliable
while the sprint was underway. Rather than risk having no evaluation corpus, the
project shifted to COLA Cloud public data.

### 2026-05-02: COLA Cloud Public Corpus

COLA Cloud was used as a practical public-data source after direct TTBOnline
access became unreliable. The goal was not to outsource runtime behavior. The
goal was to get enough official public examples to test the app.

Data decision:

- Pull a defensible public evaluation corpus.
- Keep raw/bulk data under `data/work/`.
- Do not commit raw forms, images, OCR outputs, SQLite databases, or bulk data.
- Keep official public examples separate from synthetic negatives.

Final split:

```text
train: 2,000 applications
validation: 1,000 applications
locked holdout: 3,000 applications
```

This gave the project a real train/validation/holdout structure instead of
hand-picked anecdotes.

### 2026-05-02: OCR Engine Sweep

Purpose: find out whether docTR, PaddleOCR, OpenOCR/SVTRv2, or more specialized
scene-text recognizers were the best candidate for alcohol label text.

Primary artifact family:

```text
data/work/ocr-engine-sweep/
experiments/ocr_engine_sweep/
```

Important statistical caveat: this was a 30-image smoke test, not a final
accuracy study. Small samples have high variance. These results were used for
architectural pruning and next-step selection.

#### OCR Field-Support Smoke Metrics

| Model | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate |
|---|---:|---:|---:|---:|---:|---:|
| docTR | 0.7455 | 0.9825 | 0.5000 | 0.9911 | 0.6627 | 0.0089 |
| PaddleOCR | 0.7723 | 0.9552 | 0.5714 | 0.9732 | 0.7151 | 0.0268 |
| OpenOCR / SVTRv2 | 0.7143 | 0.9800 | 0.4375 | 0.9911 | 0.6049 | 0.0089 |
| PARSeq AR over OpenOCR crops | 0.6875 | 0.9773 | 0.3839 | 0.9911 | 0.5513 | 0.0089 |
| PARSeq NAR/refine-2 over OpenOCR crops | 0.6875 | 0.9773 | 0.3839 | 0.9911 | 0.5513 | 0.0089 |
| ASTER over OpenOCR crops | 0.6880 | 1.0000 | 0.3840 | 1.0000 | 0.5548 | 0.0000 |
| FCENet + ASTER | 0.6161 | 1.0000 | 0.2478 | 1.0000 | 0.3972 | 0.0000 |
| ABINet over OpenOCR crops | 0.6607 | 1.0000 | 0.3214 | 1.0000 | 0.4865 | 0.0000 |

#### OCR Latency Smoke Metrics

| Model | Runtime tested | Mean / image | Median / image | Worst / image | Mean / app | Max / app |
|---|---|---:|---:|---:|---:|---:|
| docTR | CPU, cached baseline | 800.53 ms | 804.50 ms | 1,592 ms | 1,200.8 ms | 2,216 ms |
| PaddleOCR | CPU container | 1,105.00 ms | 1,096.0 ms | 1,544 ms | 1,657.5 ms | 3,558 ms |
| OpenOCR / SVTRv2 | CPU container | 563.77 ms | 582.50 ms | 1,211 ms | 845.65 ms | 1,383 ms |
| PARSeq AR | CPU over OpenOCR crops | 293.47 ms | 212.00 ms | 870 ms | 440.2 ms | 870 ms |
| PARSeq NAR/refine-2 | CPU over OpenOCR crops | 215.17 ms | 168.50 ms | 655 ms | 322.75 ms | 655 ms |
| ASTER | CPU over OpenOCR crops | 119.87 ms | 111.00 ms | 275 ms | crop-stage only | crop-stage only |
| FCENet + ASTER | CPU detector + recognizer | 4,526.70 ms | 4,073.50 ms | 10,525 ms | detector-stage only | detector-stage only |
| ABINet | CPU over OpenOCR crops | 458.83 ms | 369.00 ms | 1,229 ms | crop-stage only | crop-stage only |

#### Per-Field F1 From the First OCR Sweep

| Field | docTR | PaddleOCR | OpenOCR | PARSeq AR | PARSeq NAR |
|---|---:|---:|---:|---:|---:|
| Brand name | 0.7500 | 0.7097 | 0.7097 | 0.5714 | 0.5714 |
| Fanciful name | 0.8235 | 0.9474 | 0.7500 | 0.6667 | 0.7097 |
| Class/type | 0.5714 | 0.5714 | 0.4000 | 0.3333 | 0.3333 |
| Alcohol content | 0.8333 | 0.8956 | 0.8800 | 0.8800 | 0.8800 |
| Net contents | 0.8235 | 0.7500 | 0.6667 | 0.6667 | 0.6667 |
| Country of origin | 0.7143 | 0.9412 | 0.7143 | 0.7143 | 0.6154 |
| Applicant / producer | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Decision:

- PaddleOCR had the highest first-pass F1, but also the highest false-clear
  rate of the top engines.
- OpenOCR/SVTRv2 was fast and worth preserving as a future option.
- PARSeq, ASTER, FCENet, and ABINet were useful checks, but crop dependence,
  recall loss, or CPU latency made them poor candidates for deadline runtime.
- docTR remained the stable deployed OCR path.

### 2026-05-02: Deterministic OCR Ensemble Policies

Purpose: test whether docTR + PaddleOCR + OpenOCR could be combined with simple
rules before jumping into BERT/LayoutLM complexity.

Engines:

```text
docTR
PaddleOCR
OpenOCR / SVTRv2
```

Policies tested:

- any engine supports,
- majority vote,
- unanimous vote,
- high-confidence or majority,
- safety-weighted support,
- government-safe support.

Key result from `doctr-paddle-openocr-ensemble-smoke-30-govsafe`:

| Policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate |
|---|---:|---:|---:|---:|---:|---:|
| Any engine | 0.7902 | 0.9452 | 0.6161 | 0.9643 | 0.7459 | 0.0357 |
| Majority vote | 0.7411 | 0.9821 | 0.4911 | 0.9911 | 0.6548 | 0.0089 |
| WineBERT/domain model OR government-safe OCR | about 0.7946 | 1.0000 | 0.5893 | 1.0000 | about 0.7416 | 0.0000 |

Latency assumption for tri-engine sequential execution:

```text
mean: 3,703.95 ms / application
max: 6,940 ms / application
```

Decision: promising, but not promoted. A tri-engine runtime would need careful
parallelization and larger calibration before it could be trusted in the live
app.

### 2026-05-02: Curved-Text Research Path

Concepts considered:

- custom HO-GNN / hypergraph neural network over text primitives,
- TPS/STN geometric unwarping,
- SVTR/CRNN recognition,
- CTW1500 and Total-Text pretraining,
- OpenOCR/SVTRv2,
- OpenVINO / ONNX / INT8 CPU optimization on Intel AMX.

Why it mattered:

- alcohol labels often have curved, vertical, or distorted text,
- government warning text may wrap around circles or bottle neck panels,
- standard rectangular OCR crops can lose sequence order.

Decision: do **not** build a custom pixel-to-text HO-GNN/TPS/SVTR model during
the take-home. It would need polygon/character-level labels and much more time.
The practical version of the idea became the graph-aware evidence scorer below:
use OCR boxes as graph nodes and learn post-OCR field support.

### 2026-05-02: Graph-Aware Evidence Scorer POC

Purpose: test the smallest buildable version of the graph idea without training
a full computer vision model from pixels.

Input:

```text
cached OCR boxes + expected application field value
```

Model:

```text
KNN graph over OCR fragments
-> lightweight PyTorch message passing
-> field-support score
```

Best GPU safety run:

```text
data/work/graph-ocr/gpu-safety-neg2-e40/summary.json
```

Data:

| Item | Count |
|---|---:|
| Applications | 100 |
| Examples | 2,072 |
| Positive examples | 518 |
| Negative examples | 1,554 |
| Train applications | 70 |
| Dev applications | 15 |
| Test applications | 15 |

Test metrics:

| Model | Accuracy | Precision | Positive-support recall | Specificity / negative rejection | F1 | False-clear rate |
|---|---:|---:|---:|---:|---:|---:|
| Baseline fuzzy matcher | 0.8947 | 0.8438 | 0.7105 | 0.9561 | 0.7714 | 0.0439 |
| Graph-aware scorer | 0.9408 | 0.9531 | 0.8026 | 0.9868 | 0.8714 | 0.0132 |

Positive field-support improvements on the test split:

| Field | Baseline | Graph scorer | Delta |
|---|---:|---:|---:|
| Brand name | 0.8000 | 0.8667 | +0.0667 |
| Fanciful name | 0.5333 | 0.8667 | +0.3333 |
| Class/type | 0.4667 | 0.4667 | 0.0000 |
| Alcohol content | 0.9231 | 0.9231 | 0.0000 |
| Net contents | 0.8333 | 0.9167 | +0.0833 |
| Country of origin | 0.8333 | 0.8333 | 0.0000 |

Decision: strong future candidate, not shipped. It needs saved artifact export,
runtime feature conversion, same-split comparison against DistilRoBERTa, CPU
latency proof, tests, and locked noisy-OCR holdout evaluation.

### 2026-05-02: Domain NER / BERT Entity Models

Purpose: test whether alcohol-domain or food-domain NER could help clean noisy
OCR before field comparison.

Models tested:

- `panigrah/wineberto-labels`,
- `panigrah/wineberto-ner`,
- `AnanthanarayananSeetharaman/osa-custom-ner-model`,
- `Dizex/FoodBaseBERT-NER`.

Representative 30-image smoke results:

| Model | License noted in run | Entity count | Mean latency / app | Entities-only F1 | Entities-only false-clear | Best combined F1 | Best combined false-clear |
|---|---|---:|---:|---:|---:|---:|---:|
| WineBERT/o labels | unknown | 709 | 261.25 ms | 0.4865 | 0.0000 | 0.7416 | 0.0000 |
| WineBERT/o NER | unknown | 396 | 189.30 ms | 0.1176 | 0.0000 | 0.7416 | 0.0000 |
| OSA custom NER | apache-2.0 | 1,579 | 102.55 ms | 0.5166 | 0.0000 | 0.7486 | 0.0000 |
| FoodBaseBERT NER | MIT | 369 | 286.65 ms | 0.0522 | 0.0000 | 0.7416 | 0.0000 |

Interpretation:

- Domain NER can be conservative, but recall was too low by itself.
- Food-domain models are too far from regulatory alcohol labels.
- WineBERT/o license uncertainty makes it inappropriate for the production
  dependency list.
- These models did not replace field-support scoring.

Decision: document as research, keep out of runtime.

### 2026-05-03: DistilRoBERTa and RoBERTa Field-Support Models

Purpose: learn whether a text-pair transformer can classify support between an
expected COLA field and candidate text.

Artifacts:

```text
data/work/field-support-models/distilroberta-field-support-v1-runtime/metrics.json
data/work/field-support-models/roberta-base-field-support-v1-e1/metrics.json
```

#### DistilRoBERTa

Settings:

```text
model_id: distilroberta-base
epochs: 1
threshold: 0.53
max_length: 128
threshold policy: false_clear_constrained_max_f1
```

Metrics:

| Split | Examples | Accuracy | F1 | False-clear rate |
|---|---:|---:|---:|---:|
| Train | 31,008 | 1.000000 | 1.000000 | 0.000000 |
| Validation | 15,417 | 1.000000 | 1.000000 | 0.000000 |
| Locked holdout | 46,992 | 0.999936 | 0.999904 | 0.000096 |

Latency:

```text
CPU mean: 17.56 ms / pair
CPU p95: 19.36 ms / pair
GPU mean in training/eval path: 0.35 ms / pair
```

#### RoBERTa Base

Settings:

```text
model_id: roberta-base
epochs: 1
threshold: 0.99
max_length: 128
threshold policy: false_clear_constrained_max_f1
```

Metrics:

| Split | Examples | Accuracy | F1 | False-clear rate |
|---|---:|---:|---:|---:|
| Train | 31,008 | 0.999903 | 0.999855 | 0.000145 |
| Validation | 15,417 | 1.000000 | 1.000000 | 0.000000 |
| Locked holdout | 46,992 | 0.999851 | 0.999777 | 0.000223 |

Latency:

```text
CPU mean: 33.35 ms / pair
CPU p95: 37.96 ms / pair
GPU mean in training/eval path: 0.70 ms / pair
```

Decision:

- DistilRoBERTa was the better runtime candidate: similar clean-pair accuracy,
  lower CPU latency, and smaller model footprint.
- It was wired as optional evidence when the artifact is mounted.
- It is not the OCR engine and does not perform final compliance decisions.
- These results remain clean text-pair results, not final noisy OCR accuracy.

### 2026-05-03: OCR Conveyor

Purpose: create cached OCR evidence from train/validation images using the three
candidate OCR engines, without crashing the full run on corrupt images.

Artifact:

```text
data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/summary.json
```

Run shape:

| Item | Count |
|---|---:|
| Engines | docTR, OpenOCR, PaddleOCR |
| Image rows | 5,353 |
| Valid images | 5,179 |
| Invalid/corrupt skipped | 174 |
| Chunk jobs | 975 |
| Completed jobs | 975 |
| OCR output rows | 15,537 |

Decision: keep as offline evidence cache. Do not force tri-engine OCR into the
live app before locked noisy-OCR evaluation.

### 2026-05-03: Typography Requirement Added

Jenny's interview note made this explicit: the government warning statement is
not just text matching. The heading must be:

```text
GOVERNMENT WARNING:
```

and it must be all caps and bold.

This created a separate typography preflight problem:

```text
OCR word boxes
-> isolate GOVERNMENT WARNING: heading crop
-> classify strong bold evidence
-> route uncertainty to Needs Review
```

### 2026-05-03: Early SVM Typography Runs

Initial SVM-style runs generated synthetic crops but exposed a labeling problem:
some examples labeled as borderline or degraded were visually bold or visually
not bold. That polluted the decision boundary.

Corrected labeling rule:

- generated bold / extra bold / ultra bold fonts are bold,
- generated non-bold fonts are not bold,
- medium / semibold / light-bold-style labels are not treated as compliant
  bold,
- unreadable or badly degraded evidence is a review case,
- no-warning panels are valid panel-level negatives, not application-level
  failures by themselves.

Decision: rebuild the dataset instead of trusting a muddy SVM result.

### 2026-05-03: Audit-v6 Typography Dataset

Purpose: create a defensible mixed image dataset for warning-heading typography.

Artifact:

```text
data/work/typography-preflight/audit-v6/summary.json
```

Total samples:

```text
9,000
```

Source mix:

| Source | Rows | Share |
|---|---:|---:|
| COLA-derived rows | 4,957 | 55.08% |
| Synthetic-only rows | 4,043 | 44.92% |

Split sizes:

| Split | Crops |
|---|---:|
| Train | 6,000 |
| Validation | 1,500 |
| Test | 1,500 |

Boldness labels:

| Label | Total | Train | Validation | Test |
|---|---:|---:|---:|---:|
| Bold | 3,584 | 2,385 | 607 | 592 |
| Not bold | 3,616 | 2,415 | 593 | 608 |
| Unreadable review | 900 | 600 | 150 | 150 |
| Not applicable | 900 | 600 | 150 | 150 |

Source-kind breakdown:

| Source kind | Rows |
|---|---:|
| Real COLA heading positive | 1,800 |
| Real COLA background non-bold | 1,800 |
| Real COLA no-warning panel | 900 |
| Synthetic bold positive | 1,350 |
| Synthetic non-bold | 1,350 |
| Synthetic incorrect heading | 900 |
| Review unreadable | 900 |

Decision: use this as the valid same-dataset comparison base for classical,
boosting, MLP, CNN, and ensemble typography experiments.

### 2026-05-03: Audit-v6 Classical and Boosting Typography Models

Purpose: compare old-school statistical learning and boosting models on the
same audit-v6 data.

Artifact:

```text
data/work/typography-preflight/model-comparison-audit-v6-baselines-v1/metrics/report.md
```

Positive class: `bold`. False clear means actual class is not `bold` but the
model predicts `bold`.

#### Base Model Metrics

| Model | Train Acc | Train F1 | Train FC | Val Acc | Val F1 | Val FC | Test Acc | Test F1 | Test FC | Train s | Single p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SVM | 0.9983 | 0.9990 | 0.0003 | 0.9627 | 0.9603 | 0.0269 | 0.9473 | 0.9467 | 0.0363 | 5.2 | 0.1103 |
| XGBoost | 0.9993 | 0.9996 | 0.0000 | 0.9680 | 0.9666 | 0.0381 | 0.9647 | 0.9633 | 0.0297 | 40.0 | 0.1763 |
| LightGBM | 1.0000 | 1.0000 | 0.0000 | 0.9827 | 0.9810 | 0.0202 | 0.9747 | 0.9753 | 0.0198 | 36.6 | 2.1329 |
| Logistic Regression | 1.0000 | 1.0000 | 0.0000 | 0.9687 | 0.9660 | 0.0280 | 0.9600 | 0.9546 | 0.0242 | 23.9 | 0.1471 |
| MLP | 0.9977 | 0.9979 | 0.0019 | 0.9713 | 0.9694 | 0.0302 | 0.9653 | 0.9656 | 0.0275 | 5.4 | 0.2645 |
| CatBoost | 0.9700 | 0.9714 | 0.0288 | 0.9580 | 0.9558 | 0.0403 | 0.9507 | 0.9472 | 0.0452 | 28.6 | 2.1046 |

#### Classical Ensemble Metrics

| Model | Train Acc | Train F1 | Train FC | Val Acc | Val F1 | Val FC | Test Acc | Test F1 | Test FC | Single p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Strict-veto ensemble | 0.9710 | 0.9556 | 0.0000 | 0.9227 | 0.8909 | 0.0045 | 0.9153 | 0.8841 | 0.0077 | 10.5609 |
| Calibrated logistic stacker | 1.0000 | 1.0000 | 0.0000 | 0.9893 | 0.9909 | 0.0101 | 0.9707 | 0.9715 | 0.0176 | 6.2460 |
| LightGBM reject-threshold stacker | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 | 0.9707 | 0.9721 | 0.0143 | 11.2825 |
| XGBoost reject-threshold stacker | 1.0000 | 1.0000 | 0.0000 | 0.9980 | 0.9975 | 0.0011 | 0.9693 | 0.9700 | 0.0176 | 11.4115 |
| CatBoost stacker | 1.0000 | 1.0000 | 0.0000 | 0.9873 | 0.9877 | 0.0123 | 0.9727 | 0.9721 | 0.0143 | 11.3355 |

These classical models were not filler. They were chosen because low-dimensional
engineered visual features are exactly the kind of setting where SVMs, logistic
regression, and boosting models can be strong, cheap, and explainable baselines.

Decision: useful comparison, but not enough to ship an ensemble without runtime
integration and final promotion tests.

### 2026-05-03: CNN Typography Challenger

Purpose: test whether a small transfer-learning CNN handles visual boldness
better than engineered features.

Artifact:

```text
data/work/typography-preflight/cnn-audit-v6-mobilenet-v1/metrics/report.md
```

Model:

```text
MobileNetV3 Small
ImageNet weights
best epoch: 7
```

Test metrics:

| Metric | Value |
|---|---:|
| Accuracy | 0.9560 |
| Macro F1 | 0.9686 |
| Weighted F1 | 0.9558 |
| False-clear rate | 0.005507 |

Per-class test metrics:

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Bold | 0.9907 | 0.8986 | 0.9424 | 592 |
| Not bold | 0.9125 | 0.9951 | 0.9520 | 608 |
| Unreadable review | 0.9868 | 1.0000 | 0.9934 | 150 |
| Not applicable | 0.9932 | 0.9800 | 0.9866 | 150 |

Latency:

| Device | Batch ms/crop | Single mean ms | Single p95 ms |
|---|---:|---:|---:|
| GPU | 0.0394 | 9.6059 | 1.2239 |
| CPU | 2.9781 | 5.0894 | 5.2063 |

Decision: promising future runtime candidate, but not promoted before deadline.
The deployed logistic model was already small, inspectable, and wired.

### 2026-05-03: CNN-Inclusive Typography Ensembles

Purpose: test whether combining SVM, XGBoost, LightGBM, Logistic Regression,
MLP, CatBoost, and MobileNetV3 CNN gives better boldness classification.

Artifact:

```text
data/work/typography-preflight/model-comparison-audit-v6-cnn-ensemble-v1/metrics/report.md
```

Protocol:

```text
base models: 5-fold out-of-fold train predictions
stackers: trained on out-of-fold train predictions
reject thresholds: tuned on validation
final metrics: test-only
```

Base learners:

| Model | Train OOF F1 | Train OOF FC | Test Acc | Test F1 | Test FC |
|---|---:|---:|---:|---:|---:|
| SVM | 0.9453 | 0.0346 | 0.9473 | 0.9467 | 0.0363 |
| XGBoost | 0.9705 | 0.0302 | 0.9647 | 0.9633 | 0.0297 |
| LightGBM | 0.9737 | 0.0252 | 0.9747 | 0.9753 | 0.0198 |
| Logistic Regression | 0.9614 | 0.0274 | 0.9600 | 0.9546 | 0.0242 |
| MLP | 0.9656 | 0.0288 | 0.9653 | 0.9656 | 0.0275 |
| CatBoost | 0.9505 | 0.0476 | 0.9507 | 0.9472 | 0.0452 |
| MobileNetV3 CNN | 0.9523 | 0.0022 | 0.9560 | 0.9686 | 0.0055 |

CNN-inclusive ensembles:

| Model | Train F1 | Train FC | Test Acc | Test F1 | Test FC | Aggregator p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| Soft voting, all bases + CNN | 0.9784 | 0.0160 | 0.9740 | 0.9742 | 0.0198 | 0.00 |
| Strict veto, all bases + CNN | 0.8400 | 0.0006 | 0.8833 | 0.8530 | 0.0022 | 0.01 |
| Logistic stacker, all bases + CNN | 0.9932 | 0.0064 | 0.9893 | 0.9908 | 0.0099 | 0.08 |
| LightGBM stacker, all bases + CNN | 1.0000 | 0.0000 | 0.9880 | 0.9900 | 0.0143 | 0.35 |
| XGBoost stacker, all bases + CNN | 0.9985 | 0.0025 | 0.9860 | 0.9874 | 0.0165 | 0.15 |
| CatBoost stacker, all bases + CNN | 0.9933 | 0.0072 | 0.9873 | 0.9895 | 0.0154 | 0.12 |
| LightGBM reject, all bases + CNN | 0.9683 | 0.0000 | 0.9673 | 0.9552 | 0.0033 | 0.25 |
| XGBoost reject, all bases + CNN | 0.9784 | 0.0000 | 0.9753 | 0.9656 | 0.0044 | 0.14 |

Decision: very useful model-selection work, but not shipped. It requires
artifact export, runtime interface work, and a conservative comparison against
the existing deployed preflight.

### 2026-05-03: Real-COLA CNN-Inclusive Typography Smoke

Purpose: check whether audit-v6 base learners and CNN-inclusive ensembles can
score real approved COLA warning-heading crops.

Artifact:

```text
data/work/typography-preflight/real-cola-cnn-ensemble-smoke-v1/metrics/report.md
```

Counts:

| Item | Count |
|---|---:|
| Applications represented | 2,356 |
| Source images represented | 2,358 |
| Heading crops | 4,362 |
| docTR crops | 126 |
| OpenOCR crops | 2,124 |
| PaddleOCR crops | 2,112 |

Real approved COLAs are positive-domain examples. This smoke checks real-crop
clear behavior and latency. It cannot estimate false-clear safety because it
does not include real rejected/non-bold public applications.

| Type | Model / Policy | Crop clear rate | App clear rate | Crop review rate | App review rate | Mean ms/crop |
|---|---|---:|---:|---:|---:|---:|
| base | SVM | 0.3744 | 0.5310 | 0.0410 | 0.0492 | 0.0067 |
| base | XGBoost | 0.6465 | 0.7852 | 0.0165 | 0.0136 | 0.0106 |
| base | LightGBM | 0.5942 | 0.7593 | 0.0202 | 0.0161 | 0.0122 |
| base | Logistic Regression | 0.5282 | 0.6596 | 0.1894 | 0.1447 | 0.0095 |
| base | MLP | 0.7265 | 0.8196 | 0.0724 | 0.0514 | 0.0072 |
| base | CatBoost | 0.5452 | 0.6732 | 0.0358 | 0.0301 | 0.0165 |
| base | MobileNetV3 CNN | 0.6346 | 0.7330 | 0.0477 | 0.0488 | 4.0340 |
| ensemble | Soft voting + CNN | 0.6678 | 0.7784 | 0.0355 | 0.0357 | 0.0001 |
| ensemble | Strict veto + CNN | 0.1648 | 0.2610 | 0.7765 | 0.6715 | 0.0001 |
| ensemble | Logistic stacker + CNN | 0.6978 | 0.7691 | 0.0275 | 0.0280 | 0.0001 |
| ensemble | LightGBM stacker + CNN | 0.8044 | 0.8425 | 0.0195 | 0.0166 | 0.0032 |
| ensemble | XGBoost stacker + CNN | 0.8228 | 0.8527 | 0.0163 | 0.0123 | 0.0006 |
| ensemble | CatBoost stacker + CNN | 0.8469 | 0.8638 | 0.0138 | 0.0110 | 0.0004 |
| ensemble | LightGBM reject + CNN | 0.4519 | 0.5976 | 0.3721 | 0.2615 | 0.0030 |
| ensemble | XGBoost reject + CNN | 0.5066 | 0.6384 | 0.3324 | 0.2267 | 0.0006 |

Decision: the ensemble path deserves a future promotion branch, but it was too
risky to wire into the Monday deployment without final negative-domain proof.

### 2026-05-03: Deployed Warning-Heading Boldness Model

Purpose: ship a conservative, low-latency, inspectable warning-heading preflight
instead of rushing a larger ensemble.

Runtime artifact:

```text
app/models/typography/boldness_logistic_v1.json
```

Training artifact:

```text
data/work/typography-preflight/real-adapted-boldness-logistic-v1/summary.json
```

The model uses engineered image features over an isolated warning-heading crop.
It is exported as JSON so the runtime does not need scikit-learn.

Threshold selected for a low false-clear posture:

```text
0.9545819397993311
```

Reported as:

```text
0.9546
```

Operating point:

| Metric | Value |
|---|---:|
| Validation accuracy | 0.915788 |
| Validation F1 | 0.881302 |
| Validation false-clear rate | 0.000624 |
| Synthetic holdout accuracy | 0.920700 |
| Synthetic holdout F1 | 0.865570 |
| Synthetic holdout false-clear rate | 0.001800 |
| Held-out approved-COLA clear rate | 92.19% |
| Real COLA sanity latency | about 37 ms crop + classify |

Interpretation:

- The model can clear strong bold evidence.
- It does not auto-reject weak evidence.
- Missing crops, low confidence, blurry evidence, or unfamiliar cases route to
  `Needs Review`.

Decision: ship this model because it is narrow, fast, explainable, and already
wired into the deterministic rule layer.

### 2026-05-04: Runtime Hardening and Demo UX

The final app work focused on making the modeling work visible and usable:

- landing page with `Home`, `LOT Demo`, and `LOT Actual`,
- server-hosted curated public COLA demo,
- actual upload path with user-provided application folders,
- data-format instructions,
- downloadable example data with `manifest.csv`,
- multi-panel application browsing,
- current application truth fields beside scraped fields,
- durable filesystem-backed queue for batch jobs,
- cancelable running jobs,
- CSV export,
- reviewer dashboard and reviewer action buttons.

The curated public COLA demo pack is explicitly not an accuracy metric. It is a
walkthrough artifact so an evaluator can see the intended workflow without
waiting for live OCR on difficult public images.

## Runtime Model Status

| Component | Runtime status | Notes |
|---|---|---|
| Fixture OCR | Active | Used for deterministic demos/tests. |
| docTR OCR | Active | Local OCR path for real uploads. |
| DistilRoBERTa field support | Optional active | Runs only when model artifact is mounted; evidence only. |
| Logistic warning-heading boldness model | Active | JSON artifact committed under `app/models/typography/`. |
| Deterministic rules | Active | Final triage logic. |
| Reviewer policy queue | Active | Supports human-review routing. |
| PaddleOCR | Offline only | Tested, not deployed. |
| OpenOCR / SVTRv2 | Offline only | Tested, not deployed. |
| PARSeq | Offline only | Tested over crops, not deployed. |
| ASTER | Offline only | Tested over crops, not deployed. |
| FCENet + ASTER | Offline only | Tested, too slow for this runtime. |
| ABINet | Offline only | Tested over crops, not deployed. |
| WineBERT/o / OSA / FoodBaseBERT | Offline only | Tested as entity probes, not deployed. |
| Graph-aware scorer | Offline only | Strong POC, not production wired. |
| CNN typography model | Offline only | Strong POC, not production wired. |
| CNN-inclusive typography ensembles | Offline only | Strong POC, not production wired. |
| LayoutLMv3 arbiter | Future design | Deferred; needs token-level labels and clustering. |
| HO-GNN/TPS/SVTR pixel OCR | Future research | Deferred; needs polygon/character-level annotations. |

## Why the Final Runtime Is Conservative

The prompt values a working core application with clean code over ambitious but
incomplete features. The experiments above show that we explored the ambitious
paths, but the shipped runtime favors:

- local execution,
- measurable latency,
- deterministic compliance decisions,
- conservative false-clear posture,
- human review when evidence is weak,
- clear documentation of what was tested and what remains future work.

That is the right posture for a federal label-compliance prototype.

## Known Limitations

- The strongest DistilRoBERTa and RoBERTa results are clean text-pair results,
  not final noisy-OCR extraction accuracy.
- The 30-image OCR sweep is directional and high-variance.
- Public approved COLAs are biased toward compliant examples, so real
  non-compliant typography examples are scarce.
- Synthetic negatives are useful for safety testing, but they are not a perfect
  substitute for real rejected applications.
- The curated public demo pack is a walkthrough artifact, not a model metric.
- The graph scorer and CNN-inclusive typography ensembles need runtime
  promotion work before deployment.
- A full noisy-OCR locked holdout benchmark remains the next statistical gate.

## Next Statistical Gate

The next serious measurement should be:

1. Attach cached docTR/PaddleOCR/OpenOCR OCR evidence to the train and
   validation field-support manifests.
2. Tune thresholds on validation for low false-clear risk.
3. Freeze the OCR/arbiter/rule settings.
4. Run the locked 3,000-application holdout once.
5. Report field-level and application-level:
   - F1,
   - recall,
   - specificity,
   - false-clear rate,
   - reviewer-escalation rate,
   - per-label and per-application latency.

That is the point where the project can claim noisy OCR evaluation accuracy.
Everything before that is engineering evidence, calibration, or model selection.
