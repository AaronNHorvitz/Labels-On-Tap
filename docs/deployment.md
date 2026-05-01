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
