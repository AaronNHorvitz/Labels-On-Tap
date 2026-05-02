# TASKS.md - Final Sprint Command Center

**Project:** Labels On Tap
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Canonical deployment URL:** `https://www.labelsontap.ai`
**Deadline:** Monday afternoon, May 4, 2026
**Current mission:** Prove that Labels On Tap can triage COLAs Online-style applications by comparing accepted public application data against OCR extracted from submitted label artwork, then route mismatches or uncertainty to human review.

Labels On Tap is not trying to replace a TTB compliance agent. The core proof is narrower and stronger:

```text
COLAs Online-style application data
  + accepted submitted label artwork
  -> local OCR / parsing
  -> deterministic field comparison
  -> Pass / Needs Review / Fail with evidence
```

The sprint priority is now:

1. Build a statistically defensible official public COLA evaluation corpus.
2. Prove OCR + field matching works on accepted public COLAs.
3. Demonstrate deterministic mismatch detection with synthetic negative cases.
4. Add legal reasoning/guidance only after the measurement story is solid.

---

## Current Truth

- [x] Public deployed app is live at `https://www.labelsontap.ai`.
- [x] `https://labelsontap.ai` redirects to `https://www.labelsontap.ai`.
- [x] Public health smoke passed at `https://www.labelsontap.ai/health`.
- [x] Runtime architecture is FastAPI + Jinja2/HTMX + local CSS.
- [x] OCR architecture is local docTR adapter with fixture OCR fallback.
- [x] Storage architecture is filesystem JSON job/result store.
- [x] Deployment architecture is Docker Compose + Caddy on AWS Lightsail.
- [x] Current deployment target remains AWS for submission; Azure is a documented portability path if time allows.
- [x] The app has demo routes, job pages, detail pages, single-label upload, manifest-backed batch upload, and CSV export.
- [x] `country_of_origin` and `imported` are first-class application fields.
- [x] Demo fixtures/data scaffold exists.
- [x] Tests scaffold exists.
- [x] Last known complete local test run: `pytest -q` passed with 61 tests.
- [x] Local Podman image rebuild passed on May 2, 2026.
- [x] Local container smoke passed on May 2, 2026 for `/health`, `/`, and `/demo/clean`.
- [x] Public COLA ETL scripts exist for search-result imports, public form fetches, form parsing, label image download, curated fixture export, and stratified sampling.
- [x] `data/work/` is gitignored and is the home for bulk/raw public COLA data.
- [x] Existing official public COLA corpus contains **810 unique parsed applications**.
- [x] Existing official public COLA corpus contains **1,433 discovered label panel attachments**.
- [x] Attachment downloads were audited on May 2, 2026; the existing local files were HTML error pages, not valid raster images.
- [x] Invalid local attachment rows were marked pending for future redownload. No raw files were deleted.
- [x] The downloader now validates attachment bytes with Pillow before accepting them as OCR-ready images.
- [x] The downloader now warms the public form session before requesting attachment URLs.
- [x] The OCR evaluator now skips invalid image files instead of treating HTML error pages as OCR failures.
- [ ] Current valid downloaded public label raster count is **0** until the TTB attachment endpoint is reachable and pending downloads are retried.
- [x] COLA Cloud sample pack importer exists as a development-only fallback when TTBOnline.gov is unavailable.
- [x] COLA Cloud API puller exists as a development-only fallback for bounded public-data pulls.
- [x] COLA Cloud adaptive stratified sampler exists for reproducible API-backed OCR evaluation plans.
- [x] COLA Cloud smoke imported 5 applications and 8 real label images locally.
- [x] COLA Cloud smoke OCR ran through local docTR in the Podman app image.
- [x] COLA Cloud balanced plan selected **1,500 applications** from **7,788 candidates** across May 1, 2025 through April 30, 2026.
- [x] COLA Cloud balanced calibration fetched **100 detail records** and evaluated **169 label images** with local docTR.
- [x] COLA Cloud field mapping now populates `alcohol_content` from `abv` and `net_contents` from `volume` + `volume_unit`.
- [x] COLA Cloud field evaluation now includes initial class/type synonym expansion.
- [x] Balanced calibration latency met Sarah's target: mean **1,413 ms/application**, max **3,620 ms/application**.
- [x] Balanced calibration now measures ABV and net contents: alcohol-content match rate **91.49% of 94 attempted**, net-contents match rate **83.72% of 86 attempted**.
- [x] Sampler supports an exact `calibration` / `holdout` split for the planned **1,500 / 1,500** design.
- [x] No-network plan-only check produced a **3,000-record** selected sample with exact split counts: **1,500 calibration**, **1,500 holdout**.
- [x] GPU PyTorch path works locally in `.venv-gpu` with CUDA 13.0 and the RTX 4090.
- [x] Experimental graph-aware OCR evidence scorer exists under `experiments/graph_ocr/`.
- [x] First safety-weighted graph scorer POC improved F1 from **0.7714** to **0.8714** and lowered false-clear rate from **0.0439** to **0.0132** on the 100-application calibration test split.
- [x] `MODEL_LOG.md` records OCR/model experiments and caveats.
- [x] `HANDOFF.md` records current state, GPU setup, data paths, and restart steps.
- [x] Existing public sampling used deterministic seeds and sampling without replacement.
- [x] Existing public sampling produced two non-overlapping samples: 300 applications and 500 applications.
- [x] TTB's public processing-time page reports **57,636 label applications received in 2026 as of May 1, 2026**.
- [x] Current month-stratified annual-volume estimate from local daily CSV exports is about **142,510 applications** for May 1, 2025 through April 30, 2026, with an approximate 95% CI of **132,011 to 153,009**.
- [ ] Public COLA Registry access is currently fragile/resetting; pause further automated registry access until it cools down.
- [ ] Deployment URL remains live through submission.
- [ ] TASKS.md is committed after this priority reset.

---

## Statistical Evaluation Thesis

Use accepted public COLA records as positive ground truth for this claim:

> Given an accepted public COLA application and its accepted label artwork, the system can extract relevant label text and confirm whether it matches the application fields.

Do not claim accepted public COLAs are ground truth for all compliance law. They are ground truth for the narrower application-data-to-label-artwork matching task.

Use synthetic negative fixtures for this separate claim:

> When application data and label artwork do not match, deterministic comparison rules can route the submission to Needs Review or Fail with evidence.

Core metrics to report:

- [ ] Field-level match rate for brand name.
- [ ] Field-level match rate for class/type.
- [ ] Field-level match rate for alcohol content.
- [ ] Field-level match rate for net contents.
- [ ] Field-level match rate for country of origin when imported/origin data is available.
- [ ] Field-level match rate for applicant/producer/bottler text when visible.
- [ ] Application-level Pass / Needs Review / Fail distribution.
- [ ] Per-label OCR latency: p50, p95, and worst-case.
- [ ] OCR failure modes: low confidence, missing field, curved text, rotated text, poor image quality, multi-panel ambiguity.
- [ ] False-clear rate on known synthetic negative cases.

Sample-size framing:

- [x] Use `N ~= 150,000` annual COLA applications as the working population size.
- [x] Current `n = 810` parsed official public COLAs gives about **+/- 3.4%** conservative 95% margin of error for a broad proportion estimate.
- [ ] Target `n = 3,000` public COLA applications if quota/time allows, split into **1,500 calibration/tuning** and **1,500 locked holdout** records.
- [x] A locked holdout of `n = 1,500` gives about **+/- 2.5 percentage points** conservative 95% margin of error for a binary proportion estimate.
- [ ] Explain clearly that `+/- 2.5%` is a 95% margin of error on the final holdout estimate, not a guarantee of production accuracy.
- [ ] Build 300-500 known-bad synthetic negative cases for false-clear testing.
- [ ] Explain the "rule of three": zero false clears in 300 known-bad cases implies an approximate 95% upper bound of 1% on the false-clear rate.

---

## Layer 1 - Official Public COLA Evaluation Corpus

**Priority:** P0

Use accepted public COLA applications as positive ground truth. The goal is not a massive scrape. The goal is a reproducible, defensible evaluation corpus with provenance.

- [x] Build local public COLA ETL workspace under `data/work/public-cola/`.
- [x] Keep bulk/raw public registry pulls, OCR output, and SQLite data out of git.
- [x] Use SQLite for metadata and fetch state.
- [x] Store raw HTML and label image files on disk, not as SQLite blobs.
- [x] Fetch and parse 810 unique public COLA applications.
- [x] Discover 1,433 public label image/panel attachment records.
- [x] Audit previously downloaded attachment files and prove they were invalid HTML error pages.
- [x] Mark invalid attachment rows pending so they are not included in OCR evaluation.
- [ ] Download valid public label raster images from those public records after the TTB endpoint stabilizes.
- [x] Preserve deterministic sample provenance and exclusion files.
- [ ] Pause additional TTB registry fetching while the public endpoint is resetting.
- [ ] When direct TTB endpoint stabilizes, reconcile a subset of COLA Cloud records back to printable public forms where possible.
- [ ] Retry pending public label image downloads with session warming, Pillow validation, and polite delay/retry settings.
- [ ] Use COLA Cloud sample pack/API only as development/silver-label fallback; do not make it a runtime dependency.
- [ ] Pull a bounded COLA Cloud API corpus only after the API key is stored locally in `.env`.
- [ ] Keep COLA Cloud API requests slow enough to respect the provider burst limit and detail-view quota.
- [x] Before scaling beyond the 100-record calibration set, map ABV/net-content fields from COLA Cloud details where available.
- [x] Before scaling beyond the 100-record calibration set, add initial class/type synonym matching.
- [ ] Before scaling beyond the full calibration set, inspect class/type misses and decide whether they are OCR failures, metadata/label mismatch, or expected absent label text.
- [ ] Export 10-25 curated official public COLA fixtures into `data/fixtures/public-cola/`.
- [ ] Each curated fixture must include source/provenance, parsed application JSON, label image metadata, and expected field checks.
- [ ] Keep official public records separate from synthetic negative records.
- [ ] Document the sampling method as deterministic two-stage stratified cluster sampling across month strata, with secondary balancing by product/import status where available.

Desired local layout:

```text
data/work/public-cola/
  registry.sqlite
  sampling/
    plan.json
    selected_days.csv
    selected_ttbs.csv
    split_manifest.csv
    summary.json
  raw/
    search-results/
    forms/
    images/
  parsed/
    applications/
    ocr/
```

Committed curated fixture layout:

```text
data/fixtures/public-cola/
  README.md
  <ttb_id>/
    application.json
    labels/
    expected.json
    provenance.json
```

---

## Layer 2 - OCR + Field Matching Proof

**Priority:** P0 and main submission story

This is the core AI-powered proof. Extract text from real accepted label images, compare it to accepted application fields, and report evidence.

- [x] Treat one COLA application as one evidence bundle that may contain many label images/panels.
- [x] Build an OCR evaluation runner for official public COLA records.
- [x] OCR each label image separately and preserve panel-level text/evidence.
- [x] Aggregate OCR text across front/back/neck/side panels for application-level comparison.
- [x] Extract or normalize application fields from parsed public COLA forms.
- [x] Compare OCR text against application fields:
  - [x] Brand name.
  - [x] Fanciful name when present.
  - [x] Class/type.
  - [x] Alcohol content.
  - [x] Net contents.
  - [x] Country of origin / origin where applicable.
  - [x] Applicant, permittee, bottler, producer, or name/address when visible.
- [x] Report field-level expected value, observed OCR evidence, match verdict, OCR confidence, and reviewer action.
- [x] Add code support for exact calibration/holdout manifests.
- [ ] Run the full 3,000-record split when enough quota/time is available.
- [ ] Tune OCR preprocessing and fuzzy-match thresholds only on the 1,500-record calibration split.
- [ ] Evaluate final OCR/comparison behavior on the 1,500-record locked holdout.
- [x] Save OCR and evaluation outputs under `data/work/public-cola/parsed/ocr/`.
- [ ] Summarize measured accuracy, coverage, latency, and limitations in `docs/performance.md`.
- [ ] Add a README section that leads with time/money savings using TTB's 2026 application-volume page and Sarah's 5-10 minute review estimate.

Reviewer-ready output requirements:

- [ ] Application ID / TTB ID.
- [ ] Label panel filename or source URL.
- [ ] Field name.
- [ ] Expected application value.
- [ ] Observed OCR evidence.
- [ ] Match verdict.
- [ ] OCR source and confidence.
- [ ] Reviewer action.
- [ ] Latency.

---

## Layer 3 - Deterministic Mismatch Detection

**Priority:** P1 after OCR proof

Use synthetic negative cases because confidential rejected/Needs Correction records are not public. The deterministic comparison layer should make the decision; OCR provides evidence.

- [ ] Treat [PHASE1_REJECTION.md](PHASE1_REJECTION.md) as the known-bad coverage checklist.
- [ ] Create synthetic negative data for every Phase 1 mismatch/rejection reason that is feasible in this sprint.
- [ ] Keep synthetic negative records separate from official public COLA records.
- [ ] For each synthetic negative fixture, include application data, label image, expected result JSON, OCR text/ground truth where useful, and provenance.
- [ ] Add or confirm deterministic rules:
  - [x] `FORM_BRAND_MATCHES_LABEL`
  - [ ] `FORM_ALCOHOL_CONTENT_MATCHES_LABEL`
  - [ ] `FORM_CLASS_TYPE_MATCHES_LABEL`
  - [ ] `FORM_NET_CONTENTS_MATCHES_LABEL`
  - [ ] `FORM_COUNTRY_OF_ORIGIN_MATCHES_LABEL`
  - [ ] `FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL`
  - [ ] `FORM_FANCIFUL_NAME_MATCHES_LABEL`
  - [x] `GOV_WARNING_EXACT_TEXT`
  - [x] `GOV_WARNING_HEADER_CAPS`
  - [x] `GOV_WARNING_HEADER_BOLD_REVIEW`
  - [x] `OCR_LOW_CONFIDENCE`
- [ ] Fail only on clear evidence-backed mismatches.
- [ ] Route uncertainty, poor OCR, missing field evidence, curved text failures, and ambiguous matches to Needs Review.
- [ ] Report false-clear rate on synthetic known-bad cases.
- [ ] Make the CSV export usable as a reviewer mismatch report, not only a compact summary.

---

## Layer 4 - Legal Reasoning / Guidance

**Priority:** P2, only after the OCR evaluation story is solid

Legal guidance is valuable, but it should explain deterministic findings rather than decide them.

- [ ] Keep the legal corpus and source-backed criteria matrix.
- [ ] Preserve source references on deterministic rule outputs.
- [ ] Add reviewer-facing explanation text for each deterministic finding.
- [ ] If time allows, evaluate a local LLM for drafting plain-English guidance from deterministic findings only.
- [ ] Do not let an LLM decide Pass / Needs Review / Fail.
- [ ] Do not use hosted LLM APIs at runtime.
- [ ] Clearly label any generated guidance as draft support for human review.

---

## Immediate Execution Order

1. Keep pausing further direct TTB registry requests until connection resets stop.
2. Use the COLA Cloud public-data bridge only for local development/OCR evaluation, not runtime.
3. Build the full 3,000-record public-data plan with exact 1,500 calibration / 1,500 holdout splits.
4. Fetch/details/images for the calibration split first and tune only on that split.
5. Freeze OCR preprocessing, field-normalization, and pass/review thresholds.
6. Evaluate the locked 1,500-record holdout and report field-level match rates, latency, and limitations.
7. Reconcile a small subset back to direct TTB printable forms if the public endpoint stabilizes.
8. Export 10-25 curated official public fixtures for committed demo/test use.
9. Build synthetic negative coverage for the highest-risk mismatch cases.
10. Update README, `docs/performance.md`, `TRADEOFFS.md`, and `DEMO_SCRIPT.md` around the final measurement story.
11. Redeploy only after local OCR/evaluation changes pass.

---

## Deployment Checklist

The public deployment is already live. Keep this checklist for redeploys or host rebuilds.

- [x] Launch AWS Lightsail/Ubuntu instance.
- [x] Attach static public IP.
- [x] Confirm firewall allows `80` and `443` publicly and `22` for SSH.
- [x] Point DNS:
  - [x] `www.labelsontap.ai` -> static public IP.
  - [x] `labelsontap.ai` -> static public IP.
- [x] Install Docker and Git.
- [x] Clone `https://github.com/AaronNHorvitz/Labels-On-Tap`.
- [x] Run `cp .env.example .env`.
- [x] Run `docker compose build`.
- [x] Run `docker compose up -d`.
- [x] Run public smoke: `curl https://www.labelsontap.ai/health`.
- [x] Confirm apex redirect: `curl -I https://labelsontap.ai`.
- [ ] Redeploy after OCR evaluation workflow is implemented.
- [ ] Run public demo script after redeploy.
- [ ] Update `docs/performance.md` with public Docker measurements.

---

## Runtime Architecture Lock

Keep this architecture stable:

- FastAPI
- Jinja2/HTMX
- local CSS
- docTR primary OCR adapter unless a faster local OCR adapter is added behind the same interface
- fixture OCR fallback for deterministic demos/tests
- filesystem job store
- Docker + Caddy
- no hosted OCR or hosted ML APIs at runtime
- no private/authenticated COLAs Online scraping
- no React/Vue/Angular
- no ZIP upload before the OCR proof is complete
- no database-backed runtime job store before submission

---

## Data Safety Rules

- [ ] Do not commit `data/work/`.
- [ ] Do not commit local SQLite databases.
- [ ] Do not commit raw bulk public registry pulls unless explicitly curated into `data/fixtures/public-cola/`.
- [ ] Do not commit raw iPhone/store photos.
- [ ] Strip EXIF/location metadata from any local phone-photo benchmark files before derived use.
- [ ] Do not scrape private/authenticated COLAs Online data.
- [ ] Do not claim rejected/Needs Correction data is public.
- [ ] Do not claim final OCR accuracy until held-out evaluation has actually run.

---

## Documentation Updates

- [ ] Update README first sentence so it clearly says the app triages COLAs Online-style applications and identifies labels that appear out of compliance.
- [ ] Put the time-savings/business case near the top of README:
  - TTB 2026 label applications received to date.
  - Sarah's 5-10 minute simple-review estimate.
  - Annualized reviewer-hour estimate.
- [ ] Add the official public COLA sampling methodology to README if not already current.
- [ ] Update `TRADEOFFS.md` with the simplified mission: OCR proof first, legal reasoning later.
- [ ] Update `docs/performance.md` with OCR field-matching metrics and latency.
- [ ] Update `DEMO_SCRIPT.md` around official COLA OCR proof and deterministic mismatch demos.
- [ ] Keep Azure portability documented, but do not migrate hosting unless AWS becomes a blocker.

---

## Submission Artifacts

- [ ] Screenshot home page.
- [ ] Screenshot official COLA evaluation summary or field-match result.
- [ ] Screenshot clean Pass result.
- [ ] Screenshot mismatch / Needs Review or Fail result.
- [ ] Screenshot batch result table.
- [ ] Save final commit SHA.
- [ ] Draft submission email.
- [ ] Include GitHub URL.
- [ ] Include deployed URL.
- [ ] Include one-sentence local-first note.
- [ ] Include one-sentence statistical evaluation note.

Submission URLs:

```text
Repository: https://github.com/AaronNHorvitz/Labels-On-Tap
Deployed app: https://www.labelsontap.ai
```

---

## Definition Of Done For Monday

- [x] Public app is live over HTTPS.
- [x] Public health check passes.
- [x] Existing demos work.
- [x] Local public COLA corpus exists and stays gitignored.
- [ ] OCR evaluation runner works on official public COLA records.
- [ ] Field-level matching metrics are generated from official public COLA records.
- [ ] README explains the business case and statistical methodology.
- [ ] `docs/performance.md` reports measured OCR/matching results and latency.
- [ ] Deterministic mismatch demo still works.
- [ ] CSV export shows reviewer-ready expected/observed/evidence/verdict/action fields.
- [ ] Tests pass.
- [ ] Docker build passes on the deployment host after final changes.
- [ ] `https://www.labelsontap.ai` is redeployed with the final version.
- [ ] Final submission email sent.
