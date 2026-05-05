# Labels On Tap

Labels On Tap helps reviewers triage COLA-style alcohol label applications by
reading every submitted label image, comparing the scraped evidence against the
application fields, and routing each case to `Pass`, `Needs Review`, or `Fail`.
It focuses on the problems stakeholders called out directly: routine field
matching, exact government-warning checks, multi-panel applications, batch
review, fast local processing, and clear human-review controls when the evidence
is uncertain.

The prototype is intentionally local-first. It does not rely on hosted OCR APIs
or LLM-based compliance decisions at runtime because compliance workflows need
inspectable evidence, low false-clear risk, and predictable behavior without
hallucinations. This also aligns with the stakeholder constraints around blocked
outbound traffic, federal security posture, and future FedRAMP/Azure deployment
concerns. Models are used only as local evidence tools; deterministic rules and
reviewer policy controls make the final triage decision.

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
- Supports single-image verification through the backend and fixture routes.
  The primary user-facing upload path is now COLA-style application folders.
- Supports one application with multiple label panels.
- Supports manifest-backed batch uploads using loose images or a ZIP archive.
- Supports COLA-style batch rows where one application has multiple label
  panels through a `panel_filenames` manifest column.
- Uses a local filesystem-backed queue so batch jobs do not run inside the
  browser request.
- Provides a reviewer dashboard at `/review`.
- Persists reviewer decisions. Job cards expose the fast `Accept` / `Reject`
  actions; item detail pages also support `Request correction / better image`,
  `Override with note`, and `Escalate`.
- Exports reviewer-ready CSV files.
- Includes a photo OCR intake demo for bottle/can/shelf photos without
  application fields.
- Includes a server-hosted public-COLA demo page when the curated, gitignored
  demo pack is present on the deployment host.

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

Current evidence path:

- fixture OCR for deterministic demos and tests,
- local docTR for real uploads,
- optional DistilRoBERTa field-support scoring after OCR when the model artifact
  is mounted,
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
live under gitignored `data/work/` and are not committed to the repository.

### Public COLA Corpus

The evaluation corpus was built from COLA Cloud public data after direct
TTBOnline image access became unreliable. These records were used for local
evaluation and demo-pack generation; the full corpus is not included in the
repository.

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

### Option A: Docker Direct Local Run

```bash
git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
docker build -t labels-on-tap-app:local .
docker run --rm -p 8000:8000 \
  -v "$PWD/data/jobs:/app/data/jobs" \
  -v "$PWD/data/work/demo-upload:/app/data/work/demo-upload:ro" \
  labels-on-tap-app:local
```

In another terminal:

```bash
curl http://localhost:8000/health
```

Open:

```text
http://localhost:8000
```

If you are using Podman locally:

```bash
podman build -t labels-on-tap-app:local .
podman run --rm -p 8000:8000 \
  -v "$PWD/data/jobs:/app/data/jobs:Z" \
  -v "$PWD/data/work/demo-upload:/app/data/work/demo-upload:ro,Z" \
  labels-on-tap-app:local
```

### Option B: Docker Compose

Docker Compose is the production-shaped setup used on AWS Lightsail. It runs the
FastAPI app behind Caddy. The checked-in `Caddyfile` is configured for the
public domain, so the simplest local Compose health check runs inside the app
container. Compose also mounts optional gitignored runtime data when present,
including the curated demo pack and DistilRoBERTa field-support artifact.

```bash
git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
docker compose build
docker compose up -d
docker compose exec app curl -s http://localhost:8000/health
```

If the optional field-support model artifact is absent, the app still runs and
falls back to deterministic OCR/text matching.

For local browser testing, the direct Docker or local Python options are simpler
because they expose the app directly at `http://localhost:8000`.

### Option C: Local Python

Python 3.11 is recommended. The pinned requirements install CPU PyTorch wheels.
The application reads configuration from environment variables. `.env.example`
documents the expected values, but local Python does not automatically load
`.env`; export variables in your shell only when you need to override defaults.

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
105 passed
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

1. Click `LOT Demo` to open the server-hosted 300-application public COLA
   walkthrough. No upload is required.
2. Browse applications and their label panels with the previous/next controls.
3. Click `Parse This Application` to populate the `Scraped` column beside the
   `Actual` application data for one application.
4. Click `Parse This Directory of Applications` to run the full demo pack and
   show progress, timing, queue counts, and review routing.
5. Use `Accept` or `Reject` on the result cards to demonstrate reviewer action
   capture.
6. Export CSV from the job page to show the reviewer-ready output.
7. Click `LOT Actual` to upload your own application folder or a folder of
   applications. Uploaded data stays available in that browser until `Reset`.
8. Use `Download Examples` and `Data Format Instructions` from `LOT Actual` if
   you want a ready-made upload pack and the expected folder layout.
9. Open `/review` to show queue-level triage across jobs.

Application directory upload requires:

- one `manifest.csv` or `manifest.json` at the selected directory root,
- JPG/PNG panels in nested application folders,
- filenames in the manifest matching image paths after the selected root folder
  is stripped,
- optional multi-panel rows with `panel_filenames` separated by semicolons.

Example application row:

```csv
filename,panel_filenames,product_type,brand_name,class_type,alcohol_content,net_contents,imported,country_of_origin
25079001000835,images/25079001000835/front.png;images/25079001000835/back.png,wine,Example Winery,Sauvignon Blanc,12% BY VOL,750 mL,true,France
```

Evaluators do not need to build the public demo pack to use the deployed app.
When local COLA Cloud-derived working data is present, developers can recreate
the curated 300-application walkthrough pack used by `/public-cola-demo`:

```bash
python scripts/create_curated_public_cola_demo_pack.py --limit 300 --zip --force
```

Output is written to `data/work/demo-upload/public-cola-curated-300/` and is
intentionally gitignored. The exporter filters out registry artifacts that are
named like images but fail JPG/PNG signature or Pillow decode checks. It also
writes curated OCR/typography sidecars for a stable interview walkthrough. Do
not use this pack as an accuracy metric; use the evaluation corpus and holdout
metrics for performance claims.

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
git pull origin main
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
├── APP_USE_INSTRUCTIONS.md
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
- Arbitrary phone/shelf photos can exceed the 5-second target when OCR has to
  process a difficult image cold. The public demo and downloaded example data
  use curated cached evidence for a stable walkthrough; live upload performance
  remains the next optimization gate.
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
| `APP_USE_INSTRUCTIONS.md` | Plain-English guide for using LOT Demo and LOT Actual |
| `docs/performance.md` | Detailed performance and model measurements |
| `docs/deployment.md` | Deployment notes |
| `docs/security-and-privacy.md` | Prototype security posture |
