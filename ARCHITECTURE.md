# Architecture

Labels On Tap is a single-VM, local-first web application for COLA-style alcohol
label preflight.

## Runtime Stack

| Layer | Technology | Purpose |
|---|---|---|
| Web | FastAPI | Routes, uploads, health checks |
| UI | Jinja2 + HTMX | Server-rendered pages and polling |
| Styling | Local CSS | No frontend build or CDN dependency |
| OCR | docTR + fixture fallback | Real upload OCR plus deterministic demos/tests |
| Evidence model | Optional DistilRoBERTa | Field-support scoring |
| Typography model | JSON logistic classifier | Warning-heading boldness preflight |
| Rules | Python deterministic rules | Source-backed compliance triage |
| Queue | Filesystem JSON + local worker | Durable single-VM batch processing |
| Storage | Filesystem JSON | Jobs, uploads, results, reviewer notes |
| Deployment | Docker Compose + Caddy | Public HTTPS at `www.labelsontap.ai` |

## Request Flow

```mermaid
flowchart TD
    A[Upload or demo] --> B[Preflight validation]
    B --> C[Create filesystem job]
    C --> D[OCR]
    D --> E[Optional field-support scoring]
    D --> F[Warning typography preflight]
    E --> G[Source-backed rules]
    F --> G
    G --> H[Reviewer policy queue]
    H --> I[Result JSON]
    I --> J[Job page / reviewer dashboard / CSV]
```

## Batch Flow

```mermaid
flowchart TD
    A[Manifest + loose images or ZIP] --> B[Validate manifest]
    B --> C[Validate each image]
    C --> D[Randomized storage names]
    D --> E[Write queue.json]
    E --> F[Return job page immediately]
    E --> G[Local worker processes queued items]
    G --> H[Write one result JSON per item]
    H --> I[HTMX status polling]
    H --> J[Reviewer dashboard]
```

The queue is durable at the filesystem level. If the app restarts while a batch
is marked `running`, startup recovery puts it back into `queued`.

## Filesystem Layout

```text
data/jobs/{job_id}/
  manifest.json
  queue.json                 # batch jobs only
  uploads/
  results/
```

Raw/bulk evaluation data is intentionally gitignored:

```text
data/work/
```

## Security Boundaries

Implemented prototype controls:

- upload size limits,
- manifest size limits,
- ZIP archive size and item count limits,
- image extension allowlist,
- magic-byte checks,
- Pillow decode checks,
- randomized stored filenames,
- original filename kept only as metadata,
- path traversal rejection,
- no hosted OCR or hosted ML APIs at runtime.

Production controls still needed:

- authentication and roles,
- admin portal,
- audit logs,
- retention policy,
- malware scanning/quarantine,
- rate limiting,
- central logging/monitoring,
- formal accessibility/security review.

## Deployment

```text
Browser
  -> Caddy HTTPS
  -> FastAPI app container
  -> local OCR/models/rules
  -> filesystem job volume
```

Canonical host:

```text
https://www.labelsontap.ai
```

Apex redirect:

```text
https://labelsontap.ai -> https://www.labelsontap.ai
```

## Production Upgrade Path

- Replace local queue with broker-backed worker queue.
- Add PostgreSQL for review history and audit metadata.
- Add SSO/RBAC.
- Add malware scanning and retention policy.
- Promote graph/CNN model candidates only after locked noisy-OCR holdout
  evaluation and CPU latency proof.
