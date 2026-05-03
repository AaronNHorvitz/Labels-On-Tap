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
- `1,500` selected applications from `7,788` candidates.
- First `100` details fetched.
- `169` label images OCR'd through local docTR.
- Current OCR/model metrics are COLA Cloud-derived public calibration metrics,
  not direct TTB attachment-download metrics.

Key local paths:

```text
data/work/cola/official-sample-1500-balanced/
data/work/cola/official-sample-3000-balanced/
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
- Current OCR/model numbers are calibration signals.
- For pure OCR/rule calibration, the older 3,000-record design can use 1,500 calibration and 1,500 locked holdout records.
- For trained DistilRoBERTa/RoBERTa field-support classifiers, the current preferred design is an application-level `60%` train / `20%` validation / `20%` locked test split.
- A locked holdout of `1,500` gives about `+/- 2.5 percentage points` conservative 95% margin of error for binary proportions; a locked test of `600` gives about `+/- 4.0 percentage points`.
- If larger samples reveal weaker field performance, route uncertain cases to `Needs Review` and document limitations.

Do not say the app is production-ready. Say it demonstrates a measured, auditable path to production readiness.

## Best Next Steps

1. Keep the deployed app stable.
2. Use `MODEL_LOG.md` as the experiment ledger for all OCR/model runs.
3. Scale graph scoring only after more cached OCR exists.
4. Add batching/padding to speed graph training before large experiments.
5. Improve class/type with product taxonomy features.
6. Add PaddleOCR as an alternate local OCR engine and compare against docTR.
7. Create the application-level split before generating any trained-model field pairs.
8. Use `MODEL_ARCHITECTURE.md` as the current map for DistilRoBERTa/RoBERTa field-support experiments.
