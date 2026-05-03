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
  -> Pass / Needs Review / Fail with evidence
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
| `TRADEOFFS.md` | Architecture and data trade-offs |
| `DEMO_SCRIPT.md` | Reviewer demo flow |
| `PHASE1_REJECTION.md` | Known-bad/rejection checklist |
| `experiments/graph_ocr/` | Experimental graph-aware OCR evidence scorer |

## Current App State

- FastAPI + Jinja2/HTMX + local CSS.
- Docker Compose + Caddy deployment.
- AWS Lightsail deployment is live.
- Fixture demos work.
- Upload preflight exists.
- Batch upload exists.
- CSV export exists.
- `country_of_origin` and `imported` are first-class fields.
- Tests last passed with `65 passed`.

Useful verification:

```bash
pytest -q
python scripts/bootstrap_project.py --if-missing
curl https://www.labelsontap.ai/health
```

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
- Current OCR/model metrics remain COLA Cloud-derived public calibration
  metrics, not direct TTB attachment-download metrics.

Key local paths:

```text
data/work/cola/official-sample-3000-balanced/
data/work/cola/official-sample-next-3000-balanced/
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
- Current OCR/model numbers are calibration signals until rerun on the full
  6,000-record corpus.
- Use `official-sample-3000-balanced` as the development cohort.
- Use `official-sample-next-3000-balanced` as the locked holdout cohort.
- For model selection, split the first cohort into `2,000` train and `1,000`
  validation/calibration applications.
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
3. Create the application-level development/validation/holdout manifests
   before generating trained-model field pairs.
4. Run docTR/PaddleOCR/OpenOCR cached OCR over the development cohort.
5. Train/tune DistilRoBERTa/RoBERTa/OSA-style field-support arbiters on the
   development split.
6. Compare them against deterministic ensemble and graph-aware evidence scorer.
7. Freeze thresholds, then evaluate once on the 3,000-record holdout cohort.
8. Convert final metrics into `MODEL_LOG.md`, `TRADEOFFS.md`,
   `docs/performance.md`, and the README.
