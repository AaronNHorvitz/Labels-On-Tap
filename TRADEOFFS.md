# TRADEOFFS.md — Labels On Tap

**Project:** Labels On Tap
**Canonical deployment URL:** `https://www.labelsontap.ai`
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Document purpose:** Explain the major product, architecture, data, security, and regulatory trade-offs made to deliver a working prototype within the take-home deadline.

---

## 1. Executive Summary

Labels On Tap is a **local-first, source-backed alcohol label preflight prototype** for TTB-style Certificate of Label Approval (COLA) review.

The prototype is intentionally scoped around the highest-value reviewer workflow:

```text
Upload label artwork + expected application fields
  → run local OCR / fixture OCR fallback
  → compare label text to application data
  → apply deterministic source-backed rules
  → return Pass / Needs Review / Fail
  → show evidence and reviewer action
```

The core trade-off is deliberate:

> We prioritized a working, deployed, auditable reviewer-support application over attempting to implement every possible federal beverage-alcohol rule before the deadline.

The repository includes a large legal/research corpus and source-backed rule matrix to demonstrate how the rule system can scale. The runtime MVP implements a focused subset of rules that are valuable, demoable, and feasible within the sprint.

---

## 2. Product Scope Trade-Offs

### 2.1 Preflight Support, Not Final Agency Action

**Decision:** Labels On Tap returns **Pass**, **Needs Review**, or **Fail Candidate / Fail** style results. It does not claim to approve, reject, or legally certify a COLA application.

**Why:** Many TTB label issues are deterministic, such as exact government-warning text or prohibited abbreviations. Others require human/legal context, such as health claims, misleading geographic impressions, formula/SOC issues, or image-quality ambiguity.

**Implication:** The tool is framed as reviewer support and pre-submission/pre-review triage, not a replacement for TTB specialists or legal counsel.

---

### 2.2 Focused Active Rule Set

**Decision:** The MVP prioritizes a focused set of active rules:

```text
- Brand name fuzzy matching
- Country of origin check for imports
- Government warning exact text
- Government warning heading capitalization
- Government warning boldness routed to Needs Review
- ABV / A.B.V. prohibited alcohol-content wording
- Malt beverage 16 fl. oz. → 1 Pint rule
- OCR low-confidence / image-quality Needs Review
```

**Why:** These rules map directly to common reviewer tasks and stakeholder pain points. They also produce clear demo outcomes: Pass, Fail, and Needs Review.

**What is deferred:** Full wine appellation validation, full formula-to-label reconciliation, complete semi-generic wine-name logic, absinthe/thujone support validation, health-claim legal analysis, geospatial AVA analysis, and full typography measurement.

**Implication:** The legal corpus captures many more criteria than the MVP actively enforces. Those criteria are documented as future rules or Needs Review heuristics.

---

### 2.3 One-Click Demo Before Full Manual Batch Workflow

**Decision:** The MVP includes one-click evaluator demos using deterministic fixtures. Manual upload exists for the single-label workflow. Full manual multi-file batch upload is valuable but can be deferred if time is tight.

**Why:** Evaluators should be able to see the product’s value immediately without hunting for label images or constructing manifests.

**Implication:** The one-click demo proves the rule engine and UX path. Manual batch upload can be added once the core deployed app is stable.

---

## 3. Architecture Trade-Offs

### 3.1 Local-First OCR Instead of Hosted ML APIs

**Decision:** The app does not call OpenAI, Anthropic, Google Cloud Vision, Azure Vision, AWS Textract, or any hosted OCR/ML service at runtime.

**Why:** The stakeholder notes identify outbound ML endpoints as a serious infrastructure risk. A prior vendor pilot was blocked by Treasury firewall constraints. A local-first architecture is safer and more aligned with the assignment.

**Implication:** OCR and validation run inside the application environment. Runtime behavior does not depend on external inference services.

---

### 3.2 docTR / Local OCR with Fixture OCR Fallback

**Decision:** The architecture uses a local OCR adapter, with docTR as the primary OCR candidate, plus a deterministic fixture OCR fallback for generated demo/test labels.

**Why:** docTR supports local OCR with text geometry and confidence-style outputs. However, OCR can be slower, environment-sensitive, and less deterministic than pure rule tests. The fixture fallback guarantees that one-click demos and tests remain stable.

**Implication:** Demo fixtures can use known OCR text while real uploads still exercise the local OCR path. The UI should clearly indicate whether a result came from fixture ground truth or local OCR.

---

### 3.2.1 Measured OCR Engine Sweep Before Runtime Promotion

**Decision:** Alternate OCR engines such as PaddleOCR and OpenOCR/SVTRv2 should be evaluated as experimental local adapters before they are allowed to replace docTR in the deployed app.

**Why:** The curved-text research strongly suggests that modern pre-trained OCR systems may handle cylindrical, circular, rotated, and irregular label text better than the current baseline. However, the assignment rewards a working, reliable prototype. A promising model should not become the production path until it wins on the same public COLA calibration data and stays inside the latency budget.

**Candidate order:**

```text
1. docTR baseline
2. PaddleOCR / PP-OCR local adapter
3. OpenOCR / SVTRv2 local adapter
4. Combined OCR evidence, if two engines find complementary text
```

**Promotion gate:**

```text
- local/self-hosted inference only,
- normalized OCR output with text, boxes, confidence, source, and timing,
- better field-match rates on the calibration set,
- no worse false-clear behavior on synthetic known-bad fixtures,
- measured p50/p95/worst-case latency,
- clean dependency and deployment story,
- rollback to docTR if the engine fails or is too slow.
```

**Implication:** The app can pursue better OCR aggressively without destabilizing the deployed demo. Until a candidate wins, docTR remains the safe runtime baseline.

---

### 3.2.2 Graph Scorer as Post-OCR Evidence, Not OCR Replacement

**Decision:** The graph-aware experiment remains a post-OCR evidence scorer. It does not replace the image-to-text OCR engine.

**Why:** OCR engines and graph scorers solve different problems. PaddleOCR/OpenOCR can improve what text is read from a label image. The graph scorer can improve how OCR fragments are assembled and matched to expected application fields. These layers can stack, but they should be measured independently.

**Current evidence:** The first safety-weighted graph scorer improved F1 from `0.7714` to `0.8714` and lowered false-clear rate from `0.0439` to `0.0132` on the initial 100-application calibration test split with shuffled negative examples.

**Implication:** The graph scorer is promising but remains experimental until it is tested on a larger calibration split and then a locked holdout. It should not be wired into the deployed default path without a CPU latency and false-clear check.

---

### 3.2.3 OpenVINO / EC2 m7i Optimization Is a Future Path

**Decision:** ONNX/OpenVINO/INT8 optimization should be documented as a future deployment path, not claimed as current live performance.

**Why:** The research brief identifies a plausible CPU acceleration path on Intel Sapphire Rapids / AWS `m7i` hardware using OpenVINO and low-precision inference. The current public demo runs on AWS Lightsail, not a guaranteed `m7i` instance with Intel AMX exposure. Therefore, sub-second CPU OCR claims are hypotheses until measured on the actual target hardware.

**Implication:** If PaddleOCR or OpenOCR wins the local calibration benchmark but is too slow on the current VM, the next infrastructure step is an EC2 `m7i` test with ONNX/OpenVINO export and latency measurement. That path should be considered production hardening, not Monday's default runtime.

---

### 3.3 No Large Vision-Language Models

**Decision:** The prototype avoids large VLMs.

**Why:** The stakeholder latency target is approximately five seconds per label. VLMs are too heavy for a small CPU-only VM and unnecessary for the core task, which is field matching, OCR, and deterministic rules.

**Implication:** The architecture emphasizes OCR + regex + fuzzy matching + source-backed rule checks rather than generalized visual reasoning.

---

### 3.4 FastAPI + Jinja2 + HTMX Instead of React or Streamlit

**Decision:** The app uses FastAPI with server-rendered Jinja2 templates and HTMX-style polling.

**Why:** This keeps the app deployable, simple, and robust. React would add build-system overhead. Streamlit would be fast for a demo but weaker for a deployed, asynchronous, source-backed workflow.

**Implication:** The UI remains simple and accessible: upload, run demo, review results, export CSV.

---

### 3.5 Filesystem Job Store Instead of Database

**Decision:** Job state and results are stored in local filesystem directories and JSON files.

**Why:** A database adds migration and concurrency complexity. SQLite can encounter locking issues under concurrent writes. For a prototype handling small demo batches and reviewer-visible output, JSON job artifacts are easier to inspect and debug.

**Implication:** A production system should move to PostgreSQL or another approved persistent store with audit logging, retention policy, and identity controls.

---

### 3.6 Docker + Caddy on a VM Instead of Serverless

**Decision:** Deploy to a conventional x86_64 VM using Docker Compose and Caddy.

**Why:** OCR models and image processing are CPU/memory-sensitive. Serverless platforms can introduce cold starts, memory limits, request timeouts, and model-loading instability.

**Implication:** A VM gives full control over CPU, memory, ports, TLS, model cache, Docker, and logs. Caddy handles HTTPS and reverse proxying for `www.labelsontap.ai`.

---

## 4. Data Trade-Offs

### 4.1 Synthetic Negative Fixtures Instead of Rejected COLA Corpus

**Decision:** The test/demo dataset uses deterministic synthetic negative fixtures generated from source-backed rules.

**Why:** True rejected or “Needs Correction” COLA applications are not generally available through the public registry. Public records are appropriate for approved, expired, surrendered, or revoked COLAs, but not for confidential pending/denied application data.

**Implication:** The app does not claim to train on or possess a hidden rejected-label corpus. Instead, it uses:

```text
- generated synthetic failure cases,
- generated clean/pass cases,
- optional public approved labels for OCR realism,
- public-source legal/regulatory research for rule definitions.
```

---

### 4.2 Public COLA Data Is Optional, Not Required for Tests

**Decision:** Core tests do not depend on downloading public COLA records.

**Why:** Tests should be deterministic, offline-safe, and fast. Public COLA records are useful for realism but should not block the build, CI, or evaluator demo.

**Implication:** Public approved COLA examples may be curated later, but the required demo/test fixtures are generated locally.

---

### 4.3 Deterministic Stratified Sampling Instead of Ad Hoc Examples

**Decision:** Public COLA evaluation records are selected with a deterministic, two-stage stratified sampling procedure rather than by hand-picking labels that look convenient.

**Method:** The sampling frame is the public TTB COLA Registry over a fixed date range. Stage 1 selects business-day clusters within each month using a fixed pseudo-random seed. Stage 2 samples applications without replacement from the imported daily search-result pool, balancing across month, broad product family, and imported/domestic source buckets where those fields are available.

**Why:** A take-home prototype needs enough official examples to prove the OCR/form-matching workflow without pretending to be a production statistical study. Seeded sampling makes the corpus reproducible. Monthly strata reduce simple recency bias. Secondary strata improve coverage across product/source types. Sampling without replacement prevents duplicated applications from inflating evaluation confidence.

**Implication:** The resulting corpus is stronger than a hand-picked demo set, but it is still not a complete population study. It is a practical stratified cluster sample from public registry exports, not a simple random sample of every COLA application. It also cannot include confidential pending, denied, or Needs Correction applications.

**Current local result:** Direct TTB registry exports produced `810` parsed public forms and `1,433` discovered label-panel attachment records. A May 2 audit found that the previously saved direct-registry attachment files were HTML error pages rather than valid raster images, so those attachment rows were marked pending for future redownload. While TTBOnline.gov was unavailable/resetting, the COLA Cloud development bridge produced a separate 1,500-record stratified plan from 7,788 candidates and a 100-record/169-image local docTR calibration set. Bulk data remains under gitignored `data/work/`, and all image paths are validated before being treated as OCR-ready.

---

### 4.4 Commercial Public-COLA Data as Development Fallback

**Decision:** COLA Cloud may be used as a paid, development-only public-data source for building a local OCR evaluation corpus when `TTBOnline.gov` / the Public COLA Registry is unavailable or unstable.

**Why:** The project needs real label images to evaluate local OCR and field matching. During the sprint, the public TTB registry and attachment endpoints became unavailable/resetting, while COLA Cloud offers access to public COLA records and label images derived from the same public registry. The cost of the Pro tier is small relative to the take-home risk, and the spend avoids continued automated requests against an unstable government system.

**Provider context:** COLA Cloud documents public COLA data coverage, label images, API access, and a bulk-data schema. Its pricing page lists a Pro tier at `$99/month` with higher list/detail quotas. COLA Cloud also documents that its own OCR enrichment uses Google Vision, so provider OCR text is treated as third-party reference data, not as Labels On Tap's local OCR result.

**Allowed use:**

```text
- local development corpus creation,
- local OCR smoke tests and benchmark runs,
- comparison of our local OCR output against application fields,
- manual/automated download of public label images into gitignored data/work/,
- optional use of provider OCR text as a silver-label diagnostic reference.
```

**Not allowed use:**

```text
- deployed runtime dependency,
- hosted OCR dependency,
- replacing local docTR/fixture OCR,
- treating COLA Cloud OCR as our model's measured accuracy,
- committing bulk purchased data or API keys,
- sending candidate/user uploads to COLA Cloud.
```

**Security posture:** API keys must live only in `.env` or local shell environment variables and must never be committed. Bulk downloads, cached API responses, images, and evaluation outputs stay under gitignored `data/work/`. If an API pull is used, it should be logged with source, timestamp, query parameters, counts, and provider plan so the sample can be reproduced or explained.

**Data governance posture:** COLA Cloud is a pragmatic fallback over a weekend outage, not the product architecture. The README and submission notes should state that the deployed prototype remains local-first and can run without COLA Cloud; the commercial data source was used only to obtain public example records/images for OCR evaluation when TTBOnline.gov was unavailable.

**Evaluation design:** The preferred final measurement corpus is 3,000 public
COLA applications split into exactly 1,500 calibration/tuning records and 1,500
locked holdout records. The calibration split is allowed to influence OCR
preprocessing, field normalization, and pass/review thresholds. The holdout
split is not used for tuning; it is reserved for the final field-match estimates.
At `n = 1,500`, the conservative 95% margin of error for a binary proportion is
about `+/- 2.5` percentage points. This is a sampling margin for the held-out
evaluation, not a production guarantee.

**Migration plan after paid access:**

```text
1. Archive current raw TTB pull artifacts under data/work/public-cola/archive/.
2. Keep synthetic fixtures under data/fixtures/demo/ and official/commercial public corpus under data/work/.
3. Add COLA Cloud API credentials to .env only.
4. Pull a bounded evaluation subset with logged query parameters and no runtime coupling.
5. Download/validate images, then run local OCR through the existing evaluator.
6. Export only a tiny, reviewed fixture subset if needed; never commit bulk purchased data.
```

**Implication:** This path protects the sprint from government-site downtime while preserving the assignment's core architectural promise: Labels On Tap runs its own OCR and deterministic validation locally.

---

### 4.5 Legal Corpus as Provenance, Not Runtime Burden

**Decision:** The repository includes a `research/legal-corpus/` directory and source-backed criteria matrix.

**Why:** The legal corpus demonstrates that implemented rules trace to public law, regulation, guidance, stakeholder requirements, or research-derived heuristics.

**Implication:** The corpus is not meant to imply that every possible rule is fully implemented in the MVP. It is the foundation for scaling from the active MVP rules to a larger production rule set.

---

## 5. Validation Trade-Offs

### 5.1 Strict Rules vs. Fuzzy Rules

**Decision:** The rule engine separates strict compliance checks from fuzzy matching.

**Strict examples:**

```text
- Government warning exact text
- GOVERNMENT WARNING: capitalization
- ABV / A.B.V. prohibited wording
- Malt beverage 16 fl. oz. → 1 Pint rule
```

**Fuzzy examples:**

```text
- Brand name
- Fanciful name
- Country of origin where OCR noise is possible
```

**Why:** Dave’s stakeholder feedback makes clear that harmless casing or punctuation differences should not create false failures. Jenny’s warning-statement concerns require exact matching for specific fields.

**Implication:** The app applies strictness only where appropriate.

---

### 5.2 Boldness Is Needs Review, Not Hard Fail

**Decision:** The MVP does not make a definitive font-weight determination from arbitrary raster images.

**Why:** Bold detection from JPG/PNG label artwork is brittle. Lighting, compression, DPI, glare, and image scaling can make stroke-width estimates unreliable.

**Implication:** The app strictly validates warning text and heading capitalization, then routes boldness to **Needs Review** with a clear message:

```text
Manual typography verification required. This prototype verifies warning text and capitalization but does not make a definitive font-weight determination from raster images.
```

---

### 5.3 Needs Review Is a First-Class Outcome

**Decision:** Not every issue becomes Pass or Fail.

**Why:** Many regulatory issues are contextual, subjective, or image-limited. A confident but wrong automated failure could make the tool less useful to reviewers.

**Implication:** The app routes ambiguous, low-confidence, or legally contextual issues to **Needs Review**.

---

## 6. Upload and Security Trade-Offs

### 6.1 JPEG/PNG Label Images Only for MVP

**Decision:** The MVP accepts label artwork as `.jpg`, `.jpeg`, or `.png`.

**Why:** Label artwork validation is image-based. PDF parsing would add complexity and is not necessary for the core prototype.

**Implication:** PDF, TIFF, HEIC, WEBP, executable, and suspicious files should be rejected or deferred.

---

### 6.2 No ZIP Upload in MVP

**Decision:** ZIP upload is deferred.

**Why:** ZIP support introduces security concerns: ZIP bombs, nested folders, path traversal, hidden files, and inconsistent OS-generated files.

**Implication:** Batch support can use multi-file upload plus manifest CSV/JSON. If time is tight, one-click batch demo demonstrates the workflow without ZIP risk.

---

### 6.3 Basic Public Prototype Hardening

**Decision:** The public prototype should implement basic upload defenses:

```text
- extension allowlist,
- magic-byte validation,
- max file size,
- randomized internal filenames,
- original filename stored only as metadata,
- Pillow image-open validation,
- safe job directories.
```

**Why:** The deployed app is publicly reachable and accepts user-supplied files.

**Implication:** This is not a production federal security posture, but it is responsible prototype hardening.

---

## 7. Performance Trade-Offs

### 7.1 Per-Label SLA vs. Full Batch Completion

**Decision:** The app distinguishes per-label processing from total batch completion.

**Why:** A 200-image batch cannot realistically finish in five seconds on a small CPU VM. The stakeholder concern is that the user should not stare at a frozen interface.

**Implication:** The UI should show immediate progress and completed rows as they finish.

---

### 7.2 Measured Performance Over Marketing Claims

**Decision:** The documentation should avoid unmeasured claims such as “sub-second OCR” or “guaranteed five seconds.”

**Why:** Actual performance depends on VM size, image complexity, OCR model warmup, and Docker environment.

**Implication:** Use measured p50/p95 numbers in `docs/performance.md` once available.

---

## 8. Documentation Trade-Offs

### 8.1 Root Docs for Evaluators, Detailed Docs for Review

**Decision:** Keep evaluator-facing files at the root and detailed files under `docs/` and `research/`.

**Root files:**

```text
README.md
PRD.md
TASKS.md
ARCHITECTURE.md
TRADEOFFS.md
DEMO_SCRIPT.md
PERSONALITIES.md
```

**Detailed docs:**

```text
docs/
research/legal-corpus/
data/source-maps/
```

**Why:** Evaluators need a fast path, while the repository still needs to demonstrate technical rigor.

---

### 8.2 Research Language Sanitized for Federal Audience

**Decision:** Public docs should avoid aggressive OSINT language.

**Use:**

```text
public-source regulatory research
source-backed criteria
fixture provenance
post-market public records
risk-based review heuristics
```

**Avoid:**

```text
exploit
loophole
bypass
leaked notices
compliance graveyard
reverse-engineering enforcement algorithms
```

**Why:** The repo should read like a professional federal-facing prototype, not an adversarial scraping project.

---

## 9. Deferred Production Features

The following are intentionally deferred:

```text
- production authentication / SSO / RBAC,
- persistent enterprise database,
- formal audit logging,
- retention/legal-hold policy,
- direct COLAs Online integration,
- live TTB Public COLA Registry crawling,
- full Form 5100.31 parity,
- full wine appellation validation,
- full formula/SOC reconciliation,
- full semi-generic wine-name workflow,
- full absinthe/thujone support validation,
- full health-claim legal analysis,
- definitive font-size/boldness/physical-measurement validation,
- ZIP upload,
- GPU inference,
- hosted OCR/ML APIs.
```

These are not ignored. They are documented as future hardening or production expansion work.

---

## 10. Production Hardening Roadmap

A production-grade version would add:

```text
- identity provider integration,
- role-based reviewer permissions,
- audit logs for every result,
- signed result artifacts,
- approved retention and deletion policy,
- PostgreSQL or approved database,
- malware scanning for uploads,
- rate limiting,
- queue-backed worker pool,
- robust batch upload and retry behavior,
- deployment monitoring,
- formal accessibility review,
- NIST SSDF-aligned secure development documentation,
- ATO/FedRAMP-style infrastructure hardening if deployed in a federal environment.
```

---

## 11. Final Position

Labels On Tap intentionally balances ambition with deliverability.

The prototype demonstrates:

```text
- a working deployed label preflight app,
- local-first OCR architecture,
- source-backed validation rules,
- deterministic demo/test fixtures,
- simple reviewer UX,
- responsible upload handling,
- clear Pass / Needs Review / Fail outcomes,
- honest limitations.
```

The MVP does not pretend to solve all TTB label review. It demonstrates a credible, extensible path for reducing routine reviewer workload while preserving human judgment where law, context, or image quality require it.
