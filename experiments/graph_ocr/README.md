# Graph-Aware OCR Evidence Scorer

This experiment tests the smallest buildable version of the HO-GNN idea: a
PyTorch graph scorer over cached OCR boxes.

It does **not** train an OCR model from pixels. It uses local OCR output as the
input graph and learns whether those OCR fragments support a submitted COLA
application field.

```text
OCR boxes + expected field value
  -> KNN graph over OCR fragments
  -> lightweight PyTorch message passing
  -> field-support score
  -> deterministic Pass / Needs Review / Fail layer
```

Run from the dedicated CUDA environment:

```bash
python -m venv .venv-gpu
.venv-gpu/bin/python -m pip install --upgrade pip
.venv-gpu/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu130 torch torchvision
.venv-gpu/bin/python -m pip install rapidfuzz pydantic python-dotenv pillow
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py --device cuda
```

Outputs are written under gitignored `data/work/graph-ocr/<run-name>/`.

The proof-of-concept compares:

- baseline fuzzy text matching,
- baseline plus graph-aware evidence scoring.

The first goal is directional improvement on weak fields such as class/type,
brand/fanciful name, and country of origin without increasing false clears on
shuffled negative examples.

## May 2 GPU POC

The first safety-weighted GPU run used the existing 100-application calibration
set and 169 cached local OCR label images.

Command:

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 40 \
  --run-name gpu-safety-neg2-e40 \
  --device cuda \
  --negative-loss-weight 2.0 \
  --false-clear-tolerance 0.0
```

The threshold was tuned on the dev split with a false-clear cap equal to the
baseline dev false-clear rate. The test split showed:

| Metric | Baseline | Graph Scorer |
|---|---:|---:|
| Accuracy | 0.8947 | 0.9408 |
| Precision | 0.8438 | 0.9531 |
| Positive-support recall | 0.7105 | 0.8026 |
| Specificity / negative rejection | 0.9561 | 0.9868 |
| F1 | 0.7714 | 0.8714 |
| False-clear rate | 0.0439 | 0.0132 |

Positive field-support improvements on the test split:

| Field | Baseline | Graph Scorer | Delta |
|---|---:|---:|---:|
| Brand name | 0.8000 | 0.8667 | +0.0667 |
| Fanciful name | 0.5333 | 0.8667 | +0.3333 |
| Class/type | 0.4667 | 0.4667 | 0.0000 |
| Alcohol content | 0.9231 | 0.9231 | 0.0000 |
| Net contents | 0.8333 | 0.9167 | +0.0833 |
| Country of origin | 0.8333 | 0.8333 | 0.0000 |

This is not a production accuracy claim. It is a proof that graph-aware OCR
evidence scoring has measurable signal while preserving the conservative
false-clear posture. The next validation step is to scale this to the 1,500
calibration split, freeze settings, then evaluate the locked 1,500 holdout.
