# Labels On Tap Final Handoff

Date: 2026-05-05  
Repository: `AaronNHorvitz/Labels-On-Tap`  
Local path: `/var/home/aaronnhorvitz/dev/Labels-On-Tap`  
Deployed URL: `https://www.labelsontap.ai`  
Latest pushed commit at shutdown: `547f6ae docs: tighten README accuracy claims`

This document is intentionally detailed. It exists so the project can be
restarted later without relying on memory, chat context, or an active AI
session.

## 1. Current State In Plain English

Labels On Tap is a working FastAPI prototype for alcohol label verification.
It reads COLA-style application data and associated label images, extracts OCR
evidence from the labels, compares that evidence against the application
fields, applies deterministic compliance rules, and routes each application to
`Pass`, `Needs Review`, or `Fail`.

The project is deliberately local-first. It does not rely on hosted OCR APIs or
LLM compliance decisions at runtime. That choice was made for compliance,
cybersecurity, auditability, blocked-network resilience, and hallucination
avoidance.

The deployed app has:

- landing page with `Home`, `LOT Demo`, and `LOT Actual`,
- server-hosted public COLA demo data,
- user-upload application-folder workflow,
- actual-vs-scraped field comparison,
- durable local batch queue,
- reviewer accept/reject workflow,
- CSV export,
- photo OCR intake path,
- source-backed deterministic rules,
- local docTR OCR runtime,
- optional DistilRoBERTa field-support evidence model,
- deployed JSON logistic government-warning boldness preflight,
- extensive model logs and tradeoff documentation.

## 2. Absolute Do-Not-Break Guidance

If the goal is preserving the submitted prototype, do not casually change:

- `app/routes/jobs.py`
- `app/services/rules/registry.py`
- `app/services/ocr/doctr_engine.py`
- `app/services/typography/*`
- `app/models/typography/boldness_logistic_v1.json`
- `Dockerfile`
- `docker-compose.yml`
- `Caddyfile`
- production files on AWS

Reason: the app is working, the deployed demo flow has been smoke-tested, and
the README/model claims have been tightened. Most remaining issues are
production-hardening tasks, not submission blockers.

Safe post-submission edits:

- documentation clarification,
- adding tests,
- adding logging without changing behavior,
- adding new future-work docs,
- local experiments under `experiments/` or `data/work/`.

Risky edits:

- refactoring `jobs.py`,
- changing OCR routing,
- changing queue behavior,
- changing Docker user/permissions,
- changing mounted data paths,
- changing model thresholds,
- changing public demo data layout.

## 3. Latest Git State

Recent commits:

```text
547f6ae docs: tighten README accuracy claims
754a445 docs: document production hardening freeze
ae1d7e3 docs: tighten evaluator README guidance
2fca905 docs: sharpen stakeholder value proposition
0b4e7b8 docs: correct README setup and runtime notes
8c162f6 docs: add app use instructions
9d2fca5 docs: finalize submission wrap-up
0f57b11 fix: show saved reviewer decisions on job page
```

At the time this handoff was created, the local worktree was clean before the
handoff file was added.

## 4. Last Verified Test Result

The README claim was verified locally inside the app container on 2026-05-05:

```bash
podman run --rm -v "$PWD":/app:Z -w /app localhost/labels-on-tap-app:local pytest -q
```

Result:

```text
105 passed in 3.09s
```

Important caveat: running `pytest -q` directly with system Python failed
because the shell was using Python 3.14 without `cv2`. The project runtime is
Python 3.11 inside the app container.

## 5. Public Website

Canonical URL:

```text
https://www.labelsontap.ai
```

Expected top navigation:

- `Home`
- `LOT Demo`
- `LOT Actual`

Expected quick smoke path:

1. Open `https://www.labelsontap.ai`.
2. Click `LOT Demo`.
3. Confirm public COLA demo data loads.
4. Click `Parse This Application`.
5. Confirm Actual vs Scraped fields populate.
6. Click `Review Results`.
7. Click reviewer `Accept` or `Reject`.
8. Confirm the decision persists.
9. Export CSV from the job page.
10. Optional: use `LOT Actual` with downloaded example data.

## 6. AWS / Lightsail Notes

Known public IP used during deployment:

```text
18.190.191.181
```

Known SSH pattern:

```bash
ssh -i ~/.ssh/lightsail-ohio.pem ubuntu@18.190.191.181
```

Known remote repo path:

```text
/home/ubuntu/Labels-On-Tap
```

Known remote deployment commands:

```bash
cd ~/Labels-On-Tap
git pull origin main
docker compose build
docker compose up -d
curl https://www.labelsontap.ai/health
```

Do not run these unless intentionally updating production.

## 7. Demo Data On AWS

The curated public COLA demo pack was uploaded to the AWS host under:

```text
~/Labels-On-Tap/data/work/demo-upload/public-cola-curated-300
```

It contained approximately:

```text
300 applications
553 image files
553 OCR cache files
typography JSON files
manifest.csv
public-cola-demo-pack.zip
```

The app expects the data inside the container at:

```text
/app/data/work/demo-upload/public-cola-curated-300
```

If the demo page says data is missing, check:

```bash
cd ~/Labels-On-Tap
ls -lh data/work/demo-upload/public-cola-curated-300
find data/work/demo-upload/public-cola-curated-300/images -type f | wc -l
docker compose exec app ls -lh /app/data/work/demo-upload/public-cola-curated-300
```

If host permissions block writes into `data/work`, the earlier fix was:

```bash
sudo chown -R ubuntu:ubuntu ~/Labels-On-Tap/data
```

Use caution with ownership changes.

## 8. Runtime Architecture Truth

The live app does not run every experimental model. The live runtime is the
conservative path:

```text
Application fields + label images
-> local docTR OCR / cached fixture OCR
-> deterministic field/rule checks
-> optional local DistilRoBERTa field-support evidence
-> government-warning exact text/caps/boldness checks
-> reviewer policy routing
-> Pass / Needs Review / Fail
```

Active runtime pieces:

- docTR OCR for live uploads,
- fixture/cached OCR for demos where available,
- deterministic rules in `app/services/rules/registry.py`,
- warning boldness preflight in `app/services/typography/`,
- JSON-exported model at `app/models/typography/boldness_logistic_v1.json`,
- optional field-support model loader in `app/services/field_support.py`,
- filesystem-backed durable queue in `app/services/batch_queue.py`,
- JSON job/result store in `app/services/job_store.py`.

Not deployed:

- graph-aware evidence scorer,
- LayoutLMv3 ensemble aggregator,
- tri-engine OCR runtime,
- PaddleOCR/OpenOCR production runtime,
- CNN-inclusive typography ensemble,
- HO-GNN/TPS/SVTR model,
- PARSeq/ASTER/FCENet/ABINet production paths.

Those are documented as measured experiments or future work.

## 9. Model Metrics To Defend In An Interview

### 9.1 DistilRoBERTa Field-Support Arbiter

Artifact:

```text
data/work/field-support-models/distilroberta-field-support-v1-runtime/metrics.json
```

README headline claim:

```text
F1=0.999904 on a locked, unseen clean-text holdout set
```

Verified holdout metrics:

```text
examples: 46,992
accuracy: 0.999936
f1: 0.999904
false_clear_rate: 0.000096
fp: 3
fn: 0
```

Split artifact:

```text
data/work/cola/evaluation-splits/field-support-v1/split_summary.json
```

Split design:

```text
train: 2,000 applications
validation: 1,000 applications
holdout: 3,000 applications
development_holdout overlap: 0
holdout policy: do not tune thresholds or features on holdout results
```

Critical caveat:

This is a clean-text field-pair holdout claim, not a noisy-OCR holdout claim.
The README now says `clean-text holdout set` to avoid overclaiming.

### 9.2 Government-Warning Boldness Preflight

Runtime artifact:

```text
app/models/typography/boldness_logistic_v1.json
```

Training artifact:

```text
data/work/typography-preflight/real-adapted-boldness-logistic-v1/summary.json
```

Important values:

```text
threshold: 0.9545819397993311
validation false_clear_rate: 0.0006238303181534623
README rounded value: 0.000624
```

Runtime interpretation:

- High-confidence bold evidence can clear.
- Weak, missing, blurry, or uncertain typography routes to `Needs Review`.
- The model does not auto-reject solely on weak typography evidence.

### 9.3 Public COLA Demo Pack

The curated public demo data is for walkthrough stability, not model accuracy
claims. Accuracy claims should point to `MODEL_LOG.md`, `MODEL_ARCHITECTURE.md`,
`TRADEOFFS.md`, and metrics artifacts, not the curated demo pack.

## 10. Core Documents

Read these in this order if restarting:

1. `README.md`
2. `APP_USE_INSTRUCTIONS.md`
3. `DEMO_SCRIPT.md`
4. `TASKS.md`
5. `TRADEOFFS.md`
6. `MODEL_ARCHITECTURE.md`
7. `MODEL_LOG.md`
8. `ARCHITECTURE.md`
9. `docs/performance.md`
10. `docs/security-and-privacy.md`

Important project-instruction files:

```text
docs/project_instructions/Take-Home Project_ AI-Powered Alcohol Label Verification App.pdf
docs/project_instructions/Take-Home Project_ AI-Powered Alcohol Label Verification App.docx
```

## 11. Important Source Files

Application:

```text
app/main.py
app/config.py
app/routes/ui.py
app/routes/jobs.py
app/routes/demo.py
app/routes/health.py
```

Services:

```text
app/services/ocr/doctr_engine.py
app/services/rules/registry.py
app/services/batch_queue.py
app/services/job_store.py
app/services/manifest_parser.py
app/services/field_support.py
app/services/photo_intake.py
app/services/typography/boldness.py
app/services/typography/warning_heading.py
```

Templates/static:

```text
app/templates/landing.html
app/templates/base.html
app/templates/index.html
app/templates/public_cola_demo.html
app/templates/job.html
app/templates/partials/job_status.html
app/static/app.css
app/static/app.js
app/static/labels_on_tap_hero.png
```

Models:

```text
app/models/typography/boldness_logistic_v1.json
```

## 12. Known Limits That Are Deliberate

These are documented, not hidden:

- no authentication or roles,
- no admin portal,
- no append-only reviewer audit log,
- no malware scanning/quarantine for ZIP uploads,
- no broker-backed distributed queue,
- no PostgreSQL review database,
- no Section 508 audit,
- no full noisy-OCR locked holdout benchmark,
- no production non-root container runtime yet,
- no Docker/Compose healthchecks yet,
- no Caddy security headers/rate limiting yet,
- no scheduled job cleanup yet.

The reason: those changes touch deployment behavior and were not rushed into
the verified prototype.

## 13. Highest-Priority Future Engineering Work

If continuing after the interview/submission:

1. Add path-safety validation for all job IDs, item IDs, upload names, and
   result filenames.
2. Add simple auth or at least basic auth to protect public reviewer actions.
3. Add append-only reviewer decision logs.
4. Add container and Compose healthchecks.
5. Add non-root container runtime after validating AWS volume ownership.
6. Add Caddy security headers and rate limits.
7. Add scheduled cleanup for `data/jobs/`.
8. Split `app/routes/jobs.py` into smaller modules.
9. Route every parse path through the durable queue.
10. Add per-image OCR timeouts.
11. Add ZIP fallback to `LOT Actual` if directory upload is not supported by
    a browser.
12. Run the locked noisy-OCR holdout benchmark.

## 14. Interview Framing

The strongest explanation is not "I built an OCR app."

Use this:

```text
I built a local-first compliance triage prototype. The app reads every label
panel in a COLA-style application, extracts OCR evidence locally, compares that
evidence to the application fields, applies deterministic source-backed rules,
and routes uncertainty to human review. I intentionally avoided hosted OCR APIs
and LLM compliance decisions at runtime because Treasury-style workflows need
inspectable evidence, predictable behavior without hallucinations, low
false-clear risk, and a path toward controlled federal deployment.
```

If asked about AI:

```text
The AI is used as evidence extraction and field-support assistance, not as the
final legal decision-maker. The final decision path is deterministic and
reviewer-controlled.
```

If asked about the outage / COLA Cloud:

```text
During development, TTB public systems were unavailable during a published
maintenance window. Rather than continue hitting an unstable government system
or build brittle scraping around an outage, I used licensed COLA Cloud public
data for the demo/evaluation corpus and documented that tradeoff.
```

If asked about the model metrics:

```text
The high DistilRoBERTa result is on a locked, unseen clean-text holdout. I do
not claim that as noisy-OCR accuracy. The noisy-OCR locked holdout remains the
next measurement gate.
```

If asked what you would productionize first:

```text
Authentication, append-only audit logs, healthchecks, upload scanning,
scheduled retention cleanup, path-safety hardening, and a broker-backed worker
queue.
```

## 15. Final Recommended Shutdown Checklist

Before walking away:

- Confirm `git status --short` is clean.
- Confirm latest commit is pushed to GitHub.
- Do not rebuild AWS unless intentionally changing production.
- Save this handoff file.
- Keep the Lightsail SSH key safe.
- Keep `.env` and API keys out of Git.
- Do not commit `data/work/` raw datasets.

Useful final commands:

```bash
git status --short
git log --oneline -5
```

If production needs only a health check:

```bash
curl https://www.labelsontap.ai/health
```

Expected:

```json
{"status":"ok"}
```

