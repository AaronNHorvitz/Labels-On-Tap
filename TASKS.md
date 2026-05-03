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
  -> raw Pass / Needs Review / Fail with evidence
  -> reviewer-policy queue where configured
```

The sprint priority is now:

1. Build a statistically defensible official public COLA evaluation corpus.
2. Prove OCR + field matching works on accepted public COLAs.
3. Demonstrate deterministic mismatch detection with synthetic negative cases.
4. Add configurable human-review policy queues before final acceptance or rejection.
5. Add legal reasoning/guidance only after the measurement story is solid.

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
- [x] Demonstration-only photo OCR intake route exists for real bottle/can/shelf photos without application fields.
- [x] Local COLA Cloud-derived public example demo exists for side-by-side application field vs OCR evidence review.
- [x] `country_of_origin` and `imported` are first-class application fields.
- [x] Demo fixtures/data scaffold exists.
- [x] Tests scaffold exists.
- [x] Last known complete local test run: `pytest -q` passed with 69 tests.
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
- [x] COLA Cloud-derived public calibration fetched **100 detail records** and evaluated **169 label images** with local docTR.
- [x] COLA Cloud field mapping now populates `alcohol_content` from `abv` and `net_contents` from `volume` + `volume_unit`.
- [x] COLA Cloud field evaluation now includes initial class/type synonym expansion.
- [x] COLA Cloud-derived balanced calibration latency met Sarah's target: mean **1,413 ms/application**, max **3,620 ms/application**.
- [x] COLA Cloud-derived balanced calibration now measures ABV and net contents: alcohol-content match rate **91.49% of 94 attempted**, net-contents match rate **83.72% of 86 attempted**.
- [x] Sampler supports an exact `calibration` / `holdout` split for the planned **1,500 / 1,500** design.
- [x] No-network plan-only check produced a **3,000-record** selected sample with exact split counts: **1,500 calibration**, **1,500 holdout**.
- [x] COLA Cloud-derived public corpus now contains **6,000 unique fetched applications** and **10,435 local label images** across two non-overlapping 3,000-application cohorts.
- [x] Canonical application-level evaluation manifests now exist under `data/work/cola/evaluation-splits/field-support-v1/`.
- [x] Current split is **2,000 train / 1,000 validation / 3,000 locked holdout**, with zero TTB ID overlap across splits.
- [x] Field-support target/pair manifests now exist under `data/work/cola/field-support-datasets/field-support-v1/`.
- [x] Field-support manifests contain **31,139 positive field targets** and **93,417 total pair examples** using a 1:2 positive-to-shuffled-negative design.
- [x] DistilRoBERTa was trained/evaluated on the new field-support pair manifests with a 3,000-application locked holdout.
- [x] RoBERTa-base was trained/evaluated on the same field-support pair manifests as a capacity/control comparison.
- [x] Current trained text-pair arbiter winner is DistilRoBERTa: holdout F1 **0.999872**, false-clear rate **0.000128**, CPU mean **15.76 ms/pair** on weak field-pair supervision.
- [x] Armored OCR conveyor layer exists for subprocess-isolated tri-engine OCR runs.
- [x] Armored OCR conveyor real tri-engine smoke passed at 3 images, 8 images, and 16 requested images.
- [x] Latest chunk-size 16 smoke processed **13 valid images**, skipped **3 invalid/corrupt images** in preflight, and completed **39 OCR rows** across docTR, PaddleOCR, and OpenOCR with **0 row errors**.
- [x] Full train/validation OCR conveyor dry run passed at chunk-size 16: **5,353 image rows**, **5,179 valid images**, **174 invalid/corrupt skipped**, **975 planned jobs**.
- [x] Full train/validation OCR conveyor ran under `data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/`.
- [x] OCR conveyor progress snapshot at `2026-05-03T11:51:46-05:00` showed **960 / 975** chunk result files complete and **0** OCR row errors.
- [x] Full train/validation OCR conveyor completed: **975 / 975** chunk result files, **0** OCR row errors.
- [ ] Locked holdout OCR conveyor has not been run and must remain sealed until preprocessing, model, and thresholds are frozen.
- [x] OpenCV typography preflight experiments are implemented under `experiments/typography_preflight/`.
- [x] Typography preflight synthetic SVM run completed with **20,000 train**, **5,000 validation**, and **5,000 test** crops.
- [x] Typography preflight measured about **0.09 ms/crop** SVM decision latency.
- [x] Typography preflight is **not promoted**: safe thresholds have low recall, while useful-F1 thresholds have too many false clears.
- [x] Corrected typography comparison trained SVM, XGBoost, and CatBoost on `audit-v5`; XGBoost wins raw F1, SVM wins false-clear/latency, and no hard-argmax model is promoted.
- [ ] Boldness remains `Needs Review` until the typography preflight is validated with a safe false-clear rate.
- [x] GPU PyTorch path works locally in `.venv-gpu` with CUDA 13.0 and the RTX 4090.
- [x] Experimental graph-aware OCR evidence scorer exists under `experiments/graph_ocr/`.
- [x] First safety-weighted graph scorer POC improved F1 from **0.7714** to **0.8714** and lowered false-clear rate from **0.0439** to **0.0132** on the COLA Cloud-derived 100-application calibration test split.
- [x] Curved-text OCR research changed the next experiment: evaluate mature pre-trained local OCR engines before attempting a custom HO-GNN/TPS/SVTR vision model.
- [x] PaddleOCR / PP-OCR is the first alternate OCR engine candidate to benchmark against docTR.
- [x] OpenOCR / SVTRv2 is the second alternate OCR engine candidate and now has a 30-image smoke benchmark.
- [x] PARSeq was added as a recognizer-stage experiment over OpenOCR-detected crops.
- [x] ASTER was added as a recognizer-stage experiment over OpenOCR-detected crops.
- [x] FCENet + ASTER was added as a detector-plus-recognizer experiment for arbitrary-shaped text.
- [x] ABINet was added as a recognizer-stage experiment over OpenOCR-detected crops.
- [x] Deterministic OCR ensemble arbitration exists for docTR + PaddleOCR + OpenOCR field-support scores.
- [x] Government-safe OCR ensemble smoke produced F1 **0.7416** with false-clear rate **0.0000** on the 20-application / 30-image smoke.
- [x] Raw `Pass` / `Needs Review` / `Fail` triage vocabulary is documented.
- [ ] Runtime reviewer-policy queues are not yet implemented; planned queues are `Ready to accept`, `Acceptance review`, `Manual evidence review`, `Rejection review`, and `Ready to reject`.
- [ ] Planned reviewer-policy defaults are unknown government-warning review **off**, rejection review **off**, and acceptance review **off**.
- [x] WineBERT/o domain-NER smoke benchmark exists and was run against combined docTR + PaddleOCR + OpenOCR text.
- [x] WineBERT/o was evaluated for deployment and not promoted because it did not improve the government-safe ensemble, lacks ABV/net-contents coverage, is wine-specific, and has unknown public model licensing.
- [x] OSA market-domain NER smoke benchmark exists and was run against combined docTR + PaddleOCR + OpenOCR text.
- [x] OSA was evaluated as a lightweight Apache-2.0 BERT-family arbiter; the first smoke improved hybrid F1 to **0.7486** with false-clear rate **0.0000**, but it is not promoted without a COLA Cloud-derived 100-application calibration run.
- [x] FoodBaseBERT-NER culinary-domain control was evaluated and pruned: entity-only F1 **0.0522**, hybrid F1 **0.7416**, false-clear rate **0.0000** at the safe threshold.
- [x] OpenVINO/ONNX/INT8 on EC2 `m7i` is a future CPU optimization path, not a current Lightsail performance claim.
- [x] OCR engine sweep scaffold exists under `experiments/ocr_engine_sweep/`.
- [x] `MODEL_LOG.md` records OCR/model experiments and caveats.
- [x] `MODEL_ARCHITECTURE.md` records the end-to-end model architecture, train/validation/test plan, and model promotion gates.
- [x] `HANDOFF.md` records current state, GPU setup, data paths, and restart steps.
- [x] `HANDOFF_DETAILED_2026-05-03.md` records the full restart-grade state, data-source distinction, model results, quota strategy, and future execution plan.
- [x] Existing public sampling used deterministic seeds and sampling without replacement.
- [x] Existing public sampling produced two non-overlapping samples: 300 applications and 500 applications.
- [x] TTB's public processing-time page reports **57,636 label applications received in 2026 as of May 1, 2026**.
- [x] Current month-stratified annual-volume estimate from local daily CSV exports is about **142,510 applications** for May 1, 2025 through April 30, 2026, with an approximate 95% CI of **132,011 to 153,009**.
- [ ] Public COLA Registry access is currently fragile/resetting; pause further automated registry access until it cools down.
- [ ] Deployment URL remains live through submission.
- [x] TASKS.md includes the current reviewer-policy layer update.

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
- [ ] Reviewer-policy queue distribution under default settings.
- [ ] Reviewer-policy queue distribution under conservative settings where both acceptance and rejection require review.
- [ ] Per-label OCR latency: p50, p95, and worst-case.
- [ ] OCR failure modes: low confidence, missing field, curved text, rotated text, poor image quality, multi-panel ambiguity.
- [ ] False-clear rate on known synthetic negative cases.

Split discipline:

- [x] Create the locked application-level split before generating field-pair examples.
- [x] Use the current `2,000` train / `1,000` validation / `3,000` locked-holdout design for trained field-support classifiers.
- [ ] Stratify by month, product family, import/domestic bucket, and label-panel complexity where data allows.
- [x] Ensure the same TTB ID never appears across train, validation, and test.
- [ ] Tune preprocessing, thresholds, model family, and safety policy on validation only.
- [ ] Report final trained-model metrics on the locked test only after all tuning decisions are frozen.

Sample-size framing:

- [x] Use `N ~= 150,000` annual COLA applications as the working population size.
- [x] Current `n = 810` parsed official public COLAs gives about **+/- 3.4%** conservative 95% margin of error for a broad proportion estimate.
- [x] Target `n = 3,000` public COLA applications if quota/time allows.
- [x] Supersede the initial 3,000-record target with a **6,000-application** public-data corpus.
- [x] Preserve a **3,000-application locked holdout** for final model evaluation.
- [x] Use **2,000 train**, **1,000 validation**, and **3,000 locked holdout** for trained field-support classifiers.
- [x] A locked holdout of `n = 3,000` gives about **+/- 1.8 percentage points** conservative 95% margin of error for a binary proportion estimate, before finite-population correction.
- [ ] Explain clearly that `+/- 1.8%` is a conservative 95% margin of error on the 3,000-record final holdout estimate, not a guarantee of production accuracy.
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
- [ ] Use COLA Cloud sample pack/API only as a development public-data bridge; do not make it a runtime dependency.
- [x] Pull a bounded COLA Cloud API corpus only after the API key is stored locally in `.env`.
- [x] Fetch 6,000 COLA Cloud-derived public application/detail records and 10,435 label images into gitignored `data/work/cola/`.
- [x] Create application-level train/validation/holdout manifests from the 6,000-record corpus.
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
- [ ] Run OCR/evidence extraction across the 6,000-record split when enough local compute time is available.
- [ ] Tune OCR preprocessing, fuzzy-match thresholds, and trained arbiters only on the 2,000 train / 1,000 validation development cohort.
- [ ] Evaluate final OCR/comparison behavior exactly once on the 3,000-record locked holdout.
- [x] Save OCR and evaluation outputs under gitignored `data/work/public-cola/parsed/ocr/` and `data/work/cola/`.
- [ ] Summarize measured accuracy, coverage, latency, and limitations in `docs/performance.md`.
- [ ] Add a README section that leads with time/money savings using TTB's 2026 application-volume page and Sarah's 5-10 minute review estimate.

Reviewer-ready output requirements:

- [ ] Application ID / TTB ID.
- [ ] Label panel filename or source URL.
- [ ] Field name.
- [ ] Expected application value.
- [ ] Observed OCR evidence.
- [ ] Match verdict.
- [ ] Raw system verdict.
- [ ] Reviewer-policy queue.
- [ ] OCR source and confidence.
- [ ] Recommended reviewer action.
- [ ] Final reviewer action / override note when a human decision has been recorded.
- [ ] Latency.

---

## Layer 2 Photo OCR Intake Demo

**Priority:** P1 demonstration aid, not official verification

This capability supports Aaron's local phone-photo benchmark and live demos with
store-shelf bottle/can photos. It is not a replacement for COLA application
comparison because no application fields are supplied.

- [x] Add home-page photo intake upload form.
- [x] Add `POST /photo-intake` route.
- [x] Add `GET /photo-intake/{job_id}/{item_id}` result page.
- [x] Reuse upload preflight, randomized filenames, and local OCR / fixture OCR fallback.
- [x] Extract candidate fields from raw OCR text:
  - [x] brand candidate,
  - [x] product type candidate,
  - [x] class/type candidate,
  - [x] alcohol-content candidate,
  - [x] net-contents candidate,
  - [x] country-of-origin candidate,
  - [x] government-warning signals.
- [x] Display candidate values, confidence, method, evidence, OCR lines, and raw OCR text.
- [x] Clearly label the feature as demonstration-only OCR extraction, not COLA verification.
- [ ] Add a manual "promote candidate to verification form" helper if time allows.
- [ ] Run a small private local-photo benchmark under `data/work/local-photo-benchmark/` after EXIF/location stripping.

---

## Layer 2 Public COLA Example Comparison Demo

**Priority:** P1 demonstration aid using local public evaluation corpus

This capability lets evaluators see the real workflow on public example data:
application fields on one side, OCR evidence from associated label panels on
the other side. It uses already-downloaded local COLA Cloud-derived public data
under `data/work/cola/`.

- [x] Add home-page **Run Public COLA Example Demo** action.
- [x] Add `GET /cola-cloud-demo` route that selects a deterministic local public example.
- [x] Add `GET /cola-cloud-demo/{job_id}` side-by-side comparison page.
- [x] Add safe image-serving route for copied job-local label panel images.
- [x] Show application fields, source/product metadata, label panel images, OCR source/confidence/timing, and raw OCR text.
- [x] Show field-level expected value, best OCR evidence, best panel, score, verdict, and reviewer action.
- [x] Load cached OCR conveyor output when available before falling back to live local OCR.
- [x] Keep raw COLA Cloud data, image files, and cached OCR under gitignored `data/work/`.
- [x] Show a friendly missing-data page when `data/work/cola/` is absent.
- [ ] Add a small curated public fixture later if a public deployed version needs this demo without local bulk data.

---

## Layer 2A - Alternate OCR Engine Sweep

**Priority:** P0 support track for the OCR proof

The goal is not to replace the stable deployed app blindly. The goal is to determine whether a mature pre-trained local OCR system improves curved/irregular alcohol-label text enough to justify promotion.

Core principle:

```text
Better OCR engine -> better extracted text
Graph evidence scorer -> better field-support assembly
Deterministic rules -> final Pass / Needs Review / Fail decision
```

Experimental candidates:

- [x] Keep docTR as the measured baseline and rollback path.
- [x] Add a PaddleOCR / PP-OCR smoke benchmark wrapper under the experiment scaffold.
- [x] Run PaddleOCR 3.3.3 / PaddlePaddle 3.2.0 30-image CPU smoke benchmark.
- [x] Document that PaddleOCR 3.5.0 / PaddlePaddle 3.3.1 hit a CPU oneDNN/PIR runtime issue.
- [x] Compute side-by-side field-support accuracy, precision, recall, F1, specificity, and false-clear rate for docTR vs PaddleOCR.
- [x] Add an OpenOCR / SVTRv2 smoke benchmark wrapper under the experiment scaffold.
- [x] Run OpenOCR 0.1.5 / SVTRv2 30-image CPU smoke benchmark.
- [x] Compute side-by-side field-support metrics for docTR vs PaddleOCR vs OpenOCR.
- [x] Add a PARSeq crop-recognition benchmark using OpenOCR-detected boxes.
- [x] Run PARSeq autoregressive crop-recognition smoke on the same 30 images.
- [x] Run PARSeq non-autoregressive/refinement crop-recognition smoke on the same 30 images.
- [x] Compute side-by-side field-support metrics including PARSeq AR and NAR crop runs.
- [x] Add an MMOCR ASTER crop-recognition benchmark using OpenOCR-detected boxes.
- [x] Run ASTER crop-recognition smoke on the same 30 images.
- [x] Compute side-by-side field-support metrics including ASTER crop runs.
- [x] Add an MMOCR FCENet + ASTER detector-recognizer benchmark.
- [x] Run FCENet + ASTER detector-recognizer smoke on the same 30 images.
- [x] Compute side-by-side field-support metrics including FCENet + ASTER.
- [x] Add an MMOCR ABINet crop-recognition benchmark using OpenOCR-detected boxes.
- [x] Run ABINet crop-recognition smoke on the same 30 images.
- [x] Compute side-by-side field-support metrics including ABINet crop runs.
- [x] Add deterministic OCR ensemble arbitration for docTR + PaddleOCR + OpenOCR.
- [x] Run deterministic ensemble smoke on the same 20-application / 30-image benchmark.
- [x] Add government-safe ensemble policy requiring unanimous alcohol-content support.
- [x] Add WineBERT/o entity-support benchmark over combined OCR text.
- [x] Run `panigrah/wineberto-labels` on the same 20-application / 30-image benchmark.
- [x] Run `panigrah/wineberto-ner` on the same 20-application / 30-image benchmark.
- [x] Run WineBERT/o threshold sensitivity for `80`, `85`, `90`, and `95`.
- [x] Add OSA market-domain NER benchmark support over combined OCR text.
- [x] Run `AnanthanarayananSeetharaman/osa-custom-ner-model` on the same 20-application / 30-image benchmark.
- [x] Run OSA threshold sensitivity for `80`, `85`, `90`, and `95`.
- [x] Add FoodBaseBERT-NER culinary-domain control support over combined OCR text.
- [x] Run `Dizex/FoodBaseBERT-NER` on the same 20-application / 30-image benchmark.
- [x] Run FoodBaseBERT-NER threshold sensitivity for `80`, `85`, `90`, and `95`.
- [x] Record the statistical caveat that small sample sizes increase variance and the current 20-application / 30-image result is directional only.
- [ ] Promote PaddleOCR into a fuller experimental adapter only if field-level comparison beats or complements docTR.
- [ ] Promote OpenOCR into a fuller experimental adapter only if a larger run shows it beats or complements docTR/PaddleOCR.
- [ ] Keep the graph-aware scorer as a post-OCR evidence layer, not an OCR replacement.
- [ ] Keep the full custom HO-GNN/TPS/SVTR model as documented future research unless a mature pre-trained shortcut fails and time remains.

Isolation and dependency safety:

- [x] Put engine-sweep code under `experiments/ocr_engine_sweep/` or an equivalent non-runtime experiment path.
- [x] Use an isolated container environment for heavy OCR candidates; do not add heavyweight dependencies to production `requirements.txt` until an engine wins.
- [ ] Do not change the deployed default OCR engine until benchmarks and tests justify it.
- [ ] Do not send images to hosted OCR or hosted ML APIs.
- [ ] Do not commit downloaded models, OCR caches, raw public data, or benchmark image outputs.

Normalized output contract:

- [x] Normalize the current docTR/PaddleOCR smoke wrappers to the existing `OCRResult` shape.
- [x] Normalize the OpenOCR wrapper to the existing `OCRResult` shape.
- [x] Normalize PARSeq crop-recognition output to the existing `OCRResult` shape.
- [x] Normalize ASTER crop-recognition output to the existing `OCRResult` shape.
- [x] Normalize FCENet + ASTER detector-recognizer output to the existing `OCRResult` shape.
- [x] Normalize ABINet crop-recognition output to the existing `OCRResult` shape.
- [x] Preserve `source` as `local docTR`, `local PaddleOCR`, `local OpenOCR`, or equivalent.
- [x] Preserve per-block text.
- [x] Preserve per-block confidence when available.
- [x] Preserve per-block geometry/boxes when available.
- [x] Capture `preprocessing_ms`, `ocr_ms`, and `total_ms`.
- [ ] Record engine version, model name, CPU/GPU mode, image size, and host details in benchmark summaries.

Benchmark stages:

- [x] Run a 1-image smoke test for import/runtime sanity.
- [x] Run a 10-image mixed-shape smoke benchmark before any larger run.
- [x] Run a 30-image mixed-shape smoke benchmark after the 10-image run.
- [x] Run OpenOCR on the same 30-image mixed-shape smoke benchmark.
- [x] Run PARSeq AR and NAR crop-recognition on the same 30-image mixed-shape smoke benchmark.
- [x] Run ASTER crop-recognition on the same 30-image mixed-shape smoke benchmark.
- [x] Run FCENet + ASTER detector-recognizer on the same 30-image mixed-shape smoke benchmark.
- [x] Run ABINet crop-recognition on the same 30-image mixed-shape smoke benchmark.
- [ ] Run the same 100-application / 169-image COLA Cloud-derived public calibration set used by docTR.
- [x] Compare 30-image smoke against docTR using identical field-support scoring logic.
- [ ] Compare the 100-application COLA Cloud-derived calibration set against docTR using identical field-matching logic.
- [ ] If a candidate wins on the 100-application set, run it on the larger COLA Cloud-derived calibration split.
- [ ] Freeze preprocessing, thresholds, and engine choice before evaluating the 3,000-record locked holdout.

Metrics to compare:

- [x] Initial brand-name field-support F1 comparison.
- [x] Initial fanciful-name field-support F1 comparison.
- [x] Initial class/type field-support F1 comparison.
- [x] Initial alcohol-content field-support F1 comparison.
- [x] Initial net-contents field-support F1 comparison.
- [x] Initial country-of-origin field-support F1 comparison.
- [ ] Applicant/producer visibility rate if practical.
- [ ] Application-level Pass / Needs Review distribution on accepted public records.
- [x] Initial shuffled-negative false-clear comparison for docTR vs PaddleOCR.
- [x] Initial shuffled-negative false-clear comparison for docTR vs PaddleOCR vs OpenOCR.
- [x] Initial shuffled-negative false-clear comparison including PARSeq AR/NAR crop runs.
- [x] Initial shuffled-negative false-clear comparison including ASTER crop runs.
- [x] Initial shuffled-negative false-clear comparison including FCENet + ASTER.
- [x] Initial shuffled-negative false-clear comparison including ABINet crop runs.
- [x] Initial deterministic ensemble comparison: government-safe ensemble F1 0.7416, false-clear rate 0.0000.
- [x] Initial WineBERT/o comparison: `wineberto-labels` entity-only F1 0.4865, false-clear rate 0.0000.
- [x] Initial WineBERT/o comparison: `wineberto-ner` entity-only F1 0.1176, false-clear rate 0.0000.
- [x] Initial WineBERT/o hybrid comparison: tied government-safe ensemble F1 0.7416, false-clear rate 0.0000, with no incremental lift.
- [x] Initial OSA comparison: entity-only F1 0.5166, false-clear rate 0.0000.
- [x] Initial OSA hybrid comparison: improved government-safe ensemble F1 from 0.7416 to 0.7486 with false-clear rate 0.0000.
- [x] Initial FoodBaseBERT-NER comparison: entity-only F1 0.0522, false-clear rate 0.0000.
- [x] Initial FoodBaseBERT-NER hybrid comparison: tied government-safe ensemble F1 0.7416, false-clear rate 0.0000, with no incremental lift.
- [ ] False-clear rate on synthetic known-bad fixtures.
- [x] Initial per-image latency smoke: 30-image PaddleOCR mean 1,105.00 ms, median 1,096.50 ms, worst 1,544 ms.
- [x] Initial per-image latency smoke: 30-image OpenOCR mean 563.77 ms, median 582.50 ms, worst 1,211 ms.
- [x] Initial per-image latency smoke: PARSeq AR over OpenOCR crops mean 293.47 ms, median 212.00 ms, worst 870 ms.
- [x] Initial per-image latency smoke: PARSeq NAR/refine-2 over OpenOCR crops mean 215.17 ms, median 168.50 ms, worst 655 ms.
- [x] Initial per-image latency smoke: ASTER over OpenOCR crops mean 119.87 ms, median 111.00 ms, worst 275 ms.
- [x] Initial per-image latency smoke: FCENet + ASTER mean 4,526.70 ms, median 4,073.50 ms, worst 10,525 ms.
- [x] Initial per-image latency smoke: ABINet over OpenOCR crops mean 458.83 ms, median 369.00 ms, worst 1,229 ms.
- [x] Initial field-support smoke: PaddleOCR F1 0.7151 vs docTR F1 0.6627 vs OpenOCR F1 0.6049 vs PARSeq AR/NAR F1 0.5513 vs ASTER F1 0.5548 vs FCENet + ASTER F1 0.3972 vs ABINet F1 0.4865.
- [x] Initial field-support smoke: PaddleOCR false-clear rate 0.0268 vs docTR/OpenOCR false-clear rate 0.0089.
- [x] Initial ensemble smoke: naive any-engine policy F1 0.7459 but false-clear rate 0.0357, so it is not government-safe.
- [x] Initial ensemble smoke: government-safe policy F1 0.7416 and false-clear rate 0.0000 by routing non-unanimous alcohol-content evidence to review.
- [x] Initial WineBERT/o threshold smoke: threshold 80 raised recall to 0.6161 but false-clear rate rose to 0.0714.
- [x] Initial WineBERT/o threshold smoke: thresholds 90 and 95 stayed safe but did not beat the government-safe deterministic ensemble.
- [x] Initial OSA threshold smoke: threshold 80 raised recall to 0.6161 but false-clear rate rose to 0.0714.
- [x] Initial OSA threshold smoke: thresholds 90 and 95 preserved false-clear rate 0.0000, with F1 0.7486.
- [x] Initial FoodBaseBERT-NER threshold smoke: threshold 80 raised recall to 0.5982 but false-clear rate rose to 0.0714.
- [x] Initial FoodBaseBERT-NER threshold smoke: threshold 90 preserved false-clear rate 0.0000 but did not beat the government-safe ensemble.
- [x] Initial field-support smoke: ASTER false-clear rate 0.0000 with low recall on the 20-application / 30-image smoke.
- [x] Initial field-support smoke: FCENet + ASTER false-clear rate 0.0089 with low recall and slow CPU latency.
- [x] Initial field-support smoke: ABINet false-clear rate 0.0000 with low recall on the 20-application / 30-image smoke.
- [ ] Per-application latency across all associated label panels.
- [ ] OCR failure modes: curved text, rotated text, small warning text, glare, low contrast, multi-panel ambiguity.

Promotion gates:

- [ ] Candidate must be local/self-hosted at runtime.
- [ ] Candidate must improve one or more weak fields, especially class/type, brand, or fanciful name.
- [ ] Candidate must not increase false clears on known-bad synthetic fixtures.
- [ ] Candidate must keep per-label latency near Sarah's five-second target after warmup.
- [ ] Candidate must fail safely to Needs Review or docTR fallback when unavailable.
- [ ] Candidate must have a clean Docker/deployment path before becoming the default.
- [x] Candidate smoke results are recorded in `MODEL_LOG.md` and `docs/performance.md`.

OpenVINO / EC2 m7i path:

- [ ] Treat OpenVINO/ONNX/INT8 as an optimization path after a candidate wins, not as a current runtime claim.
- [ ] If CPU latency is too slow on Lightsail, benchmark on EC2 `m7i.xlarge` or similar Intel AMX-capable instance.
- [ ] Export candidate model to ONNX only if the engine's native path wins first.
- [ ] Try OpenVINO conversion and INT8 post-training quantization only after baseline candidate metrics are known.
- [ ] Report OpenVINO numbers separately from current deployed Lightsail numbers.

Documentation deliverables:

- [x] Add OCR experimentation strategy to `README.md`.
- [x] Add OCR engine sweep and OpenVINO trade-offs to `TRADEOFFS.md`.
- [x] Add deterministic OCR ensemble smoke results to `TRADEOFFS.md`.
- [x] Add WineBERT/o domain-NER smoke results to `TRADEOFFS.md`.
- [x] Add OSA market-domain NER smoke results to `TRADEOFFS.md`.
- [x] Add FoodBaseBERT-NER culinary-domain control results to `TRADEOFFS.md`.
- [x] Add each serious run to `MODEL_LOG.md`.
- [x] Add initial PaddleOCR smoke timing and extraction tables to `docs/performance.md`.
- [x] Add deterministic OCR ensemble smoke results to `docs/performance.md`.
- [x] Add WineBERT/o domain-NER smoke results to `docs/performance.md`.
- [x] Add OSA market-domain NER smoke results to `docs/performance.md`.
- [x] Add FoodBaseBERT-NER culinary-domain control results to `docs/performance.md`.
- [ ] Update `DEMO_SCRIPT.md` only if the deployed app's OCR behavior changes.

---

## Layer 2B - Armored OCR Conveyor

**Priority:** P0 before max-win tri-engine OCR execution

The max-win architecture is:

```text
docTR + PaddleOCR + OpenOCR
  -> DistilRoBERTa field-support arbiter
  -> graph-aware evidence scorer
  -> deterministic compliance rules
```

Before running that over thousands of images, the conveyor protects the run from corrupt files and native OCR crashes.

- [x] Add `docs/ocr-conveyor.md`.
- [x] Add `scripts/run_ocr_conveyor.py`.
- [x] Preflight image signatures before OCR.
- [x] Validate image decode with Pillow before OCR.
- [x] Write an image manifest under gitignored `data/work/ocr-conveyor/`.
- [x] Write an OCR chunk job manifest under gitignored `data/work/ocr-conveyor/`.
- [x] Run OCR chunks in subprocesses so native engine crashes cannot kill the parent run.
- [x] Record stdout/stderr, return code, row counts, and status per chunk.
- [x] Support resume by skipping completed chunks unless `--force` is passed.
- [x] Run a dry-run conveyor manifest for train/validation.
- [x] Run a small real smoke conveyor with all three engines.
- [x] Run chunk-size 16 real smoke with all three engines: **13 valid images**, **3 invalid skipped**, **39 OCR rows**, **0 row errors**.
- [x] Run chunk-size 16 full train/validation dry run: **5,353 image rows**, **5,179 valid**, **174 invalid skipped**, **975 planned jobs**.
- [ ] Run full train/validation conveyor after smoke passes.
- [ ] Attach conveyor OCR JSON to field-support pair manifests.
- [ ] Run holdout conveyor only after preprocessing, model, and threshold choices are frozen.

---

## Layer 2C - Trainable Field-Support Classifier

**Priority:** P0/P1 support track after corpus expansion

Do not train token-level NER from public COLA data unless human span labels are
created. The next supervised model should be a field-support classifier because
public COLA records provide application fields and accepted label artwork, not
gold token spans.

Target input/output:

```text
Input:
  field_name
  expected application value
  OCR candidate text or application-level OCR evidence
  optional OCR engine scores/source/confidence

Output:
  supports_field = yes/no
```

Planned model candidates:

- [x] Create field-support training examples from application-level splits only.
- [x] Generate positive field targets from accepted application fields.
- [x] Generate shuffled negative pairs from same-field values in other applications within the same split.
- [ ] Attach same-application OCR evidence to the generated field-support targets/pairs.
- [ ] Generate hard negatives for high-risk fields such as alcohol content and net contents.
- [x] Train a DistilRoBERTa field-support classifier first on weak field-pair supervision.
- [x] Train a RoBERTa-base field-support classifier as a capacity/control comparison on weak field-pair supervision.
- [ ] Compare both against the deterministic government-safe ensemble and OSA hybrid.
- [ ] Tune thresholds on validation only, optimizing primarily for false-clear control.
- [x] Evaluate the weak-supervision text-pair classifiers once on the 3,000-application locked holdout.
- [ ] Evaluate OCR-backed classifiers exactly once on the locked test after OCR preprocessing, thresholds, and model choice are frozen.
- [ ] Promote only behind an adapter/feature flag if locked-test F1 improves and false-clear posture remains acceptable.
- [ ] Keep deterministic rules as the final decision layer even if a classifier is added.

Deployment rule:

```text
No trained Transformer becomes runtime default unless it beats the measured
baseline on validation and locked test, fits CPU latency, and has rollback.
```

---

## Layer 2D - Government Warning Typography Preflight

**Priority:** P1 after the train/validation OCR conveyor is safe or complete

Jenny explicitly stated that `GOVERNMENT WARNING:` must be all caps and bold.
The all-caps requirement is already deterministic. Boldness is currently a
human-review trigger because font-weight inference from arbitrary label rasters
is brittle.

Planned experiment:

```text
OCR isolates GOVERNMENT WARNING:
  -> crop heading region
  -> OpenCV stroke/shape features
  -> Support Vector Machine classifier
  -> conservative bold / non-bold / uncertain typography preflight
```

Do not touch the running OCR conveyor while building this. Keep it isolated:

```text
experiments/typography_preflight/
data/work/typography-preflight/
```

Tasks:

- [x] Create `experiments/typography_preflight/README.md`.
- [x] Create a synthetic typography dataset generator for `GOVERNMENT WARNING:` crops.
- [x] Add corrected human-inspection dataset builder: `experiments/typography_preflight/build_audit_dataset.py`.
- [x] Use local system fonts only.
- [x] Generate at least **20,000 train**, **5,000 validation**, and **5,000 test** synthetic crops.
- [x] Hold out font families and distortion recipes across train/validation/test.
- [x] Include bold, non-bold, degraded, warped, blurred, compressed, and low-contrast variants.
- [x] Extract OpenCV features: ink density, edge density, distance-transform stroke width, stroke-width variance, connected-component statistics, projection profiles, and HOG descriptors.
- [x] Train a CPU-only Support Vector Machine-style margin classifier with `StandardScaler`.
- [x] Run with CPU limits such as `CUDA_VISIBLE_DEVICES=""`, `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, and `nice`/`ionice`.
- [x] Report accuracy, precision, recall, specificity, F1, confusion matrix, mean/p95 crop latency, and false-clear rate.
- [x] Treat `false clear = non-bold or uncertain heading classified as acceptable bold` as the primary safety metric.
- [ ] Smoke test approved public COLA warning crops as positive examples if warning-heading crops can be isolated cleanly.
- [x] Keep all generated crops, features, metrics, and model files under gitignored `data/work/typography-preflight/`.
- [x] Commit only experiment code/docs, never synthetic image bulk or `.joblib` model artifacts.
- [x] Update `MODEL_LOG.md`, `TRADEOFFS.md`, `MODEL_ARCHITECTURE.md`, and README after the experiment runs.
- [x] Document that the first `svm-v2` binary target mixed font weight, image quality, and auto-clearance policy and is now treated as a flawed-target baseline.
- [x] Generate corrected `audit-v5` inspection data with separate `font_weight_label`, `header_text_label`, `quality_label`, `visual_font_decision_label`, and `header_decision_label`.
- [x] Remove the source `borderline` font class: generated bold fonts are `bold`; medium/semibold/demibold/light/thin/book/regular fonts are `not_bold`.
- [x] Reserve `needs_review_unclear` for unreadable/degraded crops, not for font-weight compromise cases.
- [x] Human-inspect `data/work/typography-preflight/audit-v5/` before training any new classifier.
- [x] Add `experiments/typography_preflight/compare_models.py` for CPU-only SVM/XGBoost/CatBoost comparison.
- [x] Train side-by-side multiclass SVM, XGBoost, and CatBoost models against `audit-v5` labels after inspection.
- [x] Report Model 1 metrics for `visual_font_decision_label`.
- [x] Report Model 2 metrics for `header_decision_label`.
- [x] Document that XGBoost has the best raw F1, SVM has the safest false-clear/latency posture, and CatBoost is not currently buying enough benefit.
- [x] Add extended 80/20 typography comparison with LightGBM, Logistic Regression, MLP, and strict-veto ensemble.
- [x] Document that LightGBM wins raw F1 in the extended run, while strict veto is the safest false-clear posture.
- [ ] Add validation-threshold tuning so weak `clearly_bold` or `correct` predictions route to `needs_review_unclear`.
- [ ] Keep `GOV_WARNING_HEADER_BOLD_REVIEW` as Needs Review unless validation/test false-clear behavior justifies promotion.

Documentation framing:

```text
This is a classical statistical-learning preflight, not a deep-learning OCR
replacement. Following Hastie, Tibshirani, and Friedman, a margin-based
classifier is appropriate when engineered stroke/shape features capture the
decision boundary and low CPU latency matters.
```

Reference:

```text
Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome.
The Elements of Statistical Learning: Data Mining, Inference, and Prediction.
2nd ed., Springer, 2009.
```

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

## Layer 3A - Human Review Policy Queues

**Priority:** P1 after raw verdicts are stable

Raw `Pass`, `Needs Review`, and `Fail` outputs should feed a reviewer workflow.
They should not be described as final agency action. The policy layer lets TTB
choose how much human confirmation is required for a pilot, batch type, or risk
posture.

Policy settings:

- [ ] Add `review_unknown_government_warning: bool`, default `false`.
- [ ] Add `require_review_before_rejection: bool`, default `false`.
- [ ] Add `require_review_before_acceptance: bool`, default `false`.
- [ ] Document that these are workflow settings, not model thresholds.
- [ ] Add a control-board note that an unknown/unverifiable mandatory government warning defaults to `Fail` unless warning human review is enabled.

Routing contract:

- [ ] `Pass` + acceptance review off -> `Ready to accept`.
- [ ] `Pass` + acceptance review on -> `Acceptance review`.
- [ ] `Fail` + rejection review on -> `Rejection review`.
- [ ] `Fail` + rejection review off -> `Ready to reject`.
- [ ] `Government warning unknown` + warning review off -> `Fail`, then normal fail routing.
- [ ] `Government warning unknown` + warning review on -> `Manual evidence review`.
- [ ] `Needs Review` -> `Manual evidence review` regardless of the toggles.

Reviewer action contract:

- [ ] Add reviewer actions: `Accept`, `Reject`, `Request correction / better image`, `Override with note`, and `Escalate`.
- [ ] Require a note for overrides and escalations.
- [ ] Preserve raw evidence and source-backed reasons even after reviewer action.
- [ ] Add CSV/export columns for `raw_verdict`, `policy_queue`, `reviewer_action`, `reviewer_note`, and `reviewed_at`.
- [ ] Add batch summary counts by policy queue so 200-300 application batches can be worked in priority order.
- [ ] Add tests for every routing combination.

Documentation contract:

- [x] Document the policy layer in `README.md`.
- [x] Document the policy layer in `PRD.md`.
- [x] Document the policy layer in `ARCHITECTURE.md`.
- [x] Document the policy layer in `MODEL_ARCHITECTURE.md`.
- [x] Document the policy layer in `TRADEOFFS.md`, `DEMO_SCRIPT.md`, and handoff docs.

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
3. Keep docTR as the deployed default unless PaddleOCR/OpenOCR or an ensemble wins the measured comparison and fits the CPU SLA.
4. Use the current 6,000-record public-data corpus without replacement.
5. Use the current 2,000 train / 1,000 validation / 3,000 locked-holdout split.
6. Completed: full train/validation armored OCR conveyor with chunk-size 16.
7. Completed: isolated OpenCV typography preflight experiments, including SVM/XGBoost/CatBoost comparison.
8. Attach OCR evidence to the field-support manifests before retraining DistilRoBERTa or graph scorers.
9. Freeze OCR engine choice, OCR preprocessing, field-normalization, model family, pass/review thresholds, and any typography-preflight threshold.
10. Evaluate the locked test split and report field-level match rates, false-clear rate, latency, and limitations.
11. Keep locked-test applications untouched until settings are frozen.
12. Reconcile a small subset back to direct TTB printable forms if the public endpoint stabilizes.
13. Export 10-25 curated official public fixtures for committed demo/test use.
14. Build synthetic negative coverage for the highest-risk mismatch cases.
15. Implement reviewer-policy queue routing only after raw verdicts and exports are stable.
16. Update README, `MODEL_ARCHITECTURE.md`, `MODEL_LOG.md`, `docs/performance.md`, `TRADEOFFS.md`, and `DEMO_SCRIPT.md` around the final measurement story.
17. Redeploy only after local OCR/evaluation changes pass.

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

- [x] Update README first sentence so it clearly says the app triages COLAs Online-style applications and identifies labels that appear out of compliance.
- [ ] Put the time-savings/business case near the top of README:
  - TTB 2026 label applications received to date.
  - Sarah's 5-10 minute simple-review estimate.
  - Annualized reviewer-hour estimate.
- [ ] Add the official public COLA sampling methodology to README if not already current.
- [x] Add OCR experimentation strategy to README.
- [x] Add `MODEL_ARCHITECTURE.md` with end-to-end Mermaid diagrams, current measured model layers, and the 60/20/20 trained-classifier plan.
- [x] Update `TRADEOFFS.md` with the simplified mission: OCR proof first, legal reasoning later.
- [x] Update `TRADEOFFS.md` with the measured OCR engine sweep and OpenVINO/EC2 m7i future optimization path.
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
