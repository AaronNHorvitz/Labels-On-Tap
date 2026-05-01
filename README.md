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

## Why Local-First

The take-home stakeholder notes make local-first architecture a product requirement, not just a technical preference. A prior vendor-style approach reportedly ran into federal network constraints and adoption problems because it depended on hosted AI endpoints and slow processing.

Labels On Tap therefore keeps the review loop inside the app environment:

```text
label image + application fields
  -> local OCR or deterministic fixture OCR
  -> source-backed rules
  -> Pass / Needs Review / Fail
```

For this prototype, "local-first" means:

- no hosted OCR or hosted ML runtime,
- no OpenAI, Anthropic, Google Vision, Azure Vision, AWS Textract, or hosted VLM calls,
- no dependency on private COLAs Online data,
- no hidden rejected-label corpus,
- deterministic demos and tests that run from repository fixtures.

The app can still run on a cloud VM. The important distinction is that the VM runs the OCR and validation code itself instead of forwarding label images to a third-party AI service.

---

## What Is Implemented

- FastAPI app with server-rendered Jinja2 templates and local HTMX.
- Local CSS with high-contrast Pass / Needs Review / Fail states.
- Single-label upload form with product/application fields.
- Manifest-backed batch upload for multiple label images.
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
| **Run Batch Demo** | 12-row triage table: 3 Pass, 3 Needs Review, 6 Fail |

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

## Stakeholder-Driven Design

The prototype is built around the four stakeholder voices in the prompt, plus the practical needs of an evaluator reviewing the take-home.

| Stakeholder | What They Needed | Product Response |
|---|---|---|
| Sarah Chen, Deputy Director of Label Compliance | Reduce routine matching work and make high-volume review easier. | One-click demos, single-label upload, manifest-backed batch upload, result tables, CSV export, and a fixture-backed batch triage demo. |
| Marcus Williams, IT / Infrastructure | Avoid blocked hosted ML endpoints and keep deployment straightforward. | FastAPI, Docker Compose, Caddy, local OCR adapter, fixture fallback, filesystem storage, and no hosted ML/OCR runtime. |
| Dave Morrison, Senior Compliance Agent | Avoid false failures for harmless differences like case, punctuation, and OCR noise. | RapidFuzz-based brand matching, normalization for fuzzy fields, and Needs Review for ambiguous scores. |
| Jenny Park, Junior Compliance Agent | Catch exact checklist failures, especially government warning wording and capitalization. | Strict canonical warning check, strict `GOVERNMENT WARNING:` heading check, and manual typography review fallback for boldness. |
| Evaluator / hiring panel | See a working app quickly and understand the engineering trade-offs. | Five-minute demo path, generated fixtures, tests, architecture docs, trade-offs, and source-backed rule explanations. |

The result is intentionally narrow: it demonstrates the highest-signal workflow first instead of spreading effort across a large unfinished compliance surface.

---

## Validation Philosophy

Labels On Tap uses different standards for different kinds of checks.

| Check Type | Examples | Verdict Policy |
|---|---|---|
| Strict deterministic checks | Government warning exact text, warning heading capitalization, prohibited `ABV` shorthand, malt `16 fl. oz.` net contents issue | Fail when the source-backed mismatch is clear and OCR confidence is adequate. |
| Fuzzy application-field checks | Brand name, country of origin for imports | Pass on strong match, Needs Review on ambiguity, Fail only on clear mismatch or conflicting evidence. |
| Manual-review checks | Low OCR confidence, raster typography/boldness, missing warning isolation | Needs Review instead of pretending the image evidence is stronger than it is. |

Every rule check returns:

```text
rule_id
name
category
verdict
expected
observed
evidence_text
source_refs
message
reviewer_action
```

This makes the app auditable: a reviewer can inspect not only the verdict, but also the evidence and the reason the rule fired.

Implemented rule behavior in brief:

| Rule ID | Behavior |
|---|---|
| `FORM_BRAND_MATCHES_LABEL` | Fuzzy matches the application brand against OCR text; casing differences should pass. |
| `COUNTRY_OF_ORIGIN_MATCH` | Applies to imported products; passes on clear expected-country match, needs review when missing/low confidence, fails on conflicting country evidence. |
| `GOV_WARNING_EXACT_TEXT` | Compares warning text to canonical wording with whitespace normalization only. |
| `GOV_WARNING_HEADER_CAPS` | Requires the heading to be exactly `GOVERNMENT WARNING:`. |
| `GOV_WARNING_HEADER_BOLD_REVIEW` | Routes font-weight verification to manual review instead of brittle raster hard-fail logic. |
| `ALCOHOL_ABV_PROHIBITED` | Flags `ABV` / `A.B.V.` shorthand near an alcohol percentage. |
| `MALT_NET_CONTENTS_16OZ_PINT` | For malt beverages, flags `16 fl. oz.` style wording when `1 Pint` is expected. |
| `OCR_LOW_CONFIDENCE` | Routes low-confidence OCR output to Needs Review. |

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

## Using The Application

### Demo Queue

The fastest way to evaluate the app is the demo queue on the home page. Each button creates a new filesystem-backed job from deterministic fixture data and redirects to the result table.

Available demo scenarios:

```text
/demo/clean
/demo/warning
/demo/abv
/demo/net_contents
/demo/country_origin
/demo/batch
```

The demo route uses fixture OCR ground truth so the interview demo is deterministic even if first-run docTR model setup is slow.

### Single Label Upload

The single-label form accepts:

```text
brand_name
product_type
class_type
alcohol_content
net_contents
imported
country_of_origin
label_image
```

Supported image extensions are:

```text
.jpg
.jpeg
.png
```

Current upload preflight rejects unsupported extensions, path components, double extensions, oversize files, files whose signature does not match JPG/PNG, and corrupt images that Pillow cannot decode. Accepted uploads are stored under randomized server-side filenames while preserving the original filename as metadata.

### Result Review

Each job page shows:

- total processed items,
- Pass / Needs Review / Fail counts,
- per-label top reason,
- OCR source,
- processing time,
- links to item detail pages,
- CSV export.

The item detail page shows application fields, OCR source, per-rule verdicts, expected/observed values, source refs, reviewer actions, and the full OCR text used for the decision.

### Batch Review

The home page includes a batch upload form that accepts a `manifest.csv` or `manifest.json` file plus multiple `.jpg/.jpeg/.png` label images. The manifest filenames must match the uploaded image filenames. The server validates the manifest, rejects missing or unreferenced images, stores accepted images under randomized filenames, then runs the same OCR and rule engine used by single-label review.

The **Run Batch Demo** button uses the same generated fixture set to demonstrate mixed verdicts, item details, and CSV export without requiring the evaluator to assemble files manually.

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
brand_mismatch_fail
imported_missing_country_review
conflicting_country_origin_fail
warning_missing_block_review
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

## Batch Manifest Format

The generated batch demo uses a CSV manifest and a JSON manifest. These files are part of the deterministic fixture pipeline and use the same contract as the manual batch upload form.

Current CSV columns:

```csv
filename,fixture_id,product_type,brand_name,class_type,alcohol_content,net_contents,country_of_origin,imported,expected_verdict
clean_malt_pass.png,clean_malt_pass,malt_beverage,OLD RIVER BREWING,Ale,5% ALC/VOL,1 Pint,,false,pass
imported_country_origin_pass.png,imported_country_origin_pass,wine,VALLEY RIDGE,Red Wine,13.5% ALC/VOL,750 mL,France,true,pass
```

Current JSON item shape:

```json
{
  "fixture_id": "imported_country_origin_pass",
  "filename": "imported_country_origin_pass.png",
  "product_type": "wine",
  "brand_name": "VALLEY RIDGE",
  "class_type": "Red Wine",
  "alcohol_content": "13.5% ALC/VOL",
  "net_contents": "750 mL",
  "country_of_origin": "France",
  "imported": true,
  "expected": {
    "overall_verdict": "pass",
    "checked_rule_ids": ["COUNTRY_OF_ORIGIN_MATCH"],
    "triggered_rule_ids": []
  }
}
```

Manual manifest upload is wired into the home page batch form. The fixture generator, tests, and batch demo use the same schema so the data contract stays stable.

---

## API / Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Home page, demo buttons, single upload form |
| `/health` | GET | Health check |
| `/jobs` | POST | Create a single-label job |
| `/jobs/batch` | POST | Create a manifest-backed batch job |
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

## Performance Expectations

The evaluator demos are intentionally fast and deterministic because they use fixture OCR ground truth. Real uploads use the local docTR adapter, so first-run behavior can include model download or warmup depending on the host environment.

Performance goals for the deployed prototype:

| Area | Target |
|---|---|
| Home page / demo route | Immediate response after app startup |
| Fixture-backed demo processing | Fast enough for live interview walkthrough |
| Real OCR upload | Approximately 5 seconds per label after OCR warmup, dependent on VM CPU/RAM and image complexity |
| Batch UX | Show a job/results page immediately and let reviewers inspect completed results |

The repository does not claim measured production OCR latency yet. Final measured values should be recorded in [docs/performance.md](docs/performance.md) after local Docker and public VM smoke testing.

---

## Security And Privacy

Implemented upload controls:

- extension allowlist for `.jpg`, `.jpeg`, `.png`,
- double-extension rejection,
- path component rejection,
- image signature validation,
- max upload size enforcement,
- randomized server-side filenames,
- original filename preserved as metadata only,
- Pillow decode validation after signature check.

Runtime privacy:

- no hosted ML/OCR APIs,
- no private COLAs Online access,
- no confidential rejected-label data,
- uploaded files/results stored only in local filesystem job folders for the prototype.

---

## Known Limitations

- Batch upload runs synchronously in the web process for the sprint prototype; a production version should use a worker queue.
- Government warning boldness routes to Needs Review instead of hard-failing from raster font-weight guesses.
- docTR local OCR may require model download/warmup.
- The active rule set is intentionally narrow.
- Production use would require auth, audit logs, retention policy, formal security review, Section 508 review, and deeper legal validation.

See [TRADEOFFS.md](TRADEOFFS.md) for the fuller rationale.

---

## Troubleshooting

### Dependency install is slow

`python-doctr[torch]` can pull large CPU OCR dependencies. This is expected. The fixture demos and tests do not require hosted OCR or live external data.

### First real OCR upload is slow

The first docTR run may need model initialization or cached weights. Run a demo first to confirm the web app is healthy, then test a real upload.

### Docker health check fails on localhost

The Compose stack uses the production Caddy hostnames. Use:

```bash
curl -H "Host: www.labelsontap.ai" http://localhost/health
```

Do not use `curl http://localhost:8000/health` with the default Compose file because the FastAPI app service is internal to the Docker network.

### Public domain does not resolve

Check:

```bash
dig labelsontap.ai
dig www.labelsontap.ai
curl -I http://labelsontap.ai
curl -I https://www.labelsontap.ai
docker compose ps
docker compose logs caddy
docker compose logs app
```

Confirm that both A records point to the VM Elastic IP and that ports `80` and `443` are open.

### Demos work but real uploads fail

Check:

- uploaded file extension is `.jpg`, `.jpeg`, or `.png`,
- file signature matches the extension family,
- Docker container has enough RAM for docTR/PyTorch,
- app logs do not show OCR model import or weight-cache failures,
- result detail page says whether OCR source was `fixture ground truth` or local docTR.

---

## Future Production Hardening

A production federal version would need additional work beyond the take-home prototype:

- authentication and role-based access control,
- audit logs and immutable review history,
- formal records retention and cleanup policy,
- Section 508 accessibility review,
- vulnerability scanning and software bill of materials,
- signed container images,
- secrets management,
- centralized logging and monitoring,
- background worker queue for large batches,
- PostgreSQL or an approved enterprise data store,
- broader rule coverage across wine, spirits, malt beverages, formulas, appellations, claims, and prohibited statements,
- formal legal review of rule interpretations,
- performance benchmarking with representative image sets,
- explicit integration plan for COLAs Online or internal workflows.

For this sprint, those items stay outside the MVP so the deployed demo can remain focused, inspectable, and reliable.

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
