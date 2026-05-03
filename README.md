# Labels On Tap

**Labels On Tap is designed to triage COLAs Online-style submissions and identify alcohol labels that appear out of compliance.**

[![Live Demo](https://img.shields.io/badge/Demo-www.labelsontap.ai-blue?style=for-the-badge)](https://www.labelsontap.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Jinja2%20%2B%20HTMX-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Caddy-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

> **Deployment target:** `https://www.labelsontap.ai`
> **Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
> **Status:** take-home prototype; reviewer-support tool, not an official TTB/Treasury system.

---

## Model Posture: Conservative Triage

COLAs Online is an Internet-based system that allows registered industry members to apply online for a certificate of label approval, certificate of exemption from label approval, or distinctive liquor bottle approval. Labels On Tap is a reviewer-support triage assistant for that workflow: it compares application data against submitted label artwork, identifies likely compliance problems, and routes uncertain cases to human review.

The highest-risk failure is a **false clear**: a problematic label incorrectly marked as `Pass`. The prototype therefore favors catching possible problems over automatically clearing borderline cases:

```text
clear evidence matches       -> Pass
clear source-backed problem  -> Fail
uncertain OCR/rule evidence  -> Needs Review
```

In plain terms: the tool should quickly clear obvious matches, flag obvious problems, and send ambiguous cases to a human reviewer with the evidence attached. Extra human review is acceptable; accidentally passing a bad label is not.

The evaluation language follows that product posture:

| Metric | Plain-English Meaning |
|---|---|
| Bad-label catch rate | Of known bad or intentionally mutated examples, how many were routed to `Fail` or `Needs Review`? |
| False-clear rate | Of known bad examples, how many were incorrectly marked `Pass`? This is the primary safety metric. |
| Reviewer-escalation rate | How often does the tool choose `Needs Review` instead of pretending it is certain? |
| Clean-label pass rate | Of known clean examples, how many were correctly cleared? |
| Field extraction accuracy | How often OCR found the right brand, class/type, ABV, net contents, country of origin, or warning text? |
| Per-label latency | Whether useful feedback returns near the stakeholder target of about five seconds per label after warmup. |

Any sprint metrics should be read as prototype validation, not production certification. The current public-data work uses public COLA registry records as a realistic, safe proxy for COLAs Online application data and uploaded label images.

A production-grade evaluation would use a larger random or stratified holdout set across product types, statuses, dates, form versions, and known regulatory/form-change boundaries. For this take-home, the practical goal is narrower: prove that public COLA application data and label images can be parsed, OCR'd, compared, and evaluated with conservative human-review routing.

---

## Public COLA Sampling Methodology

The public COLA evaluation corpus is built with a deterministic, two-stage stratified sampling procedure. The goal is not to claim production statistical certification. The goal is to avoid cherry-picking while creating a reproducible official-data corpus large enough to test OCR/form matching.

Sampling frame:

```text
Public source class: public COLA records and public label images
Direct source: TTB Public COLA Registry when reachable
Development bridge: COLA Cloud API when TTBOnline.gov is unavailable
Date range: 2025-05-01 through 2026-04-30
Primary strata: month approved/completed
Secondary strata: product family, imported/domestic bucket, and single/multi-panel image complexity
Randomness: seeded pseudo-random sampling
Replacement: without replacement
```

Stage 1 uses seeded cluster sampling by date: the script chooses business days within each month using a fixed seed, then imports public records for those days. Stage 2 samples applications without replacement from that imported pool, using deterministic balancing across secondary strata such as broad product family, imported/domestic source bucket, and single-panel versus multi-panel label complexity.

The current local data story has two branches:

| Branch | Purpose | Current Result |
|---|---|---|
| Direct TTB Public Registry ETL | Preserve the official printable-form path and parser. | `810` parsed public COLA forms and `1,433` discovered attachment records; attachment endpoint was returning HTML errors during the May 2 audit, so invalid files were marked pending rather than treated as images. |
| COLA Cloud public-data bridge | Obtain validated public label rasters while TTBOnline.gov was unavailable/resetting. | `1,500` selected applications from `7,788` candidates, with the first `100` details and `169` label images evaluated by local docTR. |

COLA Cloud is not a runtime dependency and its hosted OCR enrichment is not used as Labels On Tap's measured model output. It is a development-only source for public records/images. The deployed app still runs local OCR or deterministic fixture OCR. Bulk forms, API responses, image files, SQLite data, and OCR outputs remain under gitignored `data/work/`.

The current 100-record calibration result is intentionally conservative: all applications route to `Needs Review` unless every attempted field is strongly supported. After fixing the COLA Cloud mapping for `abv`, `volume`, and `volume_unit`, the measured field results are:

| Field | Attempted | Match Rate |
|---|---:|---:|
| Brand name | 100 | 71% |
| Fanciful name | 100 | 65% |
| Class/type | 100 | 49% |
| Alcohol content | 94 | 91.49% |
| Net contents | 86 | 83.72% |
| Country of origin | 38 | 78.95% |

The next statistical target is a `3,000`-application public-data corpus split into exactly `1,500` calibration/tuning records and `1,500` locked holdout records. A no-network plan-only check has already verified that the current candidate pool can produce this exact split without replacement. The calibration split is for OCR preprocessing, field-normalization, and threshold decisions. The holdout split is reserved for the final reported estimate after tuning is frozen.

For a binary proportion on the `1,500`-record holdout, the conservative 95% margin of error is approximately:

```text
1.96 * sqrt(0.25 / 1500) = 0.0253
```

That is about `+/- 2.5 percentage points` before finite-population correction, and about the same after correction against an annual population near `150,000` COLA applications. This is a margin-of-error statement for the locked holdout estimate, not a claim that production accuracy is guaranteed.

This design gives the project a cleaner evidence story than hand-picked examples:

```text
- reproducible because seeds and date ranges are recorded,
- stratified by month to reduce simple recency bias,
- post-stratified by product/source buckets to improve coverage,
- sampled without replacement to avoid duplicated applications,
- honest about public-registry limits, transient attachment failures, and validated-image counts.
```

Limitations remain. This is not a simple random sample of all COLA applications; it is a practical stratified cluster sample from public registry exports. It excludes confidential pending, denied, and Needs Correction applications. Synthetic negative fixtures are still required to test rejection cases that are not publicly available as a clean corpus.

---

## OCR Experimentation Strategy

The OCR work is being evaluated in layers rather than treated as one all-or-nothing model choice. That matters because the review workflow has two different technical problems:

```text
Problem 1: read difficult label text from images
Problem 2: decide whether the read text supports the application fields
```

Labels On Tap currently uses local docTR OCR as the baseline OCR engine and a fixture OCR fallback for deterministic demos. Alternate engines are being measured in an isolated OCR sweep, not dropped directly into the deployed app.

| Layer | Role | Current Status | Promotion Gate |
|---|---|---|---|
| docTR | Current local OCR baseline with geometry/confidence output. | Implemented and measured on the first 100 public COLA calibration records. | Remains default unless another local engine clearly beats it. |
| PaddleOCR / PP-OCR | Candidate local OCR engine with orientation, detection, and recognition support for irregular label imagery. | 30-image smoke shows higher F1/accuracy/recall than docTR, with a higher false-clear rate. | Must keep the F1 lift on a larger calibration set while controlling false clears with field-specific thresholds/rules. |
| OpenOCR / SVTRv2 | Candidate zero-shot irregular-text OCR path, especially interesting for curved/cylindrical text. | 30-image smoke is fastest and normalized to the same OCR schema, but lower F1 than docTR/PaddleOCR in the first field-support test. | Must prove whether speed and curved-text handling translate into better field evidence on a larger sample or as supplemental evidence. |
| PARSeq | Scene-text recognizer for irregular crops, tested over OpenOCR-detected boxes. | 30-image crop-recognition smoke is fast, including autoregressive mode, but lower F1 than docTR/PaddleOCR/OpenOCR in this setup. | Must be treated as a recognizer-stage experiment unless paired with a detector and measured end-to-end. |
| ASTER | Scene-text recognizer with flexible rectification, tested over OpenOCR-detected boxes. | 30-image crop-recognition smoke is very fast and produced zero false clears, but lower recall/F1 than docTR/PaddleOCR in this setup. | Must be treated as a recognizer-stage experiment unless paired with a detector and measured end-to-end. |
| FCENet + ASTER | Arbitrary-shape detector using Fourier contour polygons, paired with ASTER recognition. | 30-image detector-plus-recognizer smoke ran successfully but was too slow on CPU and had low field-support F1. | Useful research checkpoint, not a runtime candidate unless optimized or GPU-backed. |
| Graph-aware evidence scorer | Post-OCR model that scores whether OCR fragments support a target field. | Experimental proof exists under `experiments/graph_ocr/`. | Can only be promoted if it improves matching while lowering or preserving the false-clear rate on held-out data. |
| HO-GNN / TPS / SVTR custom vision model | Long-term curved-text research path. | Future state only. | Requires annotation strategy, training/evaluation plan, CPU inference proof, and deployment packaging. |

Early OCR-engine metrics are deliberately labeled as smoke results. Small sample sizes increase variance, so the 20-application / 30-image comparison is directional only and must not be treated as a stable engine ranking. That said, the current PaddleOCR F1 lift is meaningful enough to keep PaddleOCR in contention, not reject it.

This sequencing keeps the product disciplined. Better OCR engines can improve what text is read. The graph-aware scorer can improve how OCR fragments are assembled into field evidence. Deterministic validation rules still decide `Pass`, `Needs Review`, or `Fail`.

The curved-text research brief changed the experimental priority in one practical way: the next serious attempt should start with mature pre-trained OCR systems such as PaddleOCR or OpenOCR rather than training a custom curved-text model from scratch. Modern OCR systems trained on large distorted-text corpora may provide useful zero-shot performance on alcohol labels, avoiding the immediate need for custom polygon-level annotation.

Runtime claims remain measured, not assumed. OpenVINO/ONNX/INT8 optimization on an Intel `m7i`-class EC2 instance is a promising production path, especially because those CPUs can accelerate low-precision matrix operations. The live demo currently runs on AWS Lightsail, so OpenVINO/AMX performance is documented as a future optimization path until it is benchmarked on the actual deployment hardware.

Before any OCR engine becomes the default runtime path, it must pass the same checklist:

```text
- local/self-hosted inference only,
- no hosted OCR or hosted ML API dependency,
- normalized OCRResult output with text, boxes, confidence, source, and timing,
- 10-image smoke benchmark,
- 100-application calibration benchmark,
- field-level match-rate comparison against docTR,
- p50/p95/worst-case latency measurement,
- false-clear check on synthetic known-bad fixtures,
- documented failure modes and rollback plan.
```

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

## Future State: Graph-Aware OCR

The current prototype treats OCR as a local engine plus deterministic field matching. A strong future direction is to add a geometry-aware OCR layer for highly curved, circular, spherical, fragmented, or distorted label text.

The core idea is to preserve OCR text boxes from engines such as PaddleOCR or docTR, then reason over those boxes as a graph:

```text
label panel image
  -> local OCR text boxes
  -> geometry-aware graph / hypergraph reassembly
  -> field-aware text candidates
  -> deterministic application-field comparison
```

This is especially relevant for alcohol labels because key regulatory text may appear on curved collars, circular keg labels, wraparound bottle panels, or multi-panel artwork. Standard OCR may detect individual fragments but lose reading order or fail to connect pieces that belong to the same warning statement, ABV statement, brand, or net-contents block.

A practical version of this architecture would start with a deterministic graph layer rather than immediately training a custom model:

- nodes: OCR text boxes, words, or line fragments,
- edges: geometric proximity, baseline angle, reading-order direction, panel membership, and OCR confidence,
- hyperedges: shared higher-order relationships such as same warning block, same curved baseline, same label panel, same candidate field, or same government-warning phrase,
- output: reassembled text candidates with provenance back to the original panel and boxes.

This could later become a Higher-Order Graph Neural Network or Hypergraph Neural Network research path. The near-term engineering value is that the graph layer can improve curved-text and fragmented-text reassembly while preserving the current conservative triage posture: it may improve evidence gathering, but deterministic rules still decide `Pass`, `Needs Review`, or `Fail`.

A first experimental version of this near-term graph layer now exists under
`experiments/graph_ocr/`. It trains a small PyTorch graph-aware evidence scorer
over cached local OCR boxes. On the initial 100-application calibration test,
the safety-weighted GPU run improved F1 from `0.7714` to `0.8714` and reduced
false-clear rate from `0.0439` to `0.0132` on shuffled negative examples. This
is a proof of signal, not a final accuracy claim; the full HO-GNN/TPS/SVTR
architecture below remains the longer research path.

Relevant research and implementation links:

| Area | Link | Why It Matters |
|---|---|---|
| PaddleOCR local OCR, orientation, and unwarping | [PaddleOCR OCR pipeline docs](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) | Candidate local OCR engine with document orientation/unwarping options. |
| OpenOCR / SVTRv2 | [OpenOCR repository](https://github.com/Topdu/OpenOCR) | Candidate zero-shot irregular-text OCR engine to benchmark after PaddleOCR. |
| PARSeq | [PARSeq repository](https://github.com/baudm/parseq) | Candidate scene-text recognizer for irregular crops; tested as a recognizer-stage experiment over detected label text boxes. |
| ASTER | [MMOCR ASTER model docs](https://mmocr.readthedocs.io/en/dev-1.x/textrecog_models.html#aster) | Candidate scene-text recognizer with flexible rectification; tested as a recognizer-stage experiment over detected label text boxes. |
| FCENet | [MMOCR FCENet model docs](https://mmocr.readthedocs.io/en/latest/api/generated/mmocr.models.textdet.FCENet.html) and [FCENet paper](https://arxiv.org/abs/2104.10442) | Arbitrary-shape text detector using Fourier contour embeddings; tested with ASTER recognition. |
| OpenVINO optimization | [OpenVINO documentation](https://docs.openvino.ai/) | Future CPU optimization path if an alternate OCR engine wins and needs deployment acceleration. |
| Irregular text detection with graph convolution | [Irregular Scene Text Detection Based on a Graph Convolutional Network](https://www.mdpi.com/1424-8220/23/3/1070) | Motivates graph reasoning for distant text components and irregular text shapes. |
| Graph reasoning for scene text recognition | [GRNet: a graph reasoning network for enhanced multi-modal learning in scene text recognition](https://academic.oup.com/comjnl/article/67/12/3239/7760133) | Shows graph reasoning as a modern path for distorted, occluded, and irregular scene text. |
| Arbitrary-shape recognition with self-attention | [On Recognizing Texts of Arbitrary Shapes with 2D Self-Attention](https://huggingface.co/papers/1910.04396) | Supports moving beyond simple left-to-right sequence recognition for irregular text. |
| Scene text rectification | [Robust Scene Text Recognition with Automatic Rectification](https://arxiv.org/abs/1603.03915) | Supports rectification before recognition for irregular text. |
| Hypergraph neural network foundation | [Hypergraph Neural Networks](https://huggingface.co/papers/1809.09401) | General foundation for modeling higher-order relationships beyond pairwise graph edges. |

This is not part of the current measured runtime claim. It is recorded as a future architecture because it directly targets the OCR failure mode most specific to alcohol labels: text that is legal/compliance-critical but physically curved, fragmented, or wrapped around the package.

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

## Phase 1 Screening Criteria

The Phase 1 screen-out list is captured in [PHASE1_REJECTION.md](PHASE1_REJECTION.md). In this prototype, "rejection" means a reviewer-facing **Fail** or **Needs Review** reason that would prevent the application from moving cleanly through automated preflight. It is not a claim that the prototype makes final legal determinations.

The list is interview-derived:

- Sarah Chen grounds the application-to-label matching workflow: agents compare application data to label artwork and need faster routine verification.
- Jenny Park grounds strict warning checks and image-readability concerns: warning wording must be exact, the heading must be all caps/bold, and poor images can prevent review.
- Dave Morrison grounds false-rejection guardrails: harmless formatting differences should not be treated as true mismatches.
- Marcus Williams grounds operational intake constraints: the prototype must remain standalone, safe with uploads, and usable without hosted ML/OCR dependencies.

Phase 1 screen-out / Needs Correction reasons:

### Application-Label Mismatch

- Brand name on the label does not match the application.
- Alcohol content / ABV on the label does not match the application.
- Class/type designation on the label does not match the application.
- Net contents on the label do not match the application.
- Bottler/producer name is missing or does not match expected application data.
- Bottler/producer address is missing or does not match expected application data.
- Country of origin is missing for an imported product.
- Country of origin on the label conflicts with the application.
- Fanciful name mismatch, if a fanciful name is present in the application.
- Label artwork does not represent the product/application record being reviewed.

### Government Warning

- Government Health Warning Statement is missing.
- Government warning text is not exact word-for-word.
- Government warning punctuation differs from required wording.
- `GOVERNMENT WARNING:` heading is not all caps.
- `GOVERNMENT WARNING:` heading is not bold.
- Warning text is too small.
- Warning text is buried or not reasonably visible.
- Warning statement is present but unreadable.

### Image Quality

- Label image is too blurry to read.
- Label image is photographed at a bad angle.
- Label image has poor lighting.
- Label image has glare.
- Label image is low contrast or otherwise hard to read.
- Required label areas are cropped, hidden, or not included.
- OCR confidence is too low to safely verify the label.

### Product-Type / Required Element

- Required common label element is missing: brand name.
- Required common label element is missing: class/type designation.
- Required common label element is missing: alcohol content, where required.
- Required common label element is missing: net contents.
- Required common label element is missing: bottler/producer name and address.
- Required common label element is missing: country of origin for imports.
- Required common label element is missing: Government Health Warning Statement.
- Beverage-type-specific requirement is missing or inconsistent for wine, malt beverages, or distilled spirits.
- Distilled spirits label does not include expected spirits fields like class/type, proof/alcohol content, or net contents where applicable.
- Wine-specific fields such as varietal, appellation, or vintage are inconsistent if they appear in the application/label.
- Malt beverage-specific rules are violated, such as net contents expression issues.

### False-Rejection Guardrails

- Cosmetic capitalization differences should not automatically reject the application.
- Harmless punctuation/formatting differences should not automatically reject fuzzy fields like brand name.
- Ambiguous OCR or fuzzy matches should go to Needs Review, not hard Fail.
- The tool must distinguish true mismatch from obvious equivalence, like `STONE'S THROW` vs `Stone's Throw`.

### Operational / Intake

- Uploaded label image format is unsupported.
- Label image file is too large or unusable.
- Batch application row cannot be matched to its label image.
- Application data is incomplete enough that automated comparison cannot be trusted.
- Multiple applications/images are mixed up in a batch.
- The system cannot process fast enough for reviewer workflow. This is not a COLA rejection reason, but it is a tool-adoption failure reason.

The next fixture milestone is test data coverage for every Phase 1 reason: each reason should have at least one synthetic or curated COLA-style application record, one or more paired label images, expected results, and provenance explaining whether the case is source-backed, synthetic negative data, or public registry-derived data.

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

Operational handoff and experiment tracking:

| File | Purpose |
|---|---|
| [HANDOFF.md](HANDOFF.md) | Restart guide for a fresh coding session. |
| [MODEL_LOG.md](MODEL_LOG.md) | OCR and graph-evidence experiment ledger. |
| [TASKS.md](TASKS.md) | Final sprint command center. |
| [docs/performance.md](docs/performance.md) | Measured timings, OCR calibration results, and model metrics. |

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
| Host target | AWS Lightsail Ubuntu VM; portable to EC2 |

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

### Live Deployment

The public demo at `https://www.labelsontap.ai` is currently deployed on AWS using a simple VM-first stack:

```text
AWS Lightsail
Ubuntu VM
Static IPv4
Docker Compose
Caddy
Public DNS
```

The live request path is:

```text
Browser
  -> public DNS
  -> AWS Lightsail static IP
  -> Caddy on ports 80/443
  -> FastAPI app container on port 8000
```

This deployment shape was chosen deliberately for the take-home:

- it mirrors a practical Treasury/AWS hosting posture without adding managed-service sprawl,
- it keeps the runtime local-first because OCR and rule evaluation happen on the VM,
- it keeps the app inspectable and easy to reproduce from the repository,
- it gives automatic HTTPS and apex-to-`www` redirect behavior through Caddy.

The same container stack is portable to EC2 if a later environment needs more control over instance families, storage, or network layout.

### Reference Host Shape

For a VM deployment, the app is designed to run comfortably on:

```text
AWS Lightsail or EC2
Ubuntu Linux
Static IP / Elastic IP
Docker Compose
Caddy
```

DNS:

```text
www.labelsontap.ai  A  <public VM IP>
labelsontap.ai      A  <public VM IP>
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
| Public COLA ETL | Local-only official fixture curation |
| Public approved COLA examples | OCR realism after curated export |

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

Official public COLA examples are collected separately through a local ETL workspace, not by live scraping in the web app:

```bash
python scripts/init_public_cola_workspace.py
python scripts/import_public_cola_search_results.py path/to/search-results.csv --copy-raw
python scripts/fetch_public_cola_forms.py --missing-only --limit 5 --delay 3 --jitter 1
python scripts/parse_public_cola_forms.py --limit 5
python scripts/download_public_cola_images.py --limit 10 --delay 2 --jitter 1
python scripts/export_public_cola_fixtures.py --ttb-id 03235001000005
python scripts/run_public_cola_sampling_job.py --seed 20260503 --target-total 500 --exclude-ttb-id-file data/work/public-cola/sampling/exclusions/seed-20260502-300.txt --resume
```

Bulk ETL data stays in gitignored `data/work/public-cola/`. Reviewed fixtures can be exported to `data/fixtures/public-cola/`. See [docs/public-cola-etl.md](docs/public-cola-etl.md).

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
