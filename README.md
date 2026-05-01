# Labels On Tap

**Local-first, source-backed alcohol label verification for TTB-style COLA review.**

[![Live Demo](https://img.shields.io/badge/Demo-www.labelsontap.ai-blue?style=for-the-badge)](https://www.labelsontap.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Jinja2%20%2B%20HTMX-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Caddy-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

> **Deployment target:** `https://www.labelsontap.ai`
> **Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
> **Status:** take-home prototype; reviewer-support tool, not an official TTB/Treasury system.

---

## Executive Summary

Labels On Tap is a local-first prototype for beverage-alcohol label preflight review. It compares label artwork against Form 5100.31-style application fields, runs local OCR or deterministic fixture OCR, applies source-backed validation rules, and returns:

| Verdict | Meaning |
|---|---|
| **Pass** | Implemented checks appear consistent with the provided application fields. |
| **Needs Review** | OCR confidence, image quality, typography, or legal context needs a human reviewer. |
| **Fail** | A deterministic source-backed mismatch was found with adequate evidence. |

The core design principle is simple:

> Fail deterministic issues. Pass only when the evidence is strong. Route ambiguity to Needs Review. Always show why.

---

## What Is Implemented

- FastAPI app with server-rendered Jinja2 templates and local HTMX.
- Local CSS with high-contrast Pass / Needs Review / Fail states.
- Single-label upload form with product/application fields.
- Fixture-backed one-click demos for evaluator review.
- Filesystem job/result store under `data/jobs/`.
- CSV export for job results.
- Deterministic synthetic fixtures and source maps.
- Local docTR OCR adapter with fixture OCR fallback.
- Docker Compose and Caddy deployment stack.

Implemented demo scenarios:

| Button | Expected Outcome |
|---|---|
| **Run Clean Label Demo** | Pass |
| **Run Warning Failure Demo** | Fail |
| **Run ABV Failure Demo** | Fail |
| **Run Malt Net Contents Failure Demo** | Fail |
| **Run Import Origin Demo** | Pass |
| **Run Batch Demo** | 8-row triage table: 3 Pass, 1 Needs Review, 4 Fail |

Implemented rule IDs:

```text
FORM_BRAND_MATCHES_LABEL
COUNTRY_OF_ORIGIN_MATCH
GOV_WARNING_EXACT_TEXT
GOV_WARNING_HEADER_CAPS
GOV_WARNING_HEADER_BOLD_REVIEW
ALCOHOL_ABV_PROHIBITED
MALT_NET_CONTENTS_16OZ_PINT
OCR_LOW_CONFIDENCE
```

---

## What This Is Not

Labels On Tap does not:

- approve or reject COLAs,
- replace TTB label specialists,
- provide legal advice,
- call hosted OCR or hosted ML APIs at runtime,
- scrape private COLAs Online data,
- use confidential rejected or Needs Correction applications,
- implement every federal beverage-alcohol rule in the sprint MVP.

It is a focused, auditable reviewer-support prototype.

---

## Five-Minute Demo

For the exact presentation path, use [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

Quick path:

1. Open `https://www.labelsontap.ai`.
2. Run **Clean Label Demo** and confirm **Pass**.
3. Run **Warning Failure Demo** and inspect expected vs. observed warning text.
4. Run **ABV Failure Demo** and inspect the prohibited shorthand evidence.
5. Run **Malt Net Contents Failure Demo** and inspect the `16 fl. oz.` issue.
6. Run **Import Origin Demo** and inspect `COUNTRY_OF_ORIGIN_MATCH`.
7. Run **Batch Demo**, open the Needs Review item, and export CSV.

---

## Architecture

```text
Browser
  -> FastAPI routes
  -> Jinja2 templates + HTMX partials
  -> upload preflight
  -> fixture OCR fallback or local docTR OCR
  -> source-backed rule engine
  -> filesystem job store
  -> result table, detail page, CSV export
```

Runtime choices:

| Layer | Choice |
|---|---|
| Web | FastAPI |
| UI | Jinja2 + HTMX + local CSS |
| OCR | docTR adapter; fixture fallback for deterministic demos/tests |
| Matching | RapidFuzz |
| Image handling | Pillow; OpenCV-headless dependency reserved for image preflight work |
| Storage | Filesystem JSON job store |
| Deployment | Docker Compose + Caddy |
| Host target | AWS EC2 Ubuntu VM |

The app does not send label images to OpenAI, Anthropic, Google Vision, Azure Vision, AWS Textract, or hosted VLM/OCR services.

---

## Repository Map

```text
app/
  routes/               FastAPI UI, job, demo, and health routes
  schemas/              Pydantic application, OCR, manifest, and result models
  services/
    ocr/                fixture and docTR OCR adapters
    preflight/          upload name/signature/image-quality helpers
    rules/              source-backed validation logic
    job_store.py        filesystem job/result storage
    csv_export.py       CSV output
  templates/            Jinja2 pages and partials
  static/               local CSS and vendored HTMX

data/fixtures/demo/     generated synthetic demo labels and JSON payloads
data/source-maps/       expected results and fixture provenance
docs/                   focused supporting documentation
research/legal-corpus/  source ledger, rule matrix, excerpts, reports
scripts/                corpus/bootstrap/fixture scripts
tests/                  unit and integration tests
```

Important root docs:

- [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- [TASKS.md](TASKS.md)
- [TRADEOFFS.md](TRADEOFFS.md)
- [PRD.md](PRD.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Local Environment

Use this path for local development without Docker.

### 1. Clone

```bash
git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
```

### 2. Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

If `python3.11` is not available but your `python3` is Python 3.11+, use:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` is the install source of truth. `pyproject.toml` is used only for lightweight pytest configuration.

The local docTR/PyTorch install can be large. The one-click demos and test suite use fixture OCR, so they can run even when real OCR setup is slower.

### 4. Configure environment

```bash
cp .env.example .env
```

Runtime job files are written under `data/jobs/`, which is gitignored.

### 5. Bootstrap data

```bash
python scripts/bootstrap_project.py --if-missing
```

This validates or creates:

```text
research/legal-corpus/
data/fixtures/demo/
data/source-maps/
```

### 6. Run locally

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://localhost:8000
```

### 7. Run tests

```bash
pytest -q
```

---

## Docker

```bash
docker compose build
docker compose up -d
curl -H "Host: www.labelsontap.ai" http://localhost/health
```

Stop:

```bash
docker compose down
```

Notes:

- Caddy listens on ports `80` and `443`.
- The app service stays internal on port `8000`.
- The Compose stack uses the production Caddy hostnames. For local Docker smoke tests, send the `www.labelsontap.ai` Host header as shown above.
- Docker build may take time because docTR/PyTorch dependencies are large.

---

## Deployment

Target stack:

```text
AWS EC2 On-Demand
Ubuntu 24.04 LTS
m7i.xlarge preferred; t3a.large/t3.large fallback
40-60 GB gp3 EBS
Elastic IP
Docker Compose
Caddy
```

DNS:

```text
www.labelsontap.ai  A  <Elastic IP>
labelsontap.ai      A  <Elastic IP>
```

Caddy behavior:

```text
www.labelsontap.ai -> reverse proxy to app:8000
labelsontap.ai     -> permanent redirect to https://www.labelsontap.ai
```

Server quick path:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y git
git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
cp .env.example .env
docker compose build
docker compose up -d
docker compose logs -f app
```

Public smoke:

```bash
curl -I https://www.labelsontap.ai
curl https://www.labelsontap.ai/health
curl -I https://labelsontap.ai
```

---

## Data And Fixtures

The app does not depend on a hidden rejected-label corpus.

Data sources:

| Source | Use |
|---|---|
| Runtime user upload | Real label/application review |
| Synthetic fixtures | Deterministic demos and tests |
| Legal corpus | Source-backed rule definitions |
| Public approved COLA examples | Optional future OCR realism |

Generated demo fixture set:

```text
clean_malt_pass
warning_missing_comma_fail
warning_title_case_fail
abv_prohibited_fail
malt_16_fl_oz_fail
brand_case_difference_pass
low_confidence_blur_review
imported_country_origin_pass
```

Each fixture has:

```text
{fixture_id}.png
{fixture_id}.application.json
{fixture_id}.ocr_text.json
{fixture_id}.expected.json
```

See [docs/fixture-generation.md](docs/fixture-generation.md).

---

## API / Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Home page, demo buttons, single upload form |
| `/health` | GET | Health check |
| `/jobs` | POST | Create a single-label job |
| `/jobs/{job_id}` | GET | Job result table |
| `/jobs/{job_id}/status` | GET | HTMX status partial |
| `/jobs/{job_id}/items/{item_id}` | GET | Result detail |
| `/jobs/{job_id}/results.csv` | GET | CSV export |
| `/demo/{scenario}` | GET | One-click fixture demo |

Demo scenarios:

```text
clean
warning
abv
net_contents
country_origin
batch
```

---

## Testing And Quality Gates

Run:

```bash
python -m py_compile scripts/bootstrap_legal_corpus.py scripts/validate_legal_corpus.py scripts/bootstrap_project.py scripts/seed_demo_fixtures.py $(rg --files app -g '*.py')
python scripts/bootstrap_project.py --if-missing
python scripts/validate_legal_corpus.py
pytest -q
```

Current test coverage includes:

- warning rules,
- ABV detection,
- malt net-contents rule,
- brand fuzzy matching,
- country-of-origin behavior,
- fixture/demo scenarios,
- bootstrap validation,
- app route smoke tests.

---

## Security And Privacy

Implemented or planned upload controls:

- extension allowlist for `.jpg`, `.jpeg`, `.png`,
- double-extension rejection,
- path component rejection,
- image signature validation,
- max upload size enforcement planned before deployment,
- randomized server-side filenames planned before deployment,
- Pillow decode validation planned before deployment.

Runtime privacy:

- no hosted ML/OCR APIs,
- no private COLAs Online access,
- no confidential rejected-label data,
- uploaded files/results stored only in local filesystem job folders for the prototype.

---

## Known Limitations

- Manual multi-file batch upload is a stretch item; the current batch workflow is fixture-backed for deterministic evaluation.
- Government warning boldness routes to Needs Review instead of hard-failing from raster font-weight guesses.
- docTR local OCR may require model download/warmup.
- The active rule set is intentionally narrow.
- Production use would require auth, audit logs, retention policy, formal security review, Section 508 review, and deeper legal validation.

See [TRADEOFFS.md](TRADEOFFS.md) for the fuller rationale.

---

## Primary Public Sources

- TTB Public COLA Registry: https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry
- TTB Form 5100.31: https://www.ttb.gov/system/files/images/pdfs/forms/f510031.pdf
- 27 CFR Part 4 — Wine: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4
- 27 CFR Part 5 — Distilled Spirits: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5
- 27 CFR Part 7 — Malt Beverages: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7
- 27 CFR Part 13 — Labeling Proceedings: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-13
- 27 CFR Part 16 — Government Health Warning: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
- docTR installation docs: https://mindee.github.io/doctr/getting_started/installing.html
- FastAPI file upload docs: https://fastapi.tiangolo.com/tutorial/request-files/
- Caddy automatic HTTPS docs: https://caddyserver.com/docs/automatic-https

---

## License / Use

This repository is a take-home prototype for evaluation. It is not an official TTB system, not an official Treasury product, and not legal advice.
