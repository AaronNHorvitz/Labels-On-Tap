# ARCHITECTURE.md

# Labels On Tap — System Architecture

**Project:** Labels On Tap
**Repository:** `github.com/AaronNHorvitz/Labels-On-Tap`
**Deployment Target:** `https://www.labelsontap.ai`
**Document Type:** Root-level architecture blueprint
**Status:** Sprint architecture for deployed take-home prototype

---

## 0. Architectural Thesis

Labels On Tap is a **local-first, source-backed alcohol label preflight and reviewer-support prototype** for TTB-style COLA review.

The application compares uploaded alcohol label artwork against structured application data modeled after the COLA / Form 5100.31 workflow. It uses local OCR, deterministic validation rules, fuzzy matching where reviewer judgment is appropriate, and conservative **Needs Review** escalation where the issue is image-limited, legally contextual, or not safely machine-decidable.

The architecture is designed around four non-negotiable constraints from the stakeholder discovery notes:

1. **No hosted ML runtime.** OCR and extraction must run locally because outbound ML endpoints may be blocked in Treasury infrastructure.
2. **Fast per-label feedback.** The app targets approximately five-second feedback per label after OCR warmup, dependent on image complexity and VM resources.
3. **Simple reviewer UX.** The interface must be usable by non-technical and older reviewers with minimal training.
4. **Batch triage.** The app must support high-volume importer-style submissions and show asynchronous progress instead of freezing the browser.

The system is not a final legal decision-maker. It is a preflight and triage tool that helps reviewers identify routine mismatches, deterministic fatal flaws, and source-backed risk signals more quickly.

---

## 1. Design Principles

### 1.1 Local-first over cloud-dependent AI

The runtime application does **not** call OpenAI, Anthropic, Google Cloud Vision, AWS Textract, Azure Vision, or any hosted VLM/OCR service.

All OCR and rule validation run inside the deployed host environment.

### 1.2 Deterministic checks before AI reasoning

The core task is not open-ended visual reasoning. It is mostly:

```text
label artwork text
  + application fields
  + source-backed rules
  → Pass / Needs Review / Fail
```

Rules such as the government warning exact text, alcohol terminology, net contents conversions, and field-to-label matching are better served by OCR, regex, numeric parsing, fuzzy matching, and source-backed rule definitions than by large language model inference.

### 1.3 Human-in-the-loop by design

The app returns three verdicts:

```text
Pass
Needs Review
Fail
```

Verdict policy:

```text
Fail
  Clear deterministic mismatch or source-backed fatal flaw.

Needs Review
  OCR uncertainty, image quality limitation, subjective legal issue,
  source-backed risk heuristic, or manual formatting check.

Pass
  The label appears consistent with the supplied application fields and implemented rules.
```

### 1.4 Source-backed rules, not invented heuristics

Every implemented rule should trace to one of:

```text
federal statute
CFR regulation
TTB guidance
TTB form / circular
court or public precedent
stakeholder requirement
research-derived fixture strategy
```

The repository stores this evidence chain in:

```text
research/legal-corpus/
```

The runtime app only needs a focused subset of rules for the sprint, but the architecture supports scaling the rule set without changing the application design.

### 1.5 Simple deployability

The system is designed to run on a single x86_64 cloud VM with Docker and Caddy:

```text
Browser → Caddy HTTPS → FastAPI app → local OCR + validation → filesystem job store
```

No Kubernetes, no serverless, no separate React build, and no cloud ML APIs are required.

---

## 2. High-Level System Diagram

```text
┌────────────────────────────────────────────────────────────────────┐
│                             Browser                                │
│                                                                    │
│  - Upload one label                                                │
│  - Upload multiple label images                                    │
│  - Run one-click evaluator demos                                   │
│  - Poll batch progress                                             │
│  - Review source-backed results                                    │
└───────────────────────────────┬────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                              Caddy                                 │
│                                                                    │
│  - TLS termination                                                 │
│  - Reverse proxy to FastAPI                                        │
│  - www.labelsontap.ai                                              │
│  - labelsontap.ai → www redirect                                  │
└───────────────────────────────┬────────────────────────────────────┘
                                │ HTTP inside Docker network
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                          FastAPI Web App                           │
│                                                                    │
│  UI Layer                                                          │
│    - Jinja2 templates                                              │
│    - HTMX polling                                                  │
│    - local CSS                                                     │
│                                                                    │
│  API / Route Layer                                                 │
│    - upload routes                                                 │
│    - demo routes                                                   │
│    - job status routes                                             │
│    - CSV export                                                    │
│                                                                    │
│  Job Manager                                                       │
│    - creates job directories                                       │
│    - schedules OCR/validation work                                 │
│    - writes result JSON                                            │
│                                                                    │
│  OCR + Validation Services                                         │
│    - docTR OCR                                                     │
│    - OpenCV/Pillow preflight                                       │
│    - RapidFuzz fuzzy matching                                      │
│    - deterministic rule engine                                     │
│    - source-backed criteria registry                               │
└───────────────────────────────┬────────────────────────────────────┘
                                │ local filesystem
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                        Filesystem Job Store                        │
│                                                                    │
│  data/jobs/{job_id}/                                               │
│    manifest.json                                                   │
│    uploads/                                                        │
│    thumbnails/                                                     │
│    results/                                                        │
│    evidence/                                                       │
│    exports/                                                        │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Runtime Stack

| Layer | Technology | Purpose |
|---|---|---|
| Web framework | FastAPI | Upload handling, route serving, API endpoints, health checks |
| Templates | Jinja2 | Server-rendered pages without a frontend build pipeline |
| UI interactivity | HTMX | Batch progress polling and partial result updates |
| CSS | Local CSS | High-contrast, accessible, no CDN dependency |
| OCR | docTR / PyTorch CPU | Local OCR with text, confidence, and geometry output |
| Image processing | OpenCV-headless + Pillow | Preflight checks, image loading, thumbnails, evidence crops |
| Fuzzy matching | RapidFuzz | Human-tolerant application-vs-label comparisons |
| Validation | Python rules + JSON criteria registry | Deterministic and source-backed checks |
| Job storage | Filesystem JSON | Sprint-safe persistence and batch progress |
| Containerization | Docker | Reproducible deployment |
| TLS / proxy | Caddy | HTTPS for `www.labelsontap.ai` with apex redirect |
| Deployment | x86_64 cloud VM | Local-first OCR runtime with predictable CPU/RAM |

---

## 4. Deployment Architecture

### 4.1 Target deployment

```text
Canonical URL: https://www.labelsontap.ai
Host type: x86_64 Linux VM
Runtime: Docker Compose
TLS: Caddy automatic HTTPS
```

Recommended VM baseline:

```text
CPU: 4 vCPU preferred, 2 vCPU minimum
RAM: 8 GB preferred, 4 GB minimum
Disk: 20 GB+ SSD
Architecture: x86_64
OS: Ubuntu LTS or equivalent Linux distribution
```

The OCR layer is CPU-bound and model-loading sensitive. A dedicated VM is preferred over serverless hosting because serverless cold starts and memory ceilings are poor fits for local OCR models.

### 4.2 Docker services

Sprint MVP can run with two services:

```text
web
  FastAPI app, templates, local OCR, validation, job manager

caddy
  HTTPS reverse proxy
```

Optional future services:

```text
redis
  durable queue for production-scale batch orchestration

worker
  separate OCR worker process/container

postgres
  persistent review history, audit logs, and production metadata
```

### 4.3 Docker Compose shape

```yaml
services:
  web:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
    volumes:
      - ./data:/app/data
    environment:
      - APP_ENV=production
      - DATA_DIR=/app/data
    restart: unless-stopped

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
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

`uvicorn --workers 1` is intentional for the MVP because OCR model state, in-memory job management, and local filesystem progress are simpler and safer in a single application process. Batch jobs are still asynchronous from the user's perspective because work is scheduled in a local executor and results are written incrementally.

---

## 5. Application Runtime Components

### 5.1 Web UI

The UI is server-rendered and intentionally simple.

Primary pages:

```text
GET /                      Home and upload page
GET /jobs/{job_id}          Batch/single job status page
GET /jobs/{job_id}/status   HTMX partial for progress/results
GET /jobs/{job_id}/csv      CSV export
GET /items/{item_id}        Result detail page
GET /health                 Health check
```

Primary UX flows:

```text
1. One-click evaluator demo
2. Single label verification
3. Batch multi-file verification
4. Result review and CSV export
```

### 5.2 One-click evaluator demos

The app should include demo buttons that immediately exercise the system without requiring the evaluator to find or upload files.

Recommended demo buttons:

```text
Run Clean Label Demo
Run Government Warning Failure Demo
Run ABV Failure Demo
Run Malt Net Contents Failure Demo
Run Batch Demo
```

Each demo creates a job from pre-seeded fixture data and redirects to the job results page.

### 5.3 Upload preflight service

Before OCR, uploaded files pass through preflight checks:

```text
extension allowlist
magic-byte validation
file size limits
image readability
filename randomization
path traversal prevention
unsupported type rejection
```

MVP accepted label image types:

```text
.jpg
.jpeg
.png
```

MVP metadata / manifest types:

```text
.csv
.json
```

Unsupported label-artwork types:

```text
.pdf
.tif
.tiff
.heic
.webp
executable files
unknown binary files
double-extension files
```

PDFs may be relevant as research or supporting documents in real-world COLA workflows, but the MVP label-artwork verifier is focused on image uploads.

### 5.4 Job manager

The job manager is responsible for:

```text
creating a job ID
creating job directories
saving sanitized uploads
writing manifest.json
scheduling OCR/validation tasks
writing result JSON atomically
reporting progress to the UI
building CSV export
```

The sprint MVP uses filesystem-first job storage rather than SQLite/PostgreSQL.

Reason:

```text
- avoids SQLite lock contention
- avoids database schema churn during sprint
- makes result files easy to inspect
- supports simple HTMX polling
- is sufficient for 200–300 demo/batch labels on a single VM
```

### 5.5 OCR service

The OCR service wraps docTR behind an adapter interface.

Responsibilities:

```text
load OCR model once
accept normalized image input
return OCR text blocks
return confidence scores
return bounding boxes / geometry where available
record OCR timing
```

Interface shape:

```python
class OCREngine(Protocol):
    def warmup(self) -> None: ...
    def run(self, image_path: Path) -> OCRResult: ...
```

The architecture keeps OCR pluggable even if the sprint runtime uses docTR:

```text
app/services/ocr/base.py
app/services/ocr/doctr_engine.py
app/services/ocr/tesseract_engine.py        # optional future fallback
app/services/ocr/benchmark.py               # optional future benchmark
```

### 5.6 Label topology service

OCR output is converted into a structured label topology object.

The topology object gives rules a shared way to reason about:

```text
full OCR text
text blocks
bounding boxes
confidence
field candidates
evidence snippets
evidence crops
```

MVP topology does not need full legal-grade geometry. It should be good enough to support:

```text
warning block extraction
brand candidate search
alcohol content extraction
net contents extraction
source-backed evidence display
```

Future topology enhancements:

```text
contrast estimation
font-size estimation
field-of-vision checks
panel detection
curved-label distortion detection
```

### 5.7 Validation engine

The validation engine consumes:

```text
ColaApplication
OCRResult
LabelTopology
Source-backed criteria registry
```

It returns:

```text
LabelVerificationResult
```

Validation layers:

```text
1. Upload and image preflight
2. OCR quality checks
3. Strict deterministic compliance checks
4. Fuzzy application-vs-label matching
5. Numeric / unit normalization
6. Risk-based Needs Review heuristics
7. Source-backed explanation rendering
```

---

## 6. Filesystem Job Store

### 6.1 Job directory layout

```text
data/
  jobs/
    {job_id}/
      manifest.json
      uploads/
        {item_id}.png
      thumbnails/
        {item_id}.png
      results/
        {item_id}.json
      evidence/
        {item_id}_warning.png
        {item_id}_brand.png
      exports/
        results.csv
```

### 6.2 Atomic result writes

Workers should write results atomically:

```python
tmp_path = result_path.with_suffix(".json.tmp")
tmp_path.write_text(result_json)
tmp_path.replace(result_path)
```

This prevents the status endpoint from reading partially written JSON.

### 6.3 Job status calculation

The status endpoint can compute progress from files:

```python
total = len(manifest["items"])
completed = len(list(results_dir.glob("*.json")))
```

For each completed result, count verdicts:

```text
pass_count
needs_review_count
fail_count
```

This is simple, transparent, and good enough for a single-VM sprint deployment.

---

## 7. Data Models

### 7.1 COLA application model

The application model is based on Form 5100.31-style fields, simplified for the sprint.

```python
class ColaApplication(BaseModel):
    filename: str

    # routing
    product_type: Literal["wine", "distilled_spirits", "malt_beverage"]
    source_of_product: Literal["domestic", "imported"] | None = None
    type_of_application: str | None = None

    # identity
    brand_name: str
    fanciful_name: str | None = None
    class_type: str | None = None

    # common label fields
    alcohol_content: str | None = None
    net_contents: str | None = None
    country_of_origin: str | None = None

    # applicant / producer fields
    applicant_name: str | None = None
    applicant_address: str | None = None
    producer_name: str | None = None
    producer_address: str | None = None

    # formula / composition support
    formula_id: str | None = None
    statement_of_composition: str | None = None

    # wine-specific fields
    grape_varietals: list[str] = []
    appellation_of_origin: str | None = None

    # physical metadata
    container_volume: str | None = None
    label_width_inches: float | None = None
    label_height_inches: float | None = None
```

### 7.2 OCR result

```python
class OCRTextBlock(BaseModel):
    text: str
    confidence: float
    bbox: BoundingBox | None = None

class OCRResult(BaseModel):
    full_text: str
    avg_confidence: float
    blocks: list[OCRTextBlock]
    preprocessing_ms: int
    ocr_ms: int
    total_ms: int
```

### 7.3 Verification result

```python
class FieldCheck(BaseModel):
    rule_id: str
    name: str
    category: str
    verdict: Literal["pass", "needs_review", "fail", "info"]
    severity: Literal["info", "warning", "critical"]
    expected: str | None = None
    observed: str | None = None
    score: float | None = None
    confidence: float | None = None
    evidence_text: str | None = None
    source_refs: list[str] = []
    message: str
    reviewer_action: str | None = None

class LabelVerificationResult(BaseModel):
    job_id: str
    item_id: str
    filename: str
    overall_verdict: Literal["pass", "needs_review", "fail"]
    processing_ms: int
    checks: list[FieldCheck]
    ocr: OCRResult | None = None
```

---

## 8. Source-Backed Criteria Registry

The legal corpus exists to keep rules traceable.

Primary files:

```text
research/legal-corpus/source-ledger.json
research/legal-corpus/source-ledger.md
research/legal-corpus/source-confidence.md
research/legal-corpus/matrices/source-backed-criteria.json
research/legal-corpus/matrices/source-backed-criteria.md
```

Runtime copy or import path:

```text
app/rules/definitions/source-backed-criteria.json
```

A rule definition should include:

```json
{
  "rule_id": "GOV_WARNING_EXACT_TEXT",
  "name": "Government warning exact text",
  "category": "strict_compliance",
  "beverage_types": ["wine", "distilled_spirits", "malt_beverage"],
  "default_verdict": "fail",
  "source_refs": ["SRC_27_USC_215", "SRC_27_CFR_PART_16"],
  "detection_method": "OCR warning block extraction and canonical text comparison",
  "pass_condition": "Warning text matches canonical text after whitespace normalization",
  "fail_condition": "Warning missing or altered",
  "needs_review_condition": "OCR confidence too low",
  "ui_message": "Government warning text does not match the required wording."
}
```

### 8.1 Source confidence policy

```text
Tier 1 official deterministic requirement
  → may return Fail or Pass

Tier 1 subjective/contextual requirement
  → Needs Review unless deterministic evidence is clear

Tier 2 legal/industry/case analysis
  → Needs Review

Tier 3 OSINT/research synthesis
  → Needs Review or fixture strategy only
```

---

## 9. Active MVP Rule Set

The architecture supports many source-backed rules, but the sprint MVP should prioritize high-value checks.

### 9.1 Strict compliance checks

```text
GOV_WARNING_PRESENT
GOV_WARNING_EXACT_TEXT
GOV_WARNING_HEADER_CAPS
ALCOHOL_ABV_PROHIBITED
MALT_NET_CONTENTS_16OZ_PINT
```

### 9.2 Manual typography / Needs Review checks

```text
GOV_WARNING_HEADER_BOLD_REVIEW
GOV_WARNING_BODY_NOT_BOLD
GOV_WARNING_TYPE_SIZE_ESTIMATE
GOV_WARNING_CONTRAST_LEGIBILITY
```

Sprint behavior:

```text
Do not overclaim visual font compliance from arbitrary raster images.
If image quality is weak or physical typography cannot be verified, return Needs Review with a manual-verification explanation.
```

### 9.3 Fuzzy application-vs-label matching

```text
FORM_BRAND_MATCHES_LABEL
FORM_FANCIFUL_NAME_MATCHES_LABEL
FORM_CLASS_TYPE_MATCHES_LABEL
COUNTRY_OF_ORIGIN_MATCH
```

Fuzzy behavior:

```text
Pass: harmless casing, spacing, punctuation, or apostrophe differences
Needs Review: ambiguous match
Fail: clear mismatch with high OCR confidence
```

### 9.4 Numeric checks

```text
ALCOHOL_VALUE_MATCH
PROOF_EQUIVALENCE
NET_CONTENTS_MATCH
```

### 9.5 Risk-based review checks

These are valuable but should generally return **Needs Review**:

```text
HEALTH_CLAIM_EXPLICIT
HEALTH_CLAIM_IMPLICIT
WINE_SEMI_GENERIC_NAME_DETECTED
ABSINTHE_TERM_DETECTED
GEOGRAPHIC_MULTI_AVA_RISK
SPIRITS_FORMULA_REQUIRED_RISK
SOC_PROPRIETARY_ACRONYM_NEAR_COMPOSITION
```

The key product behavior is that source-backed risk does not become an unsupported automatic rejection.

---

## 10. Validation Flow

### 10.1 Single label flow

```text
1. User opens home page.
2. User enters simple application fields or selects a demo.
3. User uploads one label image.
4. App runs upload preflight.
5. App creates job directory.
6. App runs local OCR.
7. App builds OCR/topology result.
8. App runs validation rules.
9. App writes result JSON.
10. User sees Pass / Needs Review / Fail with source-backed reasons.
```

### 10.2 Batch flow

```text
1. User uploads multiple label images and a manifest CSV/JSON.
2. App validates file count, file types, and manifest mapping.
3. App creates a batch job.
4. UI redirects immediately to job status page.
5. HTMX polls status endpoint every few seconds.
6. Completed labels appear incrementally.
7. User filters failures / Needs Review.
8. User downloads CSV export.
```

### 10.3 Status endpoint behavior

```text
GET /jobs/{job_id}/status
  → reads manifest.json
  → counts result JSON files
  → aggregates verdict counts
  → renders partial HTML table
```

No websocket is required for the sprint.

---

## 11. OCR Architecture

### 11.1 OCR decision

The sprint architecture uses **docTR** as the primary local OCR engine.

Reasoning:

```text
- local CPU inference
- structured OCR pipeline
- confidence scoring
- geometry output suitable for evidence display
- lower deployment friction than heavier alternatives
- avoids hosted OCR endpoints
```

### 11.2 OCR warmup

The model should warm up once at app startup or first use.

```python
@app.on_event("startup")
def startup() -> None:
    get_ocr_engine().warmup()
```

If startup warmup is too slow for deployment, use lazy warmup on first demo run and document the first-run delay.

### 11.3 OCR output requirements

The OCR engine must produce:

```text
full text
text blocks
confidence scores
bounding boxes or geometry when available
runtime timings
```

### 11.4 OCR uncertainty policy

If OCR confidence is low:

```text
return Needs Review
show evidence text
avoid false Pass
```

### 11.5 Future benchmark path

The code should keep OCR pluggable. Future candidates may include:

```text
Tesseract
PaddleOCR
EasyOCR
Surya OCR
```

But the sprint MVP should not block on a full multi-engine benchmark harness.

---

## 12. Security Architecture

### 12.1 Upload controls

The upload endpoint is the main public attack surface.

MVP controls:

```text
allowlist extensions
validate image signatures / magic bytes
randomize stored filenames
strip user path information
reject path traversal
reject double extensions
limit individual file size
limit batch file count
limit total batch size
reject unsupported formats
store uploads outside static-serving paths
clean up old jobs
```

### 12.2 No executable upload serving

Uploaded files should never be executed or served as active content.

Static route policy:

```text
serve thumbnails/evidence only by controlled app routes
never expose raw upload directory as a static web root
```

### 12.3 Data retention

Prototype policy:

```text
Uploaded files and results are stored only for demo/job processing.
A cleanup job or script should remove old job directories.
No production records-retention claims are made.
```

### 12.4 No private data harvesting

The deployed app must not:

```text
crawl TTB systems
scrape authenticated COLAs Online data
enumerate TTB IDs
harvest private rejection records
send user labels to hosted ML endpoints
```

---

## 13. Accessibility and UX Architecture

### 13.1 Reviewer-first UI

The UI should be designed for mixed technical comfort.

Requirements:

```text
large buttons
plain language
high-contrast status badges
keyboard-accessible forms
visible focus states
clear error messages
simple result summaries
source-backed details on demand
```

### 13.2 Status language

Use plain labels:

```text
Pass
Needs Review
Fail
```

Avoid final-agency-action language:

```text
Approved
Rejected
Legally compliant
Legally non-compliant
```

### 13.3 Batch progress language

For large batches, show immediate feedback:

```text
Batch accepted.
Processing 0 / 243 labels.
Completed results will appear as they finish.
```

Then update:

```text
Processed 37 / 243
Pass: 24
Needs Review: 9
Fail: 4
```

---

## 14. Performance Architecture

### 14.1 Performance target

```text
Single-label target:
  approximately five-second feedback after OCR warmup,
  dependent on image complexity and VM resources.

Batch target:
  immediate job creation and live progress updates,
  with each label processed independently.
```

Do not claim that a 200–300 label batch completes in five seconds total.

### 14.2 Timing fields

Each result should record:

```text
preflight_ms
preprocessing_ms
ocr_ms
validation_ms
total_ms
avg_ocr_confidence
```

### 14.3 Performance documentation

`docs/performance.md` should eventually include:

```text
VM size
OCR engine
worker/executor settings
fixture count
p50 per-label time
p95 per-label time
batch completion time
known bottlenecks
```

---

## 15. Data and Fixture Architecture

### 15.1 Fixture categories

```text
public approved labels
  realistic positive examples where legally appropriate

public surrendered/revoked labels
  post-market public anomaly context only

synthetic negative labels
  controlled failure examples mapped to source-backed rules

demo fixtures
  curated labels for evaluator one-click demos
```

### 15.2 Fixture provenance

Fixture provenance is stored in:

```text
data/source-maps/fixture-provenance.json
data/source-maps/fixture-provenance.md
```

Each fixture should map to:

```text
fixture_id
file_path
source_type
rule_ids
source_refs
expected_verdict
mutation_summary
```

### 15.3 Synthetic negative strategy

Synthetic negative fixtures are necessary because true rejected and Needs Correction applications are not generally public.

The fixture strategy should be honest:

```text
No claim is made that the prototype has access to confidential rejected application data.
Synthetic failures are generated from source-backed regulatory criteria and public examples.
```

---

## 16. Repository Architecture

Recommended repository structure:

```text
README.md
PRD.md
TASKS.md
ARCHITECTURE.md
MODEL_ARCHITECTURE.md
MODEL_LOG.md
TRADEOFFS.md
DEMO_SCRIPT.md
PERSONALITIES.md

app/
  main.py
  config.py
  routes/
  services/
  schemas/
  rules/
  templates/
  static/

docs/
  architecture.md
  validation-rules.md
  data-strategy.md
  security-and-privacy.md
  accessibility.md
  deployment.md
  performance.md
  tradeoffs.md

research/
  legal-corpus/
    source-ledger.json
    source-ledger.md
    source-confidence.md
    federal-statutes.md
    cfr-regulations.md
    ttb-guidance-and-circulars.md
    court-cases-and-precedents.md
    public-data-boundaries.md
    forms/
    excerpts/
    matrices/
    reports/

data/
  jobs/
  fixtures/
  source-maps/

scripts/
  bootstrap_legal_corpus.py
  validate_legal_corpus.py
  generate_synthetic_fixtures.py
  smoke_test.py

Dockerfile
docker-compose.yml
Caddyfile
requirements.txt
.env.example
```

---

## 17. Implementation Order for Codex

### Stage 1 — App skeleton

```text
FastAPI app
health route
Jinja templates
local CSS
Dockerfile
docker-compose.yml
Caddyfile
```

Acceptance:

```text
http://localhost:8000 loads
/health returns ok
Docker builds
```

### Stage 2 — Legal corpus and source registry

```text
run scripts/bootstrap_legal_corpus.py
run scripts/validate_legal_corpus.py
copy core criteria into app/rules/definitions
```

Acceptance:

```text
legal corpus validates
criteria JSON loads in app
```

### Stage 3 — Demo fixtures and one-click demo

```text
seed demo fixtures
add demo buttons
create job from fixture
render result page
```

Acceptance:

```text
user can click Run Demo and see a result
```

### Stage 4 — OCR integration

```text
install docTR
load OCR engine
process image
return OCR text/confidence/geometry
```

Acceptance:

```text
uploaded image produces OCRResult
```

### Stage 5 — Core rule engine

Implement:

```text
brand fuzzy match
government warning exact text
government warning header caps
ABV prohibited
malt 16 fl. oz. → 1 Pint
country of origin check for imports
```

Acceptance:

```text
clean demo passes
warning demo fails
ABV demo fails
malt net contents demo fails
ambiguous visual formatting returns Needs Review
```

### Stage 6 — Batch and export

```text
multiple file upload
manifest CSV/JSON
job status polling
incremental result table
CSV export
```

Acceptance:

```text
batch job shows progress
CSV downloads
failed items do not crash entire batch
```

### Stage 7 — Deployment

```text
provision VM
install Docker
copy repo
configure Caddy
point DNS
run docker compose
smoke test www.labelsontap.ai
```

Acceptance:

```text
https://www.labelsontap.ai loads
one-click demo works
upload demo works
batch demo works
```

---

## 18. Production Hardening Roadmap

The MVP intentionally skips several production concerns.

Future production architecture should add:

```text
SSO / identity integration
RBAC
PostgreSQL
Redis or durable queue
audit logging
records retention policy
formal malware scanning
rate limiting
centralized logs
structured observability
NIST SSDF practices
ATO/FedRAMP-aligned controls
COLAs Online integration if authorized
```

Advanced validation roadmap:

```text
full wine appellation / AVA validation
full formula-to-label reconciliation
font-size validation with physical scale confidence
field-of-vision verification with panel metadata
curved-label unwarping
expanded case-law risk heuristics
OCR benchmark harness
human feedback loop
```

---

## 19. Key Trade-Offs

### 19.1 Filesystem job store instead of database

Chosen for sprint speed and reliability.

Production path:

```text
PostgreSQL + durable queue + audit logging
```

### 19.2 docTR default instead of hosted OCR

Chosen for local-first runtime and data control.

Production path:

```text
benchmark docTR, PaddleOCR, Tesseract, EasyOCR on real deployment hardware
```

### 19.3 Server-rendered UI instead of React

Chosen for fast delivery and simple reviewer UX.

Production path:

```text
React or USWDS frontend only if the workflow grows beyond simple upload/review/export
```

### 19.4 Typography checks route to Needs Review

Chosen because reliable font-weight/physical-size verification from arbitrary raster images is brittle.

Production path:

```text
DPI-aware typography estimation + confidence gates + manual verification workflow
```

### 19.5 Source-backed legal corpus included, but focused runtime rules

Chosen to prove regulatory traceability without delaying the deployed MVP.

Production path:

```text
expand implemented rule coverage from the legal corpus over time
```

---

## 20. Architecture Summary

Labels On Tap is architected as a single-VM, local-first, source-backed verification system:

```text
FastAPI + Jinja2 + HTMX
  → accessible reviewer UI

docTR + OpenCV/Pillow
  → local OCR and image preflight

RapidFuzz + deterministic Python rules
  → field matching and compliance checks

research/legal-corpus
  → source-backed criteria and rule provenance

filesystem job store
  → sprint-safe asynchronous batch progress

Docker + Caddy
  → deployed HTTPS app at www.labelsontap.ai
```

The architecture prioritizes the take-home’s actual success criteria:

```text
working deployed URL
clear source code
simple reviewer UX
fast local processing
batch support
source-backed validation
honest trade-offs
```

It is intentionally ambitious in research structure, but pragmatic in runtime implementation.
