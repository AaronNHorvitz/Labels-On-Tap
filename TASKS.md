# TASKS.md — Final Sprint Command Center

**Project:** Labels On Tap
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Canonical deployment URL:** `https://www.labelsontap.ai`
**Deadline:** Monday afternoon, May 4, 2026
**Sprint target:** Deployable, smoke-tested app by Sunday night.

The highest priority is a working deployed demo that an evaluator can open, click through, understand, and trust.

Deployment first: after upload hardening and root docs are done, stop adding product features and deploy. Public URL reliability beats local polish.

---

## Current Truth

- [x] Canonical URL is `https://www.labelsontap.ai`.
- [ ] Public deployed app is live at `https://www.labelsontap.ai`.
- [ ] `https://labelsontap.ai` redirects to `https://www.labelsontap.ai`.
- [x] Runtime architecture is FastAPI + Jinja2/HTMX + local CSS.
- [x] OCR architecture is local docTR adapter with fixture OCR fallback.
- [x] Storage architecture is filesystem JSON job/result store.
- [x] Deployment architecture is Docker Compose + Caddy on an x86_64 cloud VM.
- [x] FastAPI app scaffold is implemented.
- [x] Home page, health route, demo routes, job pages, detail pages, and CSV export routes exist.
- [x] Single-label upload route exists.
- [x] `country_of_origin` and `imported` are first-class application fields.
- [x] Country-of-origin fields are included in the single-label route.
- [x] Core validation rules are implemented for brand match, warning text, warning caps, warning typography review, ABV shorthand, malt net contents, OCR confidence, and country of origin.
- [x] Demo fixtures/data scaffold exists.
- [x] `imported_country_origin_pass.*` fixture set exists.
- [x] Batch fixture manifest exists.
- [x] `scripts/bootstrap_project.py` exists.
- [x] `scripts/seed_demo_fixtures.py` exists.
- [x] Tests scaffold exists.
- [x] Last known local test run: `pytest -q` passed with 16 tests.
- [x] `requirements.txt` exists.
- [x] `Dockerfile` exists.
- [x] `docker-compose.yml` exists.
- [x] `Caddyfile` exists and uses `www.labelsontap.ai` as canonical host.
- [x] `docs/deployment.md` exists.
- [x] `docs/performance.md` exists.
- [x] `docs/tradeoffs.md` exists.
- [x] `TASKS.md` is committed.
- [x] Root `TRADEOFFS.md` exists.
- [x] Root `TRADEOFFS.md` is committed.
- [x] Root `DEMO_SCRIPT.md` exists.
- [x] Root `DEMO_SCRIPT.md` is committed.

---

## Must Fix Before Deployment

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
- [ ] Run `docker compose build`.
- [ ] Run local health smoke test.

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

Note: Docker is required for the Docker checks. If Docker is unavailable locally, run these on the EC2 host before public smoke testing.

---

## Should Fix Before Submission

- [x] CSV export test.
- [x] Item detail page test.
- [x] Show per-rule evidence text on the item detail page when `evidence_text` is available.
- [x] `docs/accessibility.md`.
- [ ] Update `docs/performance.md` with measured values from local Docker and public deployment.
- [x] `docs/tradeoffs.md` exists.
- [ ] Add `imported_missing_country_review.*` fixture if time allows.
- [ ] Public smoke test: `https://www.labelsontap.ai/health`.
- [ ] Public smoke test: clean demo returns Pass.
- [ ] Public smoke test: warning demo returns Fail.
- [ ] Public smoke test: ABV demo returns Fail.
- [ ] Public smoke test: malt net contents demo returns Fail.
- [ ] Public smoke test: country-of-origin demo returns Pass.
- [ ] Public smoke test: batch demo returns multiple results.
- [ ] Public smoke test: CSV export downloads.
- [ ] Public smoke test: apex redirects to `www`.

---

## If Time Allows After Public Demo Is Stable

Only start these after:

```text
upload hardening complete
pytest passes
Docker build passes
public https://www.labelsontap.ai smoke tests pass
```

Priority order:

- [ ] Manual multi-file batch upload using `manifest.csv` / `manifest.json` plus multiple `.jpg/.jpeg/.png` files.
- [ ] Manifest parser tests for missing image, unknown filename, malformed CSV, and happy path.
- [x] CSV export coverage for batch jobs.
- [x] Item detail page coverage for expected, observed, source refs, reviewer action, and per-rule evidence text.
- [ ] Add `brand_mismatch_fail.*` fixture.
- [ ] Add `conflicting_country_origin_fail.*` fixture.
- [ ] Add `warning_missing_block_review.*` fixture.
- [ ] Add a small upload-error page or friendly error template for rejected files.
- [ ] Add old-job cleanup command/script with conservative retention defaults.
- [ ] Add OCR warmup note or prewarm command for deployment.

These are useful, but none should delay the public deployed demo.

---

## Post-Submission / Not Needed For Take-Home

- [ ] ZIP upload with safe archive limits and ZIP-bomb protection.
- [ ] Public COLA fixture curation.
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

## Do Not Do Before Deadline

- [ ] Do not add ZIP upload.
- [ ] Do not add React/Vue/Angular.
- [ ] Do not scrape public COLA data.
- [ ] Do not add a database.
- [ ] Do not add authentication.
- [ ] Do not chase extra rules until the public deployment is live and smoke-tested.
- [ ] Do not replace the fixture-backed demo path with live OCR-only behavior.

---

## Deployment Runbook

Use AWS EC2 On-Demand:

```text
OS: Ubuntu 24.04 LTS
Preferred instance: m7i.xlarge or comparable 4 vCPU / 16 GiB x86_64 instance
Fallback instance: t3a.large or t3.large
Disk: 40-60 GB gp3
Network: Elastic IP
Security group:
  22 from Aaron's IP only
  80 from 0.0.0.0/0
  443 from 0.0.0.0/0
DNS:
  www.labelsontap.ai A record -> Elastic IP
  labelsontap.ai A record -> Elastic IP
```

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
- Fixture-backed batch demo is implemented; manual multi-file batch upload is a stretch item.
- Typography boldness routes to Needs Review instead of brittle raster font-weight failure.
- The app is a reviewer-support prototype, not a final legal approval/rejection system.
- The project does not use hosted OCR or hosted ML APIs at runtime.

---

## Submission Artifacts

- [ ] Screenshot home page.
- [ ] Screenshot clean Pass result.
- [ ] Screenshot government warning Fail result.
- [ ] Screenshot batch result table.
- [ ] Save final commit SHA.
- [ ] Draft submission email.
- [ ] Include GitHub URL.
- [ ] Include deployed URL.
- [ ] Include one-sentence local-first note.

---

## Definition Of Done

- [ ] `https://www.labelsontap.ai` loads over HTTPS.
- [ ] `https://labelsontap.ai` redirects to `https://www.labelsontap.ai`.
- [ ] Home page has one-click demo buttons.
- [ ] Clean demo returns Pass.
- [ ] Government warning demo returns Fail.
- [ ] ABV demo returns Fail.
- [ ] Malt net contents demo returns Fail.
- [ ] Country-of-origin demo returns Pass.
- [ ] Batch demo returns multiple results.
- [ ] CSV export works.
- [ ] Result detail page shows expected, observed, evidence, source refs, and reviewer action.
- [ ] Single upload form exists.
- [ ] Fixture-backed batch demo is clearly available.
- [ ] `pytest -q` passes.
- [ ] `docker compose build` passes.
- [ ] `docker compose up -d` runs locally or on the EC2 host.
- [ ] AWS EC2 deployment is running.
- [ ] README has quick start and live demo instructions.
- [ ] PRD exists.
- [ ] ARCHITECTURE exists.
- [ ] TASKS exists and is committed.
- [ ] TRADEOFFS exists.
- [ ] DEMO_SCRIPT exists.
- [ ] Legal corpus exists.
- [ ] Source-backed criteria matrix exists.
- [ ] Fixture provenance exists.
- [ ] No secrets committed.
- [ ] No private/confidential rejected COLA data committed.
- [ ] No hosted OCR/ML API call exists in runtime code.
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
