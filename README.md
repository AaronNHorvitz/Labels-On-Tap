# Labels On Tap

**Local-first, source-backed alcohol label verification for TTB-style COLA review.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-www.labelsontap.ai-blue?style=for-the-badge)](https://www.labelsontap.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-local%20API-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-containerized-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Local OCR](https://img.shields.io/badge/OCR-local--first-orange?style=flat-square)](#why-local-first)

> **Deployment target:** `https://www.labelsontap.ai`
> **Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
> **Prototype status:** six-day take-home build; production-informed, not production-authorized.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [What This Prototype Does](#what-this-prototype-does)
3. [What This Prototype Does Not Do](#what-this-prototype-does-not-do)
4. [Why Local-First](#why-local-first)
5. [Stakeholder-Driven Design](#stakeholder-driven-design)
6. [Core Features](#core-features)
7. [Five-Minute Evaluator Demo](#five-minute-evaluator-demo)
8. [Architecture Overview](#architecture-overview)
9. [Tech Stack](#tech-stack)
10. [Validation Engine](#validation-engine)
11. [Legal Corpus and Source-Backed Criteria](#legal-corpus-and-source-backed-criteria)
12. [Data and Fixture Strategy](#data-and-fixture-strategy)
13. [Repository Structure](#repository-structure)
14. [Quick Start: Local Development](#quick-start-local-development)
15. [Docker Quick Start](#docker-quick-start)
16. [Deployment to `www.labelsontap.ai`](#deployment-to-wwwlabelsontapai)
17. [Using the Application](#using-the-application)
18. [Batch Manifest Format](#batch-manifest-format)
19. [API Overview](#api-overview)
20. [Security and Privacy](#security-and-privacy)
21. [Accessibility and Reviewer UX](#accessibility-and-reviewer-ux)
22. [Performance Expectations](#performance-expectations)
23. [Testing](#testing)
24. [Troubleshooting](#troubleshooting)
25. [Trade-Offs and Limitations](#trade-offs-and-limitations)
26. [Future Production Hardening](#future-production-hardening)
27. [Primary Public Sources](#primary-public-sources)
28. [License / Use](#license--use)

---

## Executive Summary

The Alcohol and Tobacco Tax and Trade Bureau (TTB) label review workflow contains a large amount of routine verification work: matching the brand name on the application to the brand name on the label, confirming alcohol content, verifying net contents, checking that required warnings are present, and identifying obvious formatting or terminology problems. The stakeholder discovery notes for this take-home exercise repeatedly point to the same product opportunity: **use automation to reduce repetitive visual matching without replacing expert regulatory judgment.**

**Labels On Tap** is a local-first prototype that compares uploaded beverage-alcohol label artwork against expected COLA application fields. It uses local OCR, deterministic rules, fuzzy matching, image/upload preflight checks, and source-backed explanations to return one of three outcomes:

| Result | Meaning |
|---|---|
| **Pass** | The label appears consistent with the provided application fields and implemented source-backed checks. |
| **Needs Review** | The tool found ambiguity, low OCR confidence, subjective legal risk, or a visual condition that should be checked by a human specialist. |
| **Fail** | The tool found a clear deterministic mismatch or source-backed preflight issue with adequate evidence. |

The prototype is intentionally **not** a general-purpose chatbot, cloud OCR wrapper, or final legal approval system. It is a reviewer-support tool designed to be fast, explainable, and safe under federal infrastructure constraints.

The core product principle is:

> **Fail deterministic source-backed issues. Pass only when OCR and matching are confident. Route ambiguity, low-quality images, and subjective legal risks to Needs Review. Always show the reviewer why.**

---

## What This Prototype Does

Labels On Tap helps a reviewer answer questions like:

- Does the label artwork appear to match the expected application fields?
- Does the brand name on the label match the brand name in the application?
- Does the alcohol-content statement appear to match the expected value?
- Does the label use prohibited alcohol-content shorthand such as `ABV` where a source-backed rule says it should not?
- Is the required government warning present?
- Does the warning text match the canonical statutory language?
- Is the heading written as `GOVERNMENT WARNING:` in all caps?
- Does a malt beverage label appear to use an incorrect intermediate net-contents expression such as `16 fl. oz.` instead of `1 Pint`?
- Is the uploaded file a valid label-image format?
- Is the image too blurry, compressed, low-confidence, or otherwise risky for automated OCR?
- Does the label contain source-backed risk signals that should be routed to human review?

The application is designed around two upload modes:

1. **Single Label Review** — enter application fields and upload one label image.
2. **Batch Review** — upload a manifest plus multiple label images and watch results populate asynchronously.

The reviewer interface is designed to be deliberately simple: upload, process, review results, inspect evidence, export CSV.

---

## What This Prototype Does Not Do

Labels On Tap is not a replacement for TTB label specialists, legal counsel, or final agency review.

It does **not**:

- Issue final COLA approvals.
- Issue final legal rejections.
- Integrate directly with COLAs Online.
- Scrape or enumerate private COLAs Online data.
- Train on confidential rejected or Needs Correction applications.
- Call hosted ML endpoints such as OpenAI, Anthropic, Google Cloud Vision, Azure AI Vision, AWS Textract, or hosted VLMs.
- Claim that every federal, state, or product-specific labeling rule is implemented in the sprint MVP.
- Guarantee regulatory compliance from a flattened raster image.

The app provides **source-backed preflight and triage results**. A production federal implementation would require formal security review, authorization, data-retention policy, identity integration, audit logging, and deeper legal validation.

---

## Why Local-First

The stakeholder notes make local-first architecture a hard requirement, not an aesthetic preference.

The prior vendor pilot reportedly failed in part because hosted ML endpoints were blocked by Treasury network controls. The notes also emphasize that slow automation is worse than no automation: agents abandoned a prior tool when processing took 30–40 seconds per label.

Labels On Tap therefore avoids cloud ML APIs and large VLMs at runtime. OCR and validation run inside the deployed application environment. In this README, **local-first** means:

```text
No hosted OCR API
No hosted VLM API
No outbound ML inference endpoint
No label image sent to OpenAI, Google Vision, Azure AI Vision, Anthropic, or AWS Textract
OCR and rules execute inside the app server/container
```

A cloud VM may still host the application. The key distinction is that the VM runs the OCR model and validation code itself; it does not relay label images to a hosted AI service.

---

## Stakeholder-Driven Design

The take-home prompt includes four stakeholder voices. The architecture is deliberately mapped to those needs.

### Sarah Chen — Deputy Director of Label Compliance

Sarah’s pain point is workflow load. Agents spend substantial time performing routine label/application matching. She also emphasized that slow automation will not be adopted and that importer batches can contain hundreds of labels.

**Product response:**

- Fast single-label processing target.
- Batch upload with progress feedback.
- Simple UI with obvious actions.
- Pass / Needs Review / Fail triage.
- CSV export for reviewer follow-up.

### Marcus Williams — IT / Infrastructure

Marcus’s concern is infrastructure reality. Hosted ML endpoints may be blocked, and direct COLA-system integration is not in scope for a prototype.

**Product response:**

- Local OCR/runtime inference.
- Standalone FastAPI app.
- Dockerized deployment.
- No hosted ML APIs.
- No direct COLAs Online integration.
- Legal corpus and source-backed rule registry for maintainable expansion.

### Dave Morrison — Senior Compliance Agent

Dave’s concern is nuance. A tool that fails harmless typographic differences will make review harder, not easier. For example, `STONE'S THROW` and `Stone's Throw` should not be treated as a meaningful mismatch.

**Product response:**

- Fuzzy matching for reviewer-judgment fields.
- Normalization of case, spacing, punctuation, and apostrophes.
- Ambiguous fuzzy scores route to Needs Review.
- Strict checks are reserved for deterministic requirements.

### Jenny Park — Junior Compliance Agent

Jenny’s concern is exactness. The government warning must be word-for-word correct. `GOVERNMENT WARNING:` must be capitalized, and formatting matters.

**Product response:**

- Canonical government-warning text check.
- Strict all-caps heading check.
- Clear OCR evidence display.
- Boldness/typography routed to Needs Review unless reliably verifiable.
- Low-confidence warning OCR routes to Needs Review instead of false Pass.

---

## Core Features

### 1. Local OCR Extraction

The OCR layer extracts:

- recognized text,
- confidence scores,
- bounding boxes or polygons where available,
- normalized full-text output,
- timing metrics.

The current architecture is designed around `docTR` as the primary OCR candidate because the research package prioritizes local CPU inference, bounding boxes, confidence scores, and lower deployment friction than heavier OCR/VLM alternatives. The OCR adapter is intentionally isolated so another engine can be swapped in if benchmark results or deployment behavior require it.

### 2. Dual-Standard Validation

The engine separates fields into two categories.

**Fuzzy fields:**

- brand name,
- fanciful name,
- class/type,
- producer/bottler name,
- address,
- country of origin.

These fields tolerate casing, spacing, punctuation, and OCR noise.

**Strict fields:**

- government warning text,
- government warning heading capitalization,
- prohibited alcohol-content terminology,
- malt beverage net-contents conversion traps,
- image/upload preflight rules.

These rules are deterministic when the source and OCR evidence are strong.

### 3. Source-Backed Explanations

Each flagged rule should show:

- result status,
- rule ID,
- source-backed rationale,
- observed evidence,
- expected value or wording,
- reviewer action.

Example:

```text
Fail: Government warning text mismatch

Observed:
"... operate machinery and may cause health problems."

Expected:
"... operate machinery, and may cause health problems."

Why this matters:
The government warning must match the canonical statutory wording.

Reviewer action:
Correct the warning text and resubmit/recheck.
```

### 4. Batch Processing

Batch mode is designed for high-volume importer workflows. The UI should show progress immediately after upload:

```text
Batch accepted.
Processing 0 / 243 labels.
Completed labels will appear as they finish.
```

The app should update counts as results finish:

```text
Processed: 37 / 243
Pass: 24
Needs Review: 9
Fail: 4
```

### 5. One-Click Evaluator Demos

The evaluator should not need to find sample labels, build a manifest, or understand TTB rules before seeing value.

The app should include demo buttons such as:

- **Run Clean Label Demo**
- **Run Government Warning Failure Demo**
- **Run ABV Failure Demo**
- **Run Malt Net Contents Failure Demo**
- **Run Batch Demo**

These demos should load pre-baked fixtures, run the verification engine, and show evidence-backed results.

---

## Five-Minute Evaluator Demo

A reviewer should be able to evaluate the product quickly.

### Demo 1 — Clean Label Pass

1. Open `https://www.labelsontap.ai`.
2. Click **Run Clean Label Demo**.
3. Confirm the app returns **Pass**.
4. Open details and inspect the matched brand, alcohol content, net contents, and warning evidence.

### Demo 2 — Government Warning Failure

1. Click **Run Warning Failure Demo**.
2. Confirm the app returns **Fail**.
3. Inspect the expected vs observed warning text.
4. Confirm the UI explains the source-backed reason.

### Demo 3 — ABV Terminology Failure

1. Click **Run ABV Failure Demo**.
2. Confirm the app flags prohibited `ABV` wording.
3. Inspect the suggested acceptable wording pattern.

### Demo 4 — Malt Net Contents Failure

1. Click **Run Malt Net Contents Failure Demo**.
2. Confirm the app flags `16 fl. oz.` for malt beverage net contents when the source-backed rule expects `1 Pint`.

### Demo 5 — Import Origin Pass

1. Click **Run Import Origin Demo**.
2. Confirm the imported wine fixture returns **Pass** for `COUNTRY_OF_ORIGIN_MATCH`.
3. Open details and inspect the application country-of-origin field and OCR evidence.

### Demo 6 — Batch Processing

1. Click **Run Batch Demo** or upload a manifest and multiple images.
2. Watch the progress panel update.
3. Filter to Fail or Needs Review.
4. Export CSV.

This demo sequence shows the most important qualities: speed, clarity, local-first architecture, source-backed explanations, strict and fuzzy logic, and batch triage.

---

## Architecture Overview

```text
Browser
  |
  | Upload one label or a batch manifest + images
  v
FastAPI Web App
  |
  | Save job metadata and uploads under local job directory
  | Start OCR/validation work
  v
Local OCR Adapter
  |
  | docTR / CPU OCR
  | text + confidence + geometry
  v
Validation Engine
  |
  | image preflight
  | fuzzy field matching
  | strict warning checks
  | alcohol/net contents checks
  | risk-review checks
  v
Filesystem Job Store
  |
  | manifest.json
  | result JSON files
  | evidence snippets/crops when available
  | CSV export
  v
HTMX/Jinja Results UI
  |
  | Progress polling
  | Pass / Needs Review / Fail table
  | Source-backed detail page
```

### Why Filesystem Job Storage

For a six-day prototype, filesystem JSON storage is simpler and safer than introducing a database concurrency problem. Each processed label writes one result file under its job folder.

Example:

```text
data/jobs/{job_id}/
  manifest.json
  uploads/
    label_001.png
    label_002.png
  results/
    label_001.json
    label_002.json
  evidence/
    label_001_warning.txt
  exports/
    results.csv
```

This keeps the app easy to debug, avoids multi-writer SQLite issues, and is sufficient for a public prototype. A production system should use PostgreSQL or an approved enterprise data store with audit and retention controls.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI | Python-native, strong upload support, simple routing, good docs, easy Docker deployment. |
| Templates | Jinja2 | Server-rendered UI avoids React build complexity. |
| Interactivity | HTMX | Lightweight polling and partial updates for batch progress. |
| Styling | Local CSS / USWDS-inspired patterns | No CDN dependency; supports accessible, simple reviewer UI. |
| OCR | docTR adapter | Local OCR candidate with text localization and recognition. Adapter design allows future engine swaps. |
| Image handling | OpenCV-headless + Pillow | File validation, image loading, preflight checks, optional evidence crops. |
| Matching | RapidFuzz | Fast fuzzy matching for human-judgment fields. |
| Validation | Python regex + numeric parsers | Deterministic source-backed checks. |
| Job store | Filesystem JSON | Sprint-safe, observable, avoids database lock risk. |
| Deployment | Docker + Caddy | Containerized app with straightforward HTTPS reverse proxy. |
| Domain | `www.labelsontap.ai` | Public evaluator URL; apex redirects to `www`. |

---

## Validation Engine

### Verdict Model

The validation engine never returns a single unexplained score. It returns a checklist of rule results and an overall verdict.

```json
{
  "overall_verdict": "fail",
  "filename": "beer_16_fl_oz_only.png",
  "processing_ms": 3820,
  "checks": [
    {
      "rule_id": "MALT_NET_CONTENTS_16OZ_PINT",
      "verdict": "fail",
      "field": "net_contents",
      "expected": "1 Pint",
      "observed": "16 fl. oz.",
      "message": "Malt beverage net contents may need to be expressed as 1 Pint.",
      "source_refs": ["SRC_27_CFR_PART_7", "SRC_TTB_MALT_NET_CONTENTS_GUIDANCE"]
    }
  ]
}
```

### Active MVP Rule Families

The sprint MVP focuses on the highest-value rules that are deterministic, demoable, and aligned to stakeholder needs.

| Rule Family | Example Rule IDs | Verdict Behavior |
|---|---|---|
| Brand/application matching | `FORM_BRAND_MATCHES_LABEL` | Pass / Needs Review / Fail based on fuzzy score and OCR confidence. |
| Country of origin | `COUNTRY_OF_ORIGIN_MATCH` | Checks import-origin field where provided. |
| Alcohol content | `ALCOHOL_VALUE_MATCH`, `PROOF_EQUIVALENCE` | Numeric parser and proof equivalence where applicable. |
| ABV terminology | `ALCOHOL_ABV_PROHIBITED` | Fail when source-backed prohibited wording is detected with high confidence. |
| Government warning | `GOV_WARNING_EXACT_TEXT`, `GOV_WARNING_HEADER_CAPS` | Strict text and capitalization checks. |
| Warning typography | `GOV_WARNING_HEADER_BOLD_REVIEW` | Needs Review unless reliable measurement is implemented. |
| Malt net contents | `MALT_NET_CONTENTS_16OZ_PINT` | Fail for deterministic conversion trap where product type is malt beverage. |
| Upload preflight | `IMAGE_FORMAT_ALLOWED_TYPES`, `UPLOAD_SIZE_LIMIT` | Reject or flag unsafe/unsupported files. |
| Risk review | `HEALTH_CLAIM_RISK`, `WINE_SEMI_GENERIC_NAME_DETECTED`, `ABSINTHE_TERM_DETECTED` | Needs Review; does not issue final legal conclusion. |

### Fuzzy Matching

Fuzzy matching is used where reviewer judgment is appropriate.

Normalization includes:

- case folding,
- whitespace collapsing,
- curly/straight apostrophe normalization,
- punctuation normalization,
- token-window comparison against OCR text.

Example:

```text
Application: Stone's Throw
Label OCR:   STONE'S THROW
Result:      Pass
Reason:      Same brand after normalization.
```

### Strict Matching

Strict matching is used where the rule is deterministic.

Example:

```text
Expected: GOVERNMENT WARNING:
Observed: Government Warning:
Result:   Fail
Reason:   Required heading capitalization not met.
```

### Needs Review

Needs Review is intentional. It prevents false certainty when:

- OCR confidence is low,
- the label is blurry or poorly cropped,
- a warning block cannot be isolated,
- typography cannot be reliably measured,
- the issue requires legal context,
- the source is a case study or risk heuristic rather than a deterministic rule.

---

## Legal Corpus and Source-Backed Criteria

The repository includes a structured research and legal-corpus system. Its purpose is to make rule decisions traceable.

```text
Source
  → Extracted Requirement
  → Rule Matrix Row
  → App Rule
  → Fixture/Test
  → UI Explanation
```

Expected files:

```text
research/legal-corpus/
  README.md
  source-ledger.json
  source-ledger.md
  source-confidence.md
  federal-statutes.md
  cfr-regulations.md
  ttb-guidance-and-circulars.md
  court-cases-and-precedents.md
  public-data-boundaries.md
  excerpts/
  forms/
  matrices/
    source-backed-criteria.json
    source-backed-criteria.md
    source-backed-criteria.csv
    fixture-map.md
  reports/
```

### Source Confidence Policy

| Tier | Description | Rule Behavior |
|---|---|---|
| Tier 1 | Official statutes, CFR/eCFR, TTB guidance, TTB forms, TTB circulars, federal opinions | Deterministic rules may Fail/Pass when evidence is strong. |
| Tier 2 | Public legal analysis, public case studies, compliance-provider analysis | Usually Needs Review. |
| Tier 3 | OSINT synthesis, forum anecdotes, synthetic fixture inspiration | Needs Review or documentation only. |

### Corpus Bootstrap

The legal corpus can be scaffolded with:

```bash
python scripts/bootstrap_legal_corpus.py
python scripts/validate_legal_corpus.py
```

The validation script checks that source-backed rules reference known sources and that non-official or subjective rules do not incorrectly default to hard Fail.

---

## Data and Fixture Strategy

The data strategy is designed to be lawful, reproducible, and honest about public-data limits.

### Public Positive Fixtures

The TTB Public COLA Registry can be used for public approved, expired, surrendered, and revoked COLA examples. These records provide realistic artwork, typography, and metadata for OCR testing.

### Rejected / Needs Correction Data

Rejected and returned applications are not treated as publicly available training data. The public registry is not used as a source of confidential failed applications.

### Synthetic Negative Fixtures

Because true rejected/Needs Correction data is not generally available publicly, the project uses source-backed synthetic mutations to create controlled negative test cases.

Examples:

```text
warning_missing_machinery_comma.png
warning_title_case_heading.png
beer_5_percent_abv.png
beer_16_fl_oz_only.png
brand_mismatch.png
blurry_warning_needs_review.png
health_claim_needs_review.png
semi_generic_champagne_needs_review.png
```

Each synthetic fixture should map to:

- rule IDs,
- source references,
- mutation summary,
- expected verdict,
- demo usage.

Fixture provenance belongs in:

```text
data/source-maps/fixture-provenance.json
```

### Demo and Test Fixture Generation

Required demo/test data is generated by the repository bootstrap, not downloaded manually:

```bash
python scripts/bootstrap_project.py
```

The bootstrap writes deterministic synthetic label images, application payloads, OCR-text ground truth, expected results, manifests, and fixture provenance:

```text
data/fixtures/demo/
data/source-maps/fixture-provenance.json
data/source-maps/expected-results.json
```

Public approved COLA examples may be curated later for OCR realism, but the core tests and one-click demos use generated fixtures so they remain reproducible, offline-safe, and independent of registry scraping.

See [docs/fixture-generation.md](docs/fixture-generation.md) for the detailed fixture contract.

---

## Repository Structure

Recommended final structure:

```text
Labels-On-Tap/
  README.md
  PRD.md
  TASKS.md
  ARCHITECTURE.md
  TRADEOFFS.md
  DEMO_SCRIPT.md
  PERSONALITIES.md

  app/
    main.py
    config.py
    routes/
      ui.py
      jobs.py
      health.py
    schemas/
      cola_application.py
      ocr.py
      results.py
      manifest.py
    services/
      ocr/
        base.py
        doctr_engine.py
      preflight/
        file_signature.py
        upload_policy.py
        image_quality.py
      job_store.py
      csv_export.py
    rules/
      field_matching.py
      strict_warning.py
      alcohol_terms.py
      net_contents.py
      health_claims.py
      wine/
        semi_generic_names.py
      spirits/
        absinthe_thujone.py
    templates/
      base.html
      index.html
      job.html
      item_detail.html
      partials/
        job_status.html
        result_table.html
    static/
      app.css

  docs/
    architecture.md
    validation-rules.md
    data-strategy.md
    fixture-generation.md
    security-and-privacy.md
    accessibility.md
    deployment.md
    performance.md
    tradeoffs.md

  research/
    legal-corpus/
      source-ledger.json
      source-ledger.md
      matrices/
      excerpts/
      forms/
      reports/

  data/
    fixtures/
      demo/
      synthetic/
      manifests/
    source-maps/
    jobs/

  scripts/
    bootstrap_project.py
    bootstrap_legal_corpus.py
    seed_demo_fixtures.py
    validate_legal_corpus.py
    benchmark_ocr.py

  Dockerfile
  docker-compose.yml
  Caddyfile
  requirements.txt
  .env.example
  .gitignore
```

---

## Quick Start: Local Development

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

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Expected core dependencies include:

```text
fastapi
uvicorn[standard]
jinja2
python-multipart
python-doctr[torch]
opencv-python-headless
pillow
rapidfuzz
pydantic
python-dotenv
pytest
```

For CPU-only PyTorch environments, follow the CPU wheel guidance used in the Dockerfile or PyTorch install instructions. Avoid unintentionally installing CUDA/GPU wheels on a small VM.

### 4. Bootstrap project data

```bash
python scripts/bootstrap_project.py
```

This creates or validates the legal corpus and generates deterministic demo/test fixtures under `data/fixtures/demo/`.

### 5. Run the app

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

### 6. Run tests

```bash
python scripts/bootstrap_project.py
pytest -q
```

---

## Docker Quick Start

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

### First OCR Run

The first OCR call may take longer because model weights may need to download or initialize. The deployed container should prewarm or cache OCR weights before the evaluator demo when possible.

### Example Docker Compose Services

```yaml
services:
  web:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - APP_ENV=production
      - JOB_ROOT=/app/data/jobs

  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - web

volumes:
  caddy_data:
  caddy_config:
```

---

## Deployment to `www.labelsontap.ai`

The intended deployment is an x86_64 Linux VM running Docker and Caddy.

### Recommended VM

```text
Cloud:        AWS EC2 On-Demand
Instance:     m7i.xlarge preferred, t3a.large/t3.large fallback
Architecture: x86_64
CPU/RAM:      4 vCPU / 16 GiB preferred, 2 vCPU / 8 GiB minimum fallback
Disk:         40-60 GB gp3
OS:           Ubuntu 24.04 LTS
Ports:        80 and 443 open to public internet; 22 restricted to your IP
```

### DNS

At the domain registrar or DNS provider:

```text
A record:     www.labelsontap.ai  → Elastic IP / VM public IPv4
A record:     labelsontap.ai      → Elastic IP / VM public IPv4
```

### Caddyfile

```text
www.labelsontap.ai {
    encode gzip zstd
    reverse_proxy app:8000
}

labelsontap.ai {
    redir https://www.labelsontap.ai{uri} permanent
}
```

Caddy automatically provisions and renews HTTPS certificates when both names resolve to the VM and ports 80/443 are reachable.

### Deployment Commands

```bash
ssh ubuntu@YOUR_VM_IP
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker

git clone https://github.com/AaronNHorvitz/Labels-On-Tap.git
cd Labels-On-Tap
cp .env.example .env

docker compose up --build -d
docker compose logs -f
```

### Smoke Test

After deployment:

```bash
curl -I https://www.labelsontap.ai
curl https://www.labelsontap.ai/health
```

Then open the site and run:

1. Clean Label Demo.
2. Warning Failure Demo.
3. ABV Failure Demo.
4. Batch Demo.
5. CSV export.

---

## Using the Application

### Single Label Mode

1. Open the application.
2. Choose **Single Label Review**.
3. Enter application fields:
   - product type,
   - brand name,
   - class/type,
   - alcohol content,
   - net contents,
   - country of origin if imported,
   - optional formula/SOC fields.
4. Upload a label image.
5. Click **Verify Label**.
6. Review Pass / Needs Review / Fail output.
7. Open the detail view for OCR evidence and source-backed explanation.

### Batch Mode

1. Choose **Batch Review**.
2. Upload `manifest.csv` or `manifest.json`.
3. Upload multiple label images.
4. Submit the batch.
5. Watch live progress.
6. Filter to Fail or Needs Review.
7. Export CSV.

### Supported Label Image Formats

MVP accepted label artwork:

```text
.jpg
.jpeg
.png
```

Rejected as label artwork:

```text
.pdf
.tif
.tiff
.heic
.webp
.exe
unknown / spoofed files
```

PDFs may be useful as research documents, but the reviewer app focuses on label-image verification.

---

## Batch Manifest Format

### CSV Example

```csv
filename,product_type,brand_name,fanciful_name,class_type,alcohol_content,net_contents,country_of_origin,imported,formula_id,statement_of_composition
old_tom_front.png,distilled_spirits,Old Tom Distillery,,Kentucky Straight Bourbon Whiskey,45% Alc./Vol. (90 Proof),750 mL,,false,,
beer_001.png,malt_beverage,North Fork Brewing,,India Pale Ale,5% Alc./Vol.,1 Pint,,false,,
wine_001.png,wine,Valley Ridge,,Red Wine,13.5% Alc./Vol.,750 mL,France,true,,
```

### JSON Example

```json
{
  "items": [
    {
      "filename": "old_tom_front.png",
      "application": {
        "product_type": "distilled_spirits",
        "brand_name": "Old Tom Distillery",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "country_of_origin": null,
        "imported": false,
        "formula_id": null,
        "statement_of_composition": null
      }
    }
  ]
}
```

---

## API Overview

The application is primarily a server-rendered UI, but the route design is simple and inspectable.

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Landing page and demo buttons. |
| `/health` | GET | Health check. |
| `/jobs` | POST | Create single-label or batch job. |
| `/jobs/{job_id}` | GET | Job results page. |
| `/jobs/{job_id}/status` | GET | HTMX partial for live progress. |
| `/jobs/{job_id}/items/{item_id}` | GET | Result detail page. |
| `/jobs/{job_id}/results.csv` | GET | CSV export. |
| `/demo/{scenario}` | POST/GET | Run a pre-baked evaluator demo scenario. |

### HTMX Progress Polling

The job page can poll with a simple fragment:

```html
<div
  hx-get="/jobs/{{ job_id }}/status"
  hx-trigger="load, every 2s"
  hx-swap="innerHTML">
  Loading job status...
</div>
```

---

## Security and Privacy

This is a public prototype that accepts user-uploaded files, so upload safety is treated as a first-class requirement.

### Upload Controls

The upload pipeline should implement:

- extension allowlist,
- file signature / magic-byte validation,
- maximum file-size limits,
- maximum batch-size limits,
- randomized server-side filenames,
- path traversal rejection,
- double-extension rejection,
- image decoding before OCR,
- ZIP bomb protection if archive support is enabled,
- cleanup of old jobs,
- no script execution from upload directories.

### Runtime ML Privacy

The application does not send label artwork to hosted ML APIs. OCR runs in the deployed application environment.

### Retention

For the prototype, uploaded files and results are stored only as needed for job processing, demo review, and CSV export. A production federal version would need a formal retention schedule, audit policy, and records-management controls.

### Authentication

Authentication is intentionally out of scope for the take-home prototype unless a simple demo access code is added. A production system would require identity integration, role-based access control, audit logging, and authorization review.

---

## Accessibility and Reviewer UX

The UI is designed for non-technical reviewers and older users.

Implementation principles:

- native file inputs,
- large buttons,
- visible focus states,
- keyboard-accessible forms,
- labels associated with inputs,
- high contrast status badges,
- no color-only status communication,
- clear error messages,
- ARIA-friendly progress updates where practical,
- simple linear layout,
- no hidden advanced controls.

The goal is to make the first screen obvious:

```text
Run Demo
Upload Single Label
Upload Batch
Review Results
Export CSV
```

---

## Performance Expectations

The stakeholder requirement is that single-label processing should feel fast enough for adoption. The target is approximately **5 seconds per label after OCR warmup**, depending on:

- VM CPU and memory,
- image size,
- image complexity,
- OCR model initialization,
- number of concurrent jobs,
- preprocessing cost,
- whether weights are already cached.

The app should measure and display:

```text
preflight_ms
ocr_ms
validation_ms
total_ms
avg_ocr_confidence
```

Batch mode does not mean every image completes in five seconds total. It means the user receives immediate job feedback and can review completed labels as they finish.

Performance results should be documented in:

```text
docs/performance.md
```

---

## Testing

Run all tests:

```bash
pytest -q
```

Recommended test groups:

```text
tests/test_warning_rules.py
tests/test_alcohol_terms.py
tests/test_net_contents.py
tests/test_field_matching.py
tests/test_upload_preflight.py
tests/test_legal_corpus.py
tests/test_job_store.py
tests/test_demo_scenarios.py
```

### Legal Corpus Validation

```bash
python scripts/bootstrap_project.py
```

The validator should check:

- every rule references known source IDs,
- source IDs exist in the source ledger,
- non-official Tier 2/Tier 3 rules do not default to Fail,
- fixtures map to rule IDs,
- implemented rules have fixture coverage.

---

## Troubleshooting

### First OCR run is slow

Model weights may be downloading or warming up. Run a demo once after deployment to cache and prewarm where possible.

### Docker image is large

OCR frameworks and CPU PyTorch wheels are large. Use a slim base image and avoid CUDA/GPU wheels. A multi-stage Dockerfile can reduce build artifacts, but the final runtime image still needs OCR dependencies.

### App starts but OCR fails

Check:

```bash
docker compose logs web
```

Common causes:

- missing CPU PyTorch wheel,
- docTR dependency mismatch,
- model weights not downloaded,
- insufficient RAM,
- permissions issue in model cache directory.

### Domain does not load

Check:

```bash
dig labelsontap.ai
dig www.labelsontap.ai
curl -I http://labelsontap.ai
curl -I https://www.labelsontap.ai
sudo docker compose ps
sudo docker compose logs caddy
```

Ensure:

- DNS A record points to VM public IP,
- ports 80 and 443 are open,
- Caddyfile contains the correct domain,
- the web container is reachable from Caddy.

### Batch progress does not update

Check:

- job directory exists under `data/jobs/`,
- result JSON files are being written,
- `/jobs/{job_id}/status` returns HTML,
- HTMX script is loaded,
- browser console has no blocked resource errors.

---

## Trade-Offs and Limitations

### 1. Decision support, not final agency action

The system returns source-backed preflight results. It does not approve or reject labels on behalf of TTB.

### 2. Local OCR over cloud OCR

Hosted OCR APIs may be more accurate in some cases, but they violate the local-first runtime requirement and firewall constraints. This prototype keeps inference inside the app environment.

### 3. docTR selected as primary OCR candidate

docTR is selected because the research package prioritizes CPU-first local inference, OCR geometry, confidence scores, and Docker deployability. The OCR adapter remains isolated so another engine can be substituted if benchmark or deployment results warrant.

### 4. Boldness and type-size checks are limited

The app strictly validates warning text and all-caps heading. Font weight, physical type size, and character-density checks are difficult to verify reliably from arbitrary raster images without trustworthy DPI, scale, and image quality. These checks route to Needs Review unless implemented with reliable evidence.

### 5. No direct COLAs Online integration

The prototype is standalone. It does not submit applications, retrieve private applications, or modify COLA records.

### 6. No private rejected-label dataset

Rejected and Needs Correction applications are not treated as public training data. Negative fixtures are synthetic and source-backed.

### 7. No production auth/audit/retention

Production deployment would require identity, audit logging, formal data retention, ATO/security review, and agency-approved records handling.

### 8. No legal-advice guarantee

The app may identify source-backed risk signals, but legal interpretation remains a human/legal function.

---

## Future Production Hardening

A production-grade federal system would need:

- identity provider integration,
- role-based access control,
- audit trails,
- immutable review logs,
- approved retention policy,
- full Section 508 review,
- formal threat model,
- vulnerability scanning,
- software bill of materials,
- signed container images,
- secrets management,
- centralized logging,
- PostgreSQL or approved enterprise data store,
- integration with COLAs Online or internal systems,
- broader rule coverage across Parts 4, 5, 7, 9, 13, and 16,
- official legal review of rule interpretations,
- full performance benchmarking under realistic batch sizes.

---

## Primary Public Sources

The repository legal corpus stores source IDs and extracted requirements. The most important public sources include:

- TTB Public COLA Registry: https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry
- TTB guidance on using the COLA Registry: https://www.ttb.gov/public-information/news/using-cola-registry-search-certificates
- TTB COLAs Online / label image FAQs: https://www.ttb.gov/faqs/colas-and-formulas-online-faqs/print
- TTB Form 5100.31: https://www.ttb.gov/system/files/images/pdfs/forms/f510031.pdf
- 27 CFR Part 4 — Wine: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4
- 27 CFR Part 5 — Distilled Spirits: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5
- 27 CFR Part 7 — Malt Beverages: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7
- 27 CFR Part 13 — Labeling Proceedings: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-13
- 27 CFR Part 16 — Government Health Warning: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
- TTB malt beverage alcohol-content guidance: https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-alcohol-content
- TTB Industry Circular 2006-01 — semi-generic wine names / Retsina: https://www.ttb.gov/public-information/industry-circulars/archives/2006/06-01
- TTB Industry Circular 2007-05 — absinthe / thujone policy: https://www.ttb.gov/public-information/industry-circulars/archives/2007/07-05
- docTR installation documentation: https://mindee.github.io/doctr/getting_started/installing.html
- FastAPI file upload documentation: https://fastapi.tiangolo.com/tutorial/request-files/
- HTMX trigger documentation: https://htmx.org/attributes/hx-trigger/
- Caddy automatic HTTPS documentation: https://caddyserver.com/docs/automatic-https
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

---

## License / Use

This repository is a take-home prototype created for evaluation. It is not an official TTB system, not an official Treasury product, and not legal advice.

Labels On Tap is intended to demonstrate:

- product reasoning,
- stakeholder alignment,
- local-first AI architecture,
- OCR and deterministic validation,
- source-backed rule design,
- secure upload handling,
- accessible reviewer UX,
- deployable prototype engineering.
