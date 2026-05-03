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

The first full run used:

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
