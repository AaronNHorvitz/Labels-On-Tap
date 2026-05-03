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
65 passed
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

Current local counts:

```text
selected/list-level IDs across all sample-plan folders: 3987 unique
current primary selected plan: 3000 records in official-sample-3000-balanced
fully fetched detail/application records: 202 unique
downloaded label image files: 338
```

Important current sample folders:

```text
data/work/cola/colacloud-api-detail-probe/
data/work/cola/official-sample-1500/
data/work/cola/official-sample-1500-balanced/
data/work/cola/official-sample-3000-balanced/
```

Current measured calibration source:

```text
data/work/cola/official-sample-1500-balanced/
100 fetched detail records
169 label images
```

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

Current preferred split if training a field-support classifier:

```text
60% train
20% validation
20% locked test
```

Current alternative for pure OCR/rule calibration:

```text
1500 calibration/tuning
1500 locked holdout
```

Important leakage rule:

Split by application/TTB ID **before** generating field-pair examples. The same TTB ID must never appear in train, validation, and test.

Margin-of-error notes:

```text
n = 1500 locked holdout -> about +/- 2.5 percentage points conservative 95% MOE
n = 600 locked test -> about +/- 4.0 percentage points conservative 95% MOE
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

Recommended next pull:

```text
Do not jump straight to 7500 details.
Pull in staged batches with usage checks.
```

Suggested stages:

```text
Stage A: 100 additional details/images
Stage B: 500 additional details/images
Stage C: expand to 3000 total fetched details/images
Stage D: consider 6000 total only if quota, time, and storage are healthy
```

Why not 7500 immediately:

- detail views are valuable and limited,
- OCR time grows quickly,
- a 6000-record corpus already supports a strong 3000/3000 calibration/holdout story for deterministic OCR/rule evaluation,
- if training a classifier, a 6000-record 60/20/20 split gives 3600 train, 1200 validation, and 1200 locked test, which is already credible for a take-home.

Recommended current target:

```text
6000 total selected public applications if quota allows,
but first fetch enough to reach 3000 full detail/image records.
```

The existing `official-sample-3000-balanced` folder has a 3000-record selected plan but no fetched details/images yet. Use that as the next controlled expansion point.

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
2. Check COLA Cloud usage before any new pull.
3. Confirm how the usage endpoint moves after a 5-10 record detail+image pull.
4. Expand `official-sample-3000-balanced` in controlled batches.
5. Keep all new data under `data/work/cola/`.
6. Run docTR/PaddleOCR/OpenOCR on the larger calibration set only after enough images are fetched.
7. Do not touch the locked holdout after split creation except for final evaluation.
8. Convert final metrics into `docs/performance.md`, `MODEL_LOG.md`, `TRADEOFFS.md`, and README.
9. Build 300-500 synthetic negative cases from `PHASE1_REJECTION.md`.
10. Keep legal reasoning/guidance last; deterministic evidence first.

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

