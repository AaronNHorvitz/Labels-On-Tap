# Labels On Tap

Labels On Tap turns alcohol label review into a fast, evidence-backed triage
queue: upload the application, read the label artwork, and show the reviewer
exactly what matched, what failed, and what needs human judgment.

Labels On Tap is a local-first FastAPI prototype that triages COLAs Online-style
alcohol label applications and identifies labels that appear out of compliance.
It compares application fields against OCR evidence from submitted label artwork,
then routes each item to `Pass`, `Needs Review`, or `Fail` with source-backed
reasons and reviewer actions.

Public demo URL:

```text
https://www.labelsontap.ai
```

The app is built for the take-home prompt: a working source repository, a
deployed URL, clear setup instructions, documented assumptions, and defensible
engineering trade-offs.

## What It Does

- Verifies common TTB label fields:
  - brand name,
  - fanciful name when supplied,
  - class/type,
  - alcohol content,
  - net contents,
  - bottler/producer name and address when supplied,
  - country of origin for imports,
  - government health warning text, capitalization, and warning-heading boldness.
- Supports single-label uploads.
- Supports one application with multiple label panels.
- Supports manifest-backed batch uploads using loose images or a ZIP archive.
- Uses a local filesystem-backed queue so batch jobs do not run inside the
  browser request.
- Provides a reviewer dashboard at `/review`.
- Persists reviewer decisions: `Accept`, `Reject`, `Request correction / better
  image`, `Override with note`, and `Escalate`.
- Exports reviewer-ready CSV files.
- Includes a photo OCR intake demo for bottle/can/shelf photos without
  application fields.
- Includes a local public-COLA side-by-side demo when gitignored COLA Cloud data
  is present.

## Runtime Architecture

```text
Browser
  -> FastAPI + Jinja2/HTMX
  -> upload preflight
  -> local OCR adapter
  -> optional DistilRoBERTa field-support arbiter
  -> deterministic source-backed rules
  -> government-warning boldness preflight
  -> reviewer policy queue
  -> filesystem job store + CSV export
```

The deployed app does not use hosted OCR or hosted ML APIs at runtime.

Current OCR path:

- fixture OCR for deterministic demos and tests,
- local docTR for real uploads,
- optional DistilRoBERTa field-support scoring when the model artifact is
  mounted,
- exported logistic warning-heading boldness model in
  `app/models/typography/boldness_logistic_v1.json`.

## Reviewer Queues

The app keeps raw machine verdicts separate from workflow disposition.

| Raw result | Policy setting | Queue |
|---|---|---|
| Pass | acceptance review off | Ready to accept |
| Pass | acceptance review on | Acceptance review |
| Fail | rejection review off | Ready to reject |
| Fail | rejection review on | Rejection review |
| Needs Review | any | Manual evidence review |
| Unknown government-warning evidence | warning review off | Fail, then rejection policy |
| Unknown government-warning evidence | warning review on | Manual evidence review |

This gives the evaluator a clean control board without pretending the prototype
has production authentication, roles, or final agency-action controls.

## Measured Model Results

These are the useful statistics to report. Raw data and large model artifacts
live under gitignored `data/work/`.

### Public COLA Corpus

The evaluation corpus was built from COLA Cloud public data after direct
TTBOnline image access became unreliable.

| Split | Applications | Label images |
|---|---:|---:|
| Train | 2,000 | 3,564 |
| Validation | 1,000 | 1,789 |
| Locked holdout | 3,000 | 5,082 |
| Total | 6,000 | 10,435 |

The split is by TTB ID, with no overlap across train, validation, and holdout.
Sampling is stratified by month, product type, origin/import status, and
single-panel vs multi-panel applications where available.

### DistilRoBERTa Field-Support Arbiter

The DistilRoBERTa model is a text-pair classifier. It scores whether a candidate
OCR/application text fragment supports a target field. It is not the OCR engine
and it is not the compliance decision maker.

Training data: weakly supervised clean text pairs from accepted public COLA
application fields. Because this run used clean field-pair text rather than
noisy OCR candidates, the numbers prove the bridge can learn field support; they
do not prove final OCR extraction accuracy.

| Split | Examples | F1 | False-clear rate |
|---|---:|---:|---:|
| Train | 31,008 | 1.000000 | 0.000000 |
| Validation | 15,417 | 1.000000 | 0.000000 |
| Locked holdout | 46,992 | 0.999904 | 0.000096 |

Runtime settings:

```text
model_id: distilroberta-base
threshold: 0.53
CPU latency: mean 17.56 ms / text pair, p95 19.36 ms / text pair
```

### Government-Warning Boldness Preflight

Jenny's interview note made the warning heading strict: `GOVERNMENT WARNING:`
must be all caps and bold. The deployed typography preflight is intentionally
narrow: it isolates the warning heading crop and classifies whether there is
strong bold evidence.

| Metric | Value |
|---|---:|
| Selected threshold | 0.9546 |
| Validation false-clear rate | 0.000624 |
| Synthetic holdout false-clear rate | 0.001800 |
| Held-out approved-COLA clear rate | 92.19% |
| Real COLA sanity latency | about 37 ms crop + classify |

Safety posture: confident bold evidence can pass. Weak, blurry, missing, or
uncertain crop evidence routes to `Needs Review`. The typography model does not
hard-reject a label by itself.

### Offline Model Experiments

Additional experiments are preserved under `experiments/` and summarized in
`MODEL_LOG.md` and `docs/performance.md`.

Useful conclusions:

- PaddleOCR improved F1 in a 30-image smoke test but had a higher false-clear
  rate than docTR, so it was not promoted directly.
- OpenOCR/SVTRv2 was fast but did not beat docTR/PaddleOCR on field support in
  the first smoke.
- PARSeq, ASTER, FCENet, and ABINet were useful research checks but were not
  promoted because crop dependence, recall loss, or CPU latency made them poor
  fits for the submission runtime.
- A graph-aware evidence scorer improved field-support F1 in a 100-application
  proof of concept, but it is not wired into the deployed app because it still
  needs artifact export, same-split comparison, CPU latency proof, and tests.
- CNN-inclusive typography ensembles were tested offline. They remain promotion
  candidates, but the deployed app keeps the smaller logistic model because it
  is fast, explainable, serialized as JSON, and already wired with conservative
  review routing.

## Getting Started

### Option A: Docker

```bash
git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
cp .env.example .env
docker compose build
docker compose up -d
curl http://localhost:8000/health
```

Open:

```text
http://localhost:8000
```

If you are using Podman locally:

```bash
podman build -t labels-on-tap-app:local .
podman run --rm -p 8000:8000 -v "$PWD/data/jobs:/app/data/jobs:Z" labels-on-tap-app:local
```

### Option B: Local Python

Python 3.11 is recommended. The pinned requirements install CPU PyTorch wheels.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/bootstrap_project.py --if-missing
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest -q
```

Last verified full container test run:

```text
91 passed
```

## Environment

Key settings in `.env.example`:

```text
DATA_DIR=./data
OCR_CONFIDENCE_THRESHOLD=0.70
MAX_UPLOAD_BYTES=10485760
MAX_MANIFEST_BYTES=1048576
MAX_ARCHIVE_BYTES=262144000
MAX_BATCH_ITEMS=400
PUBLIC_BASE_URL=https://www.labelsontap.ai
FIELD_SUPPORT_MODEL_ENABLED=true
FIELD_SUPPORT_MODEL_DIR=/app/models/field_support/distilroberta
FIELD_SUPPORT_THRESHOLD=0.53
FIELD_SUPPORT_MAX_CANDIDATES=18
COLACLOUD_API_KEY=
```

`COLACLOUD_API_KEY` is for offline public-corpus pulls only. The deployed app
does not call COLA Cloud at runtime.

## How To Demo

From the home page:

1. Run `Clean Label Demo`.
2. Run `Warning Failure Demo`.
3. Run `ABV Failure Demo`.
4. Run `Malt Net Contents Failure Demo`.
5. Run `Import Origin Demo`.
6. Run `Batch Demo`.
7. Open `/review` to show queue-level triage.
8. Open a result detail page and save a reviewer decision.
9. Export CSV from a job page.
10. Upload a local phone photo through `Photo OCR Intake Demo`.

Manual batch upload requires:

- `manifest.csv` or `manifest.json`,
- loose JPG/PNG files or a ZIP archive,
- filenames in the manifest matching image basenames.

## Deployment

Production demo target:

```text
https://www.labelsontap.ai
```

Deployment shape:

```text
AWS Lightsail / Linux VM
Docker Compose
FastAPI app container
Caddy reverse proxy with automatic HTTPS
Filesystem job volume
```

Refresh the deployed app:

```bash
cd ~/Labels-On-Tap
git pull
docker compose build
docker compose up -d
docker compose logs --tail=100 app
curl https://www.labelsontap.ai/health
```

## File Structure

```text
Labels-On-Tap/
├── app/
│   ├── main.py                         FastAPI application factory and routes mount
│   ├── routes/                         Page, upload, demo, job, review, and export routes
│   ├── schemas/                        Pydantic request/result contracts
│   ├── services/
│   │   ├── ocr/                        OCR protocol plus fixture/docTR adapters
│   │   ├── rules/                      Source-backed compliance checks
│   │   ├── typography/                 Government-warning heading crop/classifier
│   │   ├── batch_queue.py              Filesystem-backed batch queue
│   │   └── ...
│   ├── templates/                      Jinja2/HTMX pages
│   ├── static/                         Local CSS
│   └── models/typography/              Small deployed typography model artifact
├── data/
│   ├── fixtures/demo/                  Committed deterministic demo fixtures
│   ├── source-maps/                    Fixture provenance and expected outputs
│   ├── jobs/                           Runtime job store, gitignored
│   └── work/                           ETL/model/OCR work area, gitignored
├── docs/                               Deployment, security, performance, ETL notes
├── experiments/                        Offline OCR/model comparison experiments
├── research/                           Source-backed legal and COLA research corpus
├── scripts/                            Bootstrap, ETL, sampling, and evaluation scripts
├── tests/                              Unit and integration tests
├── Dockerfile
├── docker-compose.yml
├── Caddyfile
├── requirements.txt
└── pyproject.toml
```

Gitignored runtime data:

```text
data/jobs/
data/work/
```

## Known Limits

- The app is not an official TTB system and does not issue final agency action.
- Authentication, roles, admin portal, audit-grade logs, and retention policy
  are future production work.
- Real uploads use local OCR and may require model warmup.
- The field-support model's strongest statistics are from clean text-pair
  supervision. A full noisy OCR holdout evaluation is the next measurement gate.
- ZIP upload is guarded for the prototype but would need malware scanning and
  quarantine handling in production.
- The graph-aware scorer and CNN-inclusive typography ensembles are documented
  but not deployed.

## Supporting Documents

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Current runtime architecture and deployment shape |
| `MODEL_ARCHITECTURE.md` | Current model stack and offline promotion candidates |
| `MODEL_LOG.md` | Concise experiment ledger and measured statistics |
| `TRADEOFFS.md` | Why the app uses this architecture for the submission |
| `TASKS.md` | Final delivery checklist |
| `DEMO_SCRIPT.md` | Suggested live demo flow |
| `docs/performance.md` | Detailed performance and model measurements |
| `docs/deployment.md` | Deployment notes |
| `docs/security-and-privacy.md` | Prototype security posture |
