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
  -> StandardScaler + LinearSVC
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

Do not train SVM/XGBoost/CatBoost models until the `audit-v5` contact sheet has
been visually inspected.

## Run

Install experiment dependencies into a gitignored venv:

```bash
python -m venv data/work/typography-preflight/.venv
data/work/typography-preflight/.venv/bin/python -m pip install --upgrade pip
data/work/typography-preflight/.venv/bin/python -m pip install numpy pillow opencv-python-headless scikit-learn joblib
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

## Citation

Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome. *The Elements of
Statistical Learning: Data Mining, Inference, and Prediction*. 2nd ed.,
Springer, 2009.
