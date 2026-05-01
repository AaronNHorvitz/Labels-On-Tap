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

### 4.3 Legal Corpus as Provenance, Not Runtime Burden

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
