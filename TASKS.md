# Labels On Tap Final Delivery Checklist

Canonical URL:

```text
https://www.labelsontap.ai
```

## Submission Status

- [x] Working FastAPI application.
- [x] Deployed public URL.
- [x] Dockerfile, Docker Compose, and Caddyfile.
- [x] Local-first OCR runtime with fixture fallback.
- [x] Source-backed deterministic rule layer.
- [x] Single-label upload.
- [x] Multi-panel application upload.
- [x] Manifest-backed batch upload.
- [x] ZIP-backed batch upload with guardrails.
- [x] Filesystem-backed durable local batch queue.
- [x] Reviewer dashboard at `/review`.
- [x] Reviewer decisions and notes.
- [x] CSV export.
- [x] Photo OCR intake demo for local bottle/can/shelf photos.
- [x] Public COLA example demo when local gitignored corpus exists.
- [x] Upload max-size checks, random stored names, signature checks, and Pillow validation.
- [x] Government-warning exact text, capitalization, and boldness preflight.
- [x] Country of origin for imported products.
- [x] Bottler/producer field support.
- [x] DistilRoBERTa field-support bridge wired as optional runtime evidence.
- [x] Logistic warning-heading boldness model exported in `app/models/typography/`.
- [x] README includes setup, run, test, deployment, assumptions, and measured results.
- [x] `MODEL_LOG.md` expanded into a chronological experiment ledger with model statistics.
- [x] `MODEL_ARCHITECTURE.md`, `TRADEOFFS.md`, `MODEL_LOG.md`, and `docs/performance.md` include Mermaid diagrams for runtime, ensemble, graph-scorer, and future model paths.
- [x] Handoff and local AI-agent files removed from the submission surface.

## Verification

Last full container test run:

```text
pytest -q
105 passed
```

## Current Website Debugging

The live site has been through the final high-priority submission smoke path.
One last browser click-through is still recommended immediately before sending
the project link, but the main deployment, demo data, upload, queue, reviewer,
and export paths are now working.

- [x] Landing page exists at `/` with `Home`, `LOT Demo`, and `LOT Actual`.
- [x] `LOT Demo` links to the server-hosted public COLA demo path.
- [x] `LOT Actual` links to the user-upload application path.
- [x] Example data download includes `manifest.csv` plus application image folders.
- [x] Single-application actual upload processes immediately instead of waiting in the queue.
- [x] Batch/directory processing uses the durable queue and can be cancelled.
- [x] Pull latest `main` on AWS.
- [x] Rebuild and restart Docker Compose on AWS.
- [x] Confirm mounted demo data exists inside the app container at `/app/data/work/demo-upload/public-cola-curated-300`.
- [x] Confirm `/health` returns `{"status":"ok"}` on the public URL.
- [x] Confirm home page nav works: `Home`, `LOT Demo`, `LOT Actual`.
- [x] Confirm `LOT Demo` loads the curated 300-application server data.
- [x] Confirm `LOT Demo` can parse one application and show Actual vs Scraped fields.
- [x] Confirm `LOT Demo` can parse the directory and show progress, timing, and queue status.
- [x] Confirm `LOT Actual` can upload the downloaded example data.
- [x] Confirm `LOT Actual` can parse one application and show Actual vs Scraped fields.
- [x] Confirm `LOT Actual` can parse a directory batch and cancel cleanly.
- [x] Confirm CSV export downloads from review results.
- [x] Confirm reviewer `Accept` / `Reject` actions visibly persist on the job page.
- [x] Confirm `LOT Actual` uploaded workspace persists after navigation until `Reset`.

## Final Smoke Checks

Important smoke checks before submission:

- [x] Pull latest commit on the AWS host.
- [x] Rebuild containers.
- [x] `curl https://www.labelsontap.ai/health`.
- [x] Home page loads.
- [x] Demo buttons work.
- [x] LOT Demo single-application parse works.
- [x] LOT Demo directory parse works against 300 curated applications.
- [x] LOT Actual downloaded example-data upload works.
- [x] LOT Actual single-application parse works.
- [x] LOT Actual directory parse works.
- [x] Reviewer dashboard loads.
- [x] Job page shows image evidence, rule checks, OCR text, and reviewer buttons.
- [x] Reviewer actions visibly persist.
- [x] CSV export downloads.
- [ ] Final five-minute browser pass immediately before submission.
- [ ] Optional: photo intake parses one fresh local phone photo.

## Current Runtime Model Truth

- [x] Runtime OCR: docTR for real uploads, fixture OCR for demos/tests.
- [x] Runtime field-support: optional DistilRoBERTa text-pair classifier when model artifact is mounted.
- [x] Runtime typography: JSON-exported logistic model for `GOVERNMENT WARNING:` heading boldness.
- [x] Runtime decisions: deterministic compliance rules and reviewer policy queues.
- [x] Graph scorer: documented offline experiment, not deployed.
- [x] CNN-inclusive typography ensembles: documented offline experiments, not deployed.
- [x] PaddleOCR/OpenOCR/PARSeq/ASTER/FCENet/ABINet: measured offline candidates, not deployed.
- [x] WineBERT/o, OSA, and FoodBaseBERT domain-NER probes: measured offline candidates, not deployed.
- [x] LayoutLMv3 and HO-GNN/TPS/SVTR paths: documented future architecture, not deployed.

## Future Production Work

- [ ] Authentication, roles, and admin portal.
- [ ] Audit-grade review history and retention policy.
- [ ] Broker-backed queue and separate worker container.
- [ ] PostgreSQL or equivalent durable review database.
- [ ] Malware scanning and quarantine for uploads/ZIPs.
- [ ] Full noisy-OCR locked holdout benchmark.
- [ ] Runtime promotion study for graph-aware scorer.
- [ ] Runtime promotion study for CNN-inclusive typography ensemble.
- [ ] Azure/FedRAMP-aligned deployment variant.
