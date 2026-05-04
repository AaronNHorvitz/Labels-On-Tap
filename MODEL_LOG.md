# Model Log

This is the concise model ledger for the submission. Raw experiment outputs are
gitignored under `data/work/`.

## Evaluation Corpus

Source: COLA Cloud public COLA data, used because direct public TTBOnline image
access became unreliable during the sprint.

| Split | Applications | Images |
|---|---:|---:|
| Train | 2,000 | 3,564 |
| Validation | 1,000 | 1,789 |
| Locked holdout | 3,000 | 5,082 |
| Total | 6,000 | 10,435 |

Split seed: `20260503`.

No TTB ID overlaps exist across train, validation, and holdout.

## Field-Support Dataset

Script:

```text
scripts/build_field_support_dataset.py
```

Fields:

```text
brand_name
fanciful_name
class_type
alcohol_content
net_contents
country_of_origin
```

Pair counts:

| Split | Positive pairs | Negative pairs | Total pairs |
|---|---:|---:|---:|
| Train | 10,336 | 20,672 | 31,008 |
| Validation | 5,139 | 10,278 | 15,417 |
| Holdout | 15,664 | 31,328 | 46,992 |

Negatives are generated within the same split and field to avoid cross-split
leakage.

## DistilRoBERTa Field-Support Run

Artifact:

```text
data/work/field-support-models/distilroberta-field-support-v1-runtime/model/
```

Settings:

```text
model_id: distilroberta-base
epochs: 1
threshold: 0.53
max_length: 128
```

Results:

| Split | Examples | F1 | False-clear rate |
|---|---:|---:|---:|
| Train | 31,008 | 1.000000 | 0.000000 |
| Validation | 15,417 | 1.000000 | 0.000000 |
| Locked holdout | 46,992 | 0.999904 | 0.000096 |

Latency:

```text
CPU mean: 17.56 ms / pair
CPU p95: 19.36 ms / pair
GPU mean during training/eval path: 0.35 ms / pair
```

Interpretation: useful runtime evidence bridge, but not a final OCR accuracy
claim because this run used clean weak-supervision pairs.

## OCR Conveyor

Train/validation tri-engine run:

```text
engines: docTR, OpenOCR, PaddleOCR
image rows: 5,353
valid images: 5,179
invalid/corrupt skipped: 174
chunks/jobs: 975
status: completed
```

This run created OCR evidence caches for later evaluation work. It is not
directly bundled into the deployed app.

## OCR Engine Sweep

Directional 30-image smoke results:

| Engine / policy | F1 | False-clear rate | Mean latency |
|---|---:|---:|---:|
| docTR cached baseline | 0.6627 | 0.0089 | 800.53 ms/image |
| PaddleOCR | 0.7151 | 0.0268 | 1,105.00 ms/image |
| OpenOCR / SVTRv2 | 0.6049 | 0.0089 | 563.77 ms/image |
| PARSeq AR over OpenOCR crops | 0.5513 | 0.0089 | 293.47 ms/image |
| ASTER over OpenOCR crops | 0.5548 | 0.0000 | 119.87 ms/image |
| FCENet + ASTER | 0.3972 | 0.0000 | 4,526.70 ms/image |
| ABINet over OpenOCR crops | 0.4865 | 0.0000 | 458.83 ms/image |

Interpretation: PaddleOCR stayed interesting because of F1, but false-clear
risk and runtime dependency cost kept docTR as the stable submission OCR path.

## Typography Boldness Runtime Model

Artifact:

```text
app/models/typography/boldness_logistic_v1.json
```

Operating point:

| Metric | Value |
|---|---:|
| Threshold | 0.9546 |
| Validation false-clear rate | 0.000624 |
| Synthetic holdout false-clear rate | 0.001800 |
| Held-out approved-COLA clear rate | 92.19% |
| Real COLA sanity latency | about 37 ms crop + classify |

Interpretation: deployed as conservative reviewer-assist evidence. It can clear
strong bold evidence, but uncertain cases route to review.

## Typography CNN/Ensemble Experiments

CNN-inclusive audit-v6 comparison:

| Model / Policy | Test macro F1 | Test false-clear |
|---|---:|---:|
| MobileNetV3 CNN base | 0.9686 | 0.0055 |
| Logistic stacker + CNN | 0.9908 | 0.0099 |
| LightGBM reject + CNN | 0.9552 | 0.0033 |
| XGBoost reject + CNN | 0.9656 | 0.0044 |

Interpretation: promising future path, not deployed.

## Graph-Aware Scorer POC

| Model | F1 | False-clear rate |
|---|---:|---:|
| Baseline fuzzy matcher | 0.7714 | 0.0439 |
| Graph-aware scorer POC | 0.8489 | 0.0175 |

Interpretation: promising post-submission candidate for fragmented/curved OCR
evidence, not deployed.
