# TASKS.md — Final Sprint Command Center

**Project:** Labels On Tap
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Canonical deployment URL:** `https://www.labelsontap.ai`
**Deadline:** Monday afternoon, May 4, 2026
**Sprint target:** Stakeholder-complete prototype that automates the COLA-style application-data-to-label-artwork comparison workflow described in the interviews.
**Status as of May 1:** A working repo and deployed public app exist. The remaining risk is product completeness against Sarah Chen and Marcus Williams's interview requirements, not basic deployment.

The highest priority is now a working deployed demo that visibly matches the agency workflow: upload COLA-style application data, upload label artwork, compare application fields against OCR text, triage mismatches, and export reviewer-ready results.

Do not use the deadline or existing deployment as a reason to waive interview-derived requirements. Direct COLA integration remains out of scope, but a COLA-shaped standalone proof of concept is in scope.

---

## Current Truth

- [x] Canonical URL is `https://www.labelsontap.ai`.
- [x] Public deployed app is live at `https://www.labelsontap.ai`.
- [x] `https://labelsontap.ai` redirects to `https://www.labelsontap.ai`.
- [x] Runtime architecture is FastAPI + Jinja2/HTMX + local CSS.
- [x] OCR architecture is local docTR adapter with fixture OCR fallback.
- [x] Storage architecture is filesystem JSON job/result store.
- [x] Deployment architecture is Docker Compose + Caddy on an x86_64 cloud VM.
- [x] Current public deployment is AWS Lightsail Ubuntu VM with static IP, Docker Compose, and Caddy.
- [x] Current deployment target remains AWS for submission; Azure is a portability/documentation path if time allows.
- [x] Public health smoke passed at `https://www.labelsontap.ai/health`.
- [x] Apex redirect smoke passed for `https://labelsontap.ai`.
- [x] FastAPI app scaffold is implemented.
- [x] Home page, health route, demo routes, job pages, detail pages, and CSV export routes exist.
- [x] Single-label upload route exists.
- [x] Manual manifest-backed batch upload route exists.
- [x] `country_of_origin` and `imported` are first-class application fields.
- [x] Country-of-origin fields are included in the single-label route.
- [x] Core validation rules are implemented for brand match, warning text, warning caps, warning typography review, ABV shorthand, malt net contents, OCR confidence, and country of origin.
- [x] Demo fixtures/data scaffold exists.
- [x] `imported_country_origin_pass.*` fixture set exists.
- [x] Batch fixture manifest exists.
- [x] Expanded 12-row demo fixture set exists.
- [x] `scripts/bootstrap_project.py` exists.
- [x] `scripts/seed_demo_fixtures.py` exists.
- [x] Tests scaffold exists.
- [x] Last known local test run: `pytest -q` passed with 45 tests.
- [x] `requirements.txt` exists.
- [x] `Dockerfile` exists.
- [x] `docker-compose.yml` exists.
- [x] `Caddyfile` exists and uses `www.labelsontap.ai` as canonical host.
- [x] `docs/deployment.md` exists.
- [x] `docs/performance.md` exists.
- [x] `docs/tradeoffs.md` exists.
- [x] `docs/public-cola-etl.md` exists.
- [x] `TASKS.md` is committed.
- [x] Root `TRADEOFFS.md` exists.
- [x] Root `TRADEOFFS.md` is committed.
- [x] Root `DEMO_SCRIPT.md` exists.
- [x] Root `DEMO_SCRIPT.md` is committed.

---

## Non-Negotiable Requirements

This is the consolidated Phase 1 requirements list. If these are not covered, the prototype is still incomplete even though the repo and public app exist.

### Step 1 - Investigate COLAs Online Data Structure

- [ ] Confirm the current COLAs Online create-application flow from official TTB docs and screenshots.
- [ ] Confirm Step 1 Application Type fields and conditional options.
- [ ] Confirm Step 2 COLA Information fields and product-specific fields.
- [ ] Confirm Step 3 Upload Labels image/attachment behavior.
- [ ] Confirm whether public registry printable records expose enough application data and label images to derive realistic fixtures.
- [ ] Treat public `publicFormDisplay` HTML as a first-class input source when available, not only screenshots.
- [ ] Extract structured application fields from public form HTML labels/data cells.
- [ ] Identify all `/colasonline/publicViewAttachment.do?...&filetype=l` label image tags and ignore non-label images such as signatures.
- [ ] Store attachment metadata for every label image: source URL, filename, image type, stated dimensions, alt text, and panel order.
- [ ] Build a field map from COLAs Online / TTB F 5100.31 concepts to the app's `ColaApplication` schema.
- [ ] Document the prototype ingestion boundary: no direct authenticated COLAs Online integration, but standalone COLA-style application export plus attached label artwork.

### Step 1A - Local Public COLA Data Workspace

Create the public-registry ETL and database locally first. Do not change the AWS deployment until the local data contract, parser, fixtures, and tests are working.

Use this gitignored local workspace:

```text
data/work/
  public-cola/
    raw/
      search-results/
      forms/
      images/
    parsed/
      applications/
      ocr/
    registry.sqlite
  local-photo-benchmark/
    raw/
    normalized/
    ocr/
    synthetic-applications/
    expected-results/
```

Use this committed curated-fixture export path:

```text
data/fixtures/public-cola/
  README.md
  <ttb_id>/
    source.html
    application.json
    labels/
    expected.json
    provenance.json
```

- [x] Add local ETL scripts for public registry search-result CSV imports, public form HTML fetches, form parsing, label image download, and curated fixture export.
- [ ] Store bulk/raw public registry pulls, local OCR output, and SQLite data only under `data/work/`.
- [ ] Store local phone-photo benchmark data only under `data/work/local-photo-benchmark/`.
- [x] Keep `data/work/` out of git.
- [x] Use SQLite for the local ETL/index database; do not store image blobs in SQLite.
- [x] Store image files on disk and image/application metadata in SQLite.
- [ ] Export a small curated set of official public COLA fixtures into `data/fixtures/public-cola/` with provenance.
- [ ] Runtime app and tests must use committed fixtures or user uploads, not live scraping.
- [ ] Redeploy AWS only after local parser/fixture/test changes pass locally.
- [ ] Keep Azure migration optional unless AWS becomes a blocker; document Azure portability if time allows.

### Step 2 - Phase 1 Rejection / Needs Correction Coverage

- [ ] Treat [PHASE1_REJECTION.md](PHASE1_REJECTION.md) as the complete Phase 1 screen-out checklist.
- [ ] Create test data for every item in `PHASE1_REJECTION.md`.
- [ ] Each Phase 1 case must include COLA-style application data, at least one label image, expected result JSON, OCR text/ground truth where appropriate, and provenance.
- [ ] Keep synthetic negative data for mismatch/rejection cases that are not available as public registry data.
- [ ] Use public registry-derived data only with recorded status and source provenance.

### Step 3 - Image Data And OCR

- [ ] Treat image data as mandatory, not optional decoration.
- [ ] Support front/back/multi-panel label artwork for one application where applicable.
- [ ] OCR each attached label image separately and preserve panel-level evidence.
- [ ] Aggregate OCR across all label panels when comparing application fields to label artwork.
- [ ] Support curved, rotated, or circular label text by attempting OCR first, then routing low-confidence/partial extraction to Needs Review.
- [ ] Add a local-photo benchmark workflow for phone photos: strip EXIF, normalize orientation, resize, run OCR, save OCR confidence/timing, and keep raw photos out of git.
- [ ] Store local phone photos and derived OCR artifacts under `data/work/local-photo-benchmark/`.
- [ ] Benchmark OCR on real phone label photos.
- [ ] Add image preprocessing for orientation, size, and readability before OCR.
- [ ] Add image-quality checks for blur, low contrast, glare/lighting, low resolution, and skew/angle where practical.
- [ ] Keep OCR local/self-hosted; do not use hosted OCR, hosted VLM, or cloud ML APIs at runtime.

### Step 4 - Five-Second Per-Label Target

- [ ] Measure deployed per-label processing time on AWS Lightsail.
- [ ] Track OCR time separately from preprocessing and rule evaluation.
- [ ] Record p50 and p95 per-label timings in `docs/performance.md`.
- [ ] Target useful per-label feedback in approximately 5 seconds after OCR warmup.
- [ ] If docTR cannot meet the target on realistic images, evaluate a faster local OCR adapter or a two-stage local OCR path.
- [ ] For 200-300 label batches, show immediate progress and completed-item results; do not imply the whole batch completes in 5 seconds.

### Step 5 - Reviewer-Ready Output

- [ ] Output must show application ID, image filename, field/rule, expected application value, observed label evidence, verdict, reviewer action, OCR source, and confidence.
- [ ] CSV export must be useful as a batch mismatch report, not only a compact summary.
- [ ] UI wording must describe "application data" and "label artwork" in plain reviewer language.

---

## Interview-Derived Product Gap List

This section is the authoritative requirements gap list. It is derived from Sarah Chen's and Marcus Williams's interview notes, not from what is currently convenient to build.

### P0 Sarah Chen Workflow Gaps

Sarah's core process is:

```text
agent opens COLA application data
  + agent reviews submitted label artwork
  -> agent verifies that the label matches the application
```

Current app risk: the prototype has strong compliance-rule demos, but it must more visibly automate the routine application-record-to-label-artwork matching Sarah described.

- [ ] Reframe the batch input as a **COLA-style application data file** plus label artwork, not a generic manifest.
- [ ] Add first-class `application_id` / `cola_id` traceability to schema, fixtures, batch input, job manifest, item detail, and CSV export.
- [ ] Add applicant, permittee, bottler, producer, or name/address fields needed to represent common COLA-style application data.
- [ ] Add `FORM_ALCOHOL_CONTENT_MATCHES_LABEL`.
- [ ] Add `FORM_CLASS_TYPE_MATCHES_LABEL`.
- [ ] Add `FORM_NET_CONTENTS_MATCHES_LABEL`.
- [ ] Add `FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL`.
- [ ] Add `FORM_FANCIFUL_NAME_MATCHES_LABEL` if `fanciful_name` remains in the application schema.
- [ ] Keep `FORM_BRAND_MATCHES_LABEL`, but present it as one field in a broader field-by-field comparison report.
- [ ] Expand result detail pages so each application field clearly shows expected value, observed OCR evidence, verdict, and reviewer action.
- [ ] Expand CSV export into a reviewer-ready mismatch report with application ID, filename, field/rule, expected, observed, verdict, evidence, reviewer action, and OCR source.
- [ ] Add fixture cases for clean application-data match, alcohol-content mismatch, class/type mismatch, net-contents mismatch, bottler/address missing, and mixed batch triage.
- [ ] Add test data coverage for every Phase 1 rejection / Needs Correction reason in `PHASE1_REJECTION.md`.
- [ ] Add a distilled spirits sample fixture modeled after the prompt's `OLD TOM DISTILLERY` example.
- [ ] Add wine, malt beverage, and distilled spirits coverage so product-type differences are visible.
- [ ] Add a 200-300 row synthetic batch generator or fixture-backed batch proof to address Sarah's peak-season importer scenario.
- [ ] Add automated test coverage for the large synthetic batch path.
- [ ] Improve batch progress/status behavior so the UI feels responsive for large jobs, even when full completion takes longer.
- [ ] Measure and document per-label timing on the deployed VM, with special attention to Sarah's approximately 5-second adoption threshold.
- [ ] Improve UI copy so older/nontechnical agents see simple workflow language such as "Application data file" and "Label artwork files" instead of unexplained technical terms.

### P0 Marcus Williams Architecture Gaps

Marcus's core constraints are:

```text
standalone proof of concept
no direct COLA integration
government network constraints
no hosted ML/OCR dependency
PII and retention awareness
future procurement signal
Azure infrastructure context
```

Current app risk: AWS deployment proves public availability, but Marcus explicitly hints that Azure compatibility, restricted-network behavior, and production-security posture matter. Keep AWS as the live submission host unless it becomes a blocker; make Azure a documented portability path, not a Friday-night migration.

- [ ] Keep the current public deployment on AWS Lightsail for the take-home submission.
- [ ] Add Azure deployment documentation/path if time allows because Marcus says current infrastructure is on Azure.
- [ ] Document that the current AWS deployment is for evaluation convenience and that the container stack is cloud-portable to Azure VM or Azure Container Apps.
- [ ] Ensure runtime architecture is not AWS-specific.
- [ ] Add restricted-network runtime posture: no hosted ML/OCR calls, no external model endpoints, local static assets, and no outbound AI dependency during label verification.
- [ ] Distinguish build-time dependency downloads from runtime network behavior.
- [ ] Strengthen PII/document-retention docs: prototype storage is local filesystem job storage, cleanup is available, and production needs records policy.
- [ ] Add or improve cleanup/retention workflow docs for uploaded label artifacts.
- [ ] Add future .NET/COLA integration path without implementing direct COLA integration.
- [ ] Add procurement-oriented architecture summary explaining feasibility, limitations, operations, deployment options, and trade-offs.
- [ ] Avoid any FedRAMP overclaim; explicitly state production deployment would require authorization, identity, logging, retention, and security review.

### P1 Jenny Park / Dave Morrison Supporting Gaps

Jenny and Dave fill in practical reviewer behavior: exact warning checks, non-perfect images, and tolerance for harmless formatting differences.

- [ ] Improve missing-warning handling so the app distinguishes missing, unreadable, wrong text, wrong capitalization, and typography review.
- [ ] Add explicit image-quality diagnostics for blur, low resolution, glare/contrast, or hard-to-read photos where feasible.
- [ ] Keep warning boldness conservative, but improve the reviewer-facing typography explanation and evidence.
- [ ] Extend Dave-style fuzzy matching philosophy to alcohol-content, class/type, net contents, country origin, and bottler/address formatting differences.
- [ ] Add tests for harmless formatting variants such as `45% Alc./Vol.`, `45% alcohol by volume`, and `90 Proof`.

### P2 Documentation And Submission Gaps

- [ ] Update README narrative so the product thesis is application-data-to-label-artwork verification.
- [ ] Update `DEMO_SCRIPT.md` around a COLA-style application data file plus label artwork workflow.
- [ ] Update `ARCHITECTURE.md` with COLA-shaped standalone input and Azure portability.
- [ ] Update `PRD.md` so Sarah and Marcus's hidden requirements are explicitly tracked.
- [ ] Update `docs/performance.md` with measured public VM timings.
- [ ] Add or update `docs/security.md` / privacy language around restricted networks, uploads, retention, and non-production limits.
- [ ] Add test data documentation explaining synthetic COLA-style application data, fixture OCR, and why confidential rejected applications are not used.

### Implementation Order

Build in this order so every change reinforces the agency workflow:

1. Finish the local data path contract and keep `data/work/` gitignored.
2. Investigate and document the COLAs Online data structure.
3. Build the local public COLA ETL/SQLite workspace before touching AWS.
4. Export a small curated official public COLA fixture set with source HTML, label images, parsed application JSON, expected results, and provenance.
5. Expand `ColaApplication` and `ManifestItem` into a COLA-style application record.
6. Regenerate fixtures/manifests with application IDs and bottler/producer fields.
7. Create a Phase 1 fixture coverage matrix where every item in `PHASE1_REJECTION.md` has application data, image data, expected results, and provenance.
8. Add field-by-field rules for alcohol content, class/type, net contents, bottler/producer, and fanciful name.
9. Update result detail pages and CSV export into field-level mismatch reports.
10. Add OCR benchmarking/preprocessing for real phone photos and document p50/p95 timings.
11. Add 200-300 row synthetic batch proof and tests.
12. Update README, PRD, ARCHITECTURE, DEMO_SCRIPT, performance docs, security docs, and optional Azure deployment docs.
13. Redeploy AWS and rerun public smoke/demo checks.

---

## Deployment Checklist

The first public deployment was completed on AWS Lightsail. Keep this checklist for redeploys or host rebuilds.

- [x] Launch or confirm AWS Lightsail/EC2 Ubuntu instance.
- [x] Attach or confirm static public IP.
- [x] Confirm firewall allows `80` and `443` publicly and `22` for SSH.
- [x] Point DNS A records:
  - [x] `www.labelsontap.ai` -> static public IP.
  - [x] `labelsontap.ai` -> static public IP.
- [x] SSH to server.
- [x] Install Docker and Git.
- [x] Clone `https://github.com/AaronNHorvitz/Labels-On-Tap`.
- [x] Run `cp .env.example .env`.
- [x] Run `docker compose build`.
- [x] Run `docker compose up -d`.
- [x] Run public smoke: `curl https://www.labelsontap.ai/health`.
- [x] Confirm apex redirect: `curl -I https://labelsontap.ai`.
- [ ] Open browser and run demo script.
- [ ] Update `docs/performance.md` with Docker/public measurements.

---

## Completed Deployment Hardening

- [x] Commit `TASKS.md`.
- [x] Fix README stale command: `docker compose logs web` → `docker compose logs app`.
- [x] Commit root `TRADEOFFS.md`.
- [x] Add root `DEMO_SCRIPT.md`.
- [x] Add `docs/deployment.md` if missing.
- [x] Add upload max-size enforcement.
- [x] Randomize saved upload filenames.
- [x] Preserve original upload filename as metadata only.
- [x] Validate uploaded images with Pillow after signature check.
- [x] Add upload preflight tests.
- [x] Run `pytest -q` after the upload hardening changes.
- [x] Run `docker compose build` on the deployed AWS host.
- [x] Run local health smoke test.

Acceptance commands:

```bash
python -m py_compile scripts/bootstrap_legal_corpus.py scripts/validate_legal_corpus.py scripts/bootstrap_project.py scripts/seed_demo_fixtures.py $(rg --files app -g '*.py')
python scripts/bootstrap_project.py --if-missing
python scripts/validate_legal_corpus.py
pytest -q
docker compose build
docker compose up -d
curl -H "Host: www.labelsontap.ai" http://localhost/health
docker compose down
```

Note: Docker is required for Docker checks. Docker is not available in the current local Codex workspace, so Docker verification runs on the AWS host.

---

## Should Fix Before Submission

- [x] CSV export test.
- [x] Item detail page test.
- [x] Show per-rule evidence text on the item detail page when `evidence_text` is available.
- [x] `docs/accessibility.md`.
- [ ] Update `docs/performance.md` with measured values from local Docker and public deployment.
- [x] `docs/tradeoffs.md` exists.
- [x] Add `imported_missing_country_review.*` fixture if time allows.
- [x] Public smoke test: `https://www.labelsontap.ai/health`.
- [ ] Public smoke test: clean demo returns Pass.
- [ ] Public smoke test: warning demo returns Fail.
- [ ] Public smoke test: ABV demo returns Fail.
- [ ] Public smoke test: malt net contents demo returns Fail.
- [ ] Public smoke test: country-of-origin demo returns Pass.
- [ ] Public smoke test: batch demo returns multiple results.
- [ ] Public smoke test: CSV export downloads.
- [x] Public smoke test: apex redirects to `www`.

---

## Completed Stretch Features

These were previously time-permitting items and are now implemented.

- [x] Manual multi-file batch upload using `manifest.csv` / `manifest.json` plus multiple `.jpg/.jpeg/.png` files.
- [x] Manifest parser tests for missing image, unknown filename, malformed CSV, and happy path.
- [x] CSV export coverage for batch jobs.
- [x] Item detail page coverage for expected, observed, source refs, reviewer action, and per-rule evidence text.
- [x] Add `brand_mismatch_fail.*` fixture.
- [x] Add `conflicting_country_origin_fail.*` fixture.
- [x] Add `warning_missing_block_review.*` fixture.
- [x] Add a small upload-error page or friendly error template for rejected files.
- [x] Add old-job cleanup command/script with conservative retention defaults.
- [x] Add OCR warmup note or prewarm command for deployment.

---

## Deferred Unless Interview Requirements Are Complete

- [ ] ZIP upload with safe archive limits and ZIP-bomb protection.
- [ ] Broad public COLA fixture curation beyond the first targeted official sample set.
- [ ] OCR benchmark harness across real public labels.
- [ ] Extra risk-rule demos beyond the current source-backed core.
- [ ] Thumbnails/evidence/export folders if they are not used by the UI.
- [ ] Database-backed job store.
- [ ] Authentication and audit logging.

---

## Runtime Architecture Lock

Keep this architecture stable:

- FastAPI
- Jinja2/HTMX
- local CSS
- docTR primary OCR adapter
- fixture OCR fallback for deterministic demos/tests
- filesystem job store
- Docker + Caddy
- no hosted OCR or hosted ML APIs at runtime
- no React/Vue/Angular
- no ZIP upload for MVP
- no brittle font-weight CV hard failure

---

## Do Not Do Until Interview Requirements Are Covered

- [ ] Do not add ZIP upload.
- [ ] Do not add React/Vue/Angular.
- [ ] Do not scrape private or authenticated COLA data.
- [ ] Do not replace the runtime filesystem job store with a database before interview requirements are covered.
- [ ] Do not commit `data/work/`, local SQLite databases, raw registry pulls, or raw phone-photo benchmark data.
- [ ] Do not add authentication.
- [ ] Do not chase speculative rules before the Sarah/Marcus application-data workflow is complete.
- [ ] Do not replace the fixture-backed demo path with live OCR-only behavior.

---

## Deployment Runbook

Current public host is AWS Lightsail:

```text
OS: Ubuntu Linux
Instance: 8 GB RAM / 2 vCPU Lightsail general purpose
Network: static public IPv4
Firewall:
  22 for SSH
  80 from 0.0.0.0/0
  443 from 0.0.0.0/0
DNS:
  www.labelsontap.ai A/CNAME path -> static public IP
  labelsontap.ai A record -> static public IP
Runtime:
  Docker Compose
  Caddy
  FastAPI app container
```

The stack must remain portable to Azure VM or Azure Container Apps because Marcus stated current agency infrastructure is on Azure. Do not introduce AWS-only runtime dependencies.

Server commands:

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

## Known Constraints To Mention If Asked

- Demo OCR uses fixture ground truth for deterministic evaluator behavior.
- Real uploads use the local docTR adapter and route OCR failures or low confidence to Needs Review.
- Fixture-backed batch demo and manual manifest-backed batch upload are implemented; batch processing is synchronous in the web process for the sprint prototype.
- Typography boldness routes to Needs Review instead of brittle raster font-weight failure.
- The app is a reviewer-support prototype, not a final legal approval/rejection system.
- The project does not use hosted OCR or hosted ML APIs at runtime.

---

## Submission Artifacts

- [ ] Screenshot home page.
- [ ] Screenshot clean Pass result.
- [ ] Screenshot government warning Fail result.
- [ ] Screenshot batch result table.
- [ ] Save final commit SHA. Current pushed SHA before requirements-gap update is `23e303d`.
- [ ] Draft submission email.
- [ ] Include GitHub URL.
- [ ] Include deployed URL.
- [ ] Include one-sentence local-first note.

---

## Definition Of Done

- [x] `https://www.labelsontap.ai` loads over HTTPS.
- [x] `https://labelsontap.ai` redirects to `https://www.labelsontap.ai`.
- [x] Home page has one-click demo buttons.
- [x] Clean demo returns Pass.
- [x] Government warning demo returns Fail.
- [x] ABV demo returns Fail.
- [x] Malt net contents demo returns Fail.
- [x] Country-of-origin demo returns Pass.
- [x] Batch demo returns multiple results.
- [x] CSV export works.
- [x] Result detail page shows expected, observed, evidence, source refs, and reviewer action.
- [x] Single upload form exists.
- [x] Manual manifest-backed batch upload form exists.
- [x] Fixture-backed batch demo is clearly available.
- [x] `pytest -q` passes.
- [x] `docker compose build` passes on the AWS host.
- [x] `docker compose up -d` runs on the AWS host.
- [x] AWS Lightsail deployment is running.
- [ ] COLA-style application data import is the central workflow.
- [ ] Field-by-field application-to-label matching covers brand, alcohol content, class/type, net contents, country of origin, and bottler/producer.
- [ ] CSV export is reviewer-ready and includes application IDs, expected values, observed values, verdicts, and reviewer actions.
- [ ] Large synthetic batch proof covers Sarah's 200-300 application scenario.
- [ ] Local public COLA ETL workspace exists and stays gitignored.
- [ ] Public form parser extracts structured application fields and label attachment metadata into local SQLite.
- [ ] Curated official public COLA fixtures are exported from local ETL data into committed fixture folders.
- [ ] AWS deployment is updated after local parser/fixture/app changes are tested.
- [ ] Azure deployment path is documented if time allows.
- [ ] Restricted-network runtime posture is documented.
- [ ] PII/document-retention prototype limits are documented.
- [x] README has quick start and live demo instructions.
- [x] PRD exists.
- [x] ARCHITECTURE exists.
- [x] TASKS exists and is committed.
- [x] TRADEOFFS exists.
- [x] DEMO_SCRIPT exists.
- [x] Legal corpus exists.
- [x] Source-backed criteria matrix exists.
- [x] Fixture provenance exists.
- [x] No secrets committed.
- [x] No private/confidential rejected COLA data committed.
- [x] No hosted OCR/ML API call exists in runtime code.
- [ ] Final submission email sent.

---

## Monday Submission Buffer

Only light verification and submission should remain for Monday:

- [ ] Open `https://www.labelsontap.ai`.
- [ ] Run Clean Label Demo.
- [ ] Run Batch Demo.
- [ ] Confirm GitHub repo is public.
- [ ] Confirm README loads.
- [ ] Confirm latest commit is visible.
- [ ] Send GitHub URL and deployed URL to Sam.

Submission URLs:

```text
Repository: https://github.com/AaronNHorvitz/Labels-On-Tap
Deployed app: https://www.labelsontap.ai
```
