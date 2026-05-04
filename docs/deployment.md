# Deployment

Labels On Tap is designed for an x86_64 Linux VM running Docker Compose and Caddy.

## Bootstrap

```bash
python scripts/bootstrap_project.py --if-missing
```

## Docker

```bash
docker compose build
docker compose up -d
curl -H "Host: www.labelsontap.ai" http://localhost/health
```

The Compose stack routes through the production Caddy hostnames. For a local Docker smoke test, send the `www.labelsontap.ai` Host header. On the public VM, DNS should point the real hostname to the instance before Caddy requests certificates.

The recommended target is AWS EC2 On-Demand on Ubuntu 24.04 LTS. Use `m7i.xlarge` for the deadline window if available; `t3a.large` or `t3.large` is the minimum fallback for a modest demo.

The Caddyfile serves `www.labelsontap.ai` and redirects `labelsontap.ai` permanently to the `www` hostname.

DNS should point both records at the VM's Elastic IP:

```text
www.labelsontap.ai  A  <elastic-ip>
labelsontap.ai      A  <elastic-ip>
```

## Runtime Notes

The app does not call hosted OCR or hosted ML APIs. Demo routes use fixture OCR ground truth for deterministic evaluator behavior. Real uploads use the local docTR adapter when available and route OCR failures or low confidence to Needs Review.

The `/cola-cloud-demo` route is local-data dependent. It reads previously
downloaded public example data from gitignored `data/work/cola/` if that corpus
is present on the host; otherwise it renders a friendly missing-data page. Do
not deploy API keys or bulk purchased/public-data caches unless you explicitly
intend the host to serve that local comparison demo.

The deployed sprint app reports raw triage verdicts and maps them into reviewer
policy queues. The queue layer stores whether human approval is required before
acceptance, rejection, or unknown government-warning routing, then maps raw
verdicts into reviewer queues before final agency action.

The DistilRoBERTa field-support bridge is optional but wired into the runtime.
The model artifact is too large for normal Git commit, so copy or mount it
separately before rebuilding if you want BERT evidence enabled:

```bash
mkdir -p data/work/field-support-models/distilroberta-field-support-v1-runtime
# Copy the local model directory into the same path on the host, then:
docker compose build
docker compose up -d
```

`docker-compose.yml` mounts:

```text
./data/work/field-support-models/distilroberta-field-support-v1-runtime/model
-> /app/models/field_support/distilroberta
```

If the directory is absent or empty, the app falls back to deterministic field
matching.

Optional OCR warmup on the deployment host:

```bash
docker compose exec app python scripts/warm_ocr.py
```

Conservative prototype cleanup:

```bash
docker compose exec app python scripts/cleanup_jobs.py --days 7 --dry-run
docker compose exec app python scripts/cleanup_jobs.py --days 7
```
