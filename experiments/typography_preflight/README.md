# Typography Preflight Experiment

This experiment tests a lightweight OpenCV/SVM preflight for Jenny Park's
government-warning typography requirement:

```text
GOVERNMENT WARNING:
```

must be all caps and bold.

The deployed app already checks the all-caps heading deterministically and
routes boldness to `Needs Review`. This experiment asks whether a classical
statistical-learning model can provide useful font-weight evidence without
introducing a heavy deep-learning dependency.

## Architecture

```text
warning heading crop
  -> OpenCV normalization
  -> stroke/shape features
  -> classical tabular classifier
  -> conservative threshold tuned on validation false-clear rate
```

The primary safety metric is:

```text
false clear = regular, medium, degraded, or uncertain warning heading
classified as acceptable bold
```

## Data

The dataset is synthetic because public rejected/non-bold warning headings are
not available as a clean corpus. The generator renders the known phrase across
local system fonts and distortions.

Default split:

```text
train:      20,000 crops
validation: 5,000 crops
test:       5,000 crops
```

Font families and distortion recipes are held out across splits. This makes the
test stricter than a naive random image split because the model must generalize
to unseen font families and image artifacts.

The first full SVM run under `data/work/typography-preflight/svm-v2/` is now
treated as a flawed-target baseline. It mixed source font weight, image quality,
and auto-clearance policy into one binary label. That caused avoidable label
noise, such as bold fonts marked negative because the crop was degraded.

The corrected audit workflow uses a separate inspection builder:

```bash
data/work/typography-preflight/.venv/bin/python \
  -m experiments.typography_preflight.build_audit_dataset \
  --output-dir data/work/typography-preflight/audit-v5 \
  --samples-per-combo 36 \
  --clean
```

It writes:

```text
data/work/typography-preflight/audit-v5/
  index.html
  manifest.csv
  summary.json
  by_quality/
  by_visual_font_decision/
  by_header_decision/
```

The current inspection dataset is:

```text
data/work/typography-preflight/audit-v5/
```

The corrected labels are:

```text
font_weight_label             bold / not_bold
header_text_label             correct / incorrect
quality_label                 crop quality provenance
visual_font_decision_label    clearly_bold / clearly_not_bold / needs_review_unclear
header_decision_label         correct / incorrect / needs_review_unclear
```

The `audit-v5` rule is intentionally strict:

```text
Bold / ExtraBold / UltraBold / Black / Heavy font source -> bold
Regular / Book / Light / Thin / Medium / SemiBold / DemiBold source -> not_bold
Unreadable, faded, broken, blurry, or heavily degraded crop -> needs_review_unclear
```

The `audit-v5` contact sheet has now been visually inspected and used for the
first side-by-side model comparison.

## Run

Install experiment dependencies into a gitignored venv:

```bash
python -m venv data/work/typography-preflight/.venv
data/work/typography-preflight/.venv/bin/python -m pip install --upgrade pip
data/work/typography-preflight/.venv/bin/python -m pip install numpy pillow opencv-python-headless scikit-learn joblib xgboost catboost
```

Run CPU-only:

```bash
CUDA_VISIBLE_DEVICES="" \
OMP_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
NUMEXPR_NUM_THREADS=2 \
nice -n 15 ionice -c3 \
data/work/typography-preflight/.venv/bin/python \
  -m experiments.typography_preflight.train_svm
```

The first flawed-target full run used:

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

Artifacts are written under:

```text
data/work/typography-preflight/
```

That path is gitignored. Commit experiment code and documentation only, not
generated crops, features, metrics, or `.joblib` model artifacts.

## SVM vs. XGBoost vs. CatBoost Comparison

The corrected multiclass comparison is implemented in:

```text
experiments/typography_preflight/compare_models.py
```

Run:

```bash
OMP_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
NUMEXPR_NUM_THREADS=2 \
nice -n 15 ionice -c3 \
data/work/typography-preflight/.venv/bin/python \
  -m experiments.typography_preflight.compare_models \
  --output-dir data/work/typography-preflight/model-comparison-v1 \
  --train-samples 6000 \
  --validation-samples 1500 \
  --test-samples 1500 \
  --latency-rows 1000 \
  --sample-crop-limit 180 \
  --tree-iterations 120 \
  --svm-max-iter 2000
```

Do not set `CUDA_VISIBLE_DEVICES=""` for this comparison. XGBoost 3.x can raise
a CUDA driver discovery error when CUDA is explicitly hidden even when the
classifier is pinned to `device="cpu"`. The script itself keeps XGBoost and
CatBoost on CPU and limits thread counts.

The May 3 comparison output is:

```text
data/work/typography-preflight/model-comparison-v1/
```

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

- XGBoost produced the best raw accuracy and F1.
- SVM produced the lowest false-clear rate and the fastest single-row latency.
- CatBoost is viable but slower here and does not improve the safety metric.
- None of the hard-argmax models is promoted to runtime authority yet. The next
  step is validation-threshold tuning so low-confidence bold/header predictions
  route to `needs_review_unclear` instead of false clearing.

## Citation

Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome. *The Elements of
Statistical Learning: Data Mining, Inference, and Prediction*. 2nd ed.,
Springer, 2009.
