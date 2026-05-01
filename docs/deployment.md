# Deployment

Labels On Tap is designed for a small x86_64 Linux VM running Docker Compose and Caddy.

## Bootstrap

```bash
python scripts/bootstrap_project.py --if-missing
```

## Docker

```bash
docker compose build
docker compose up -d
curl http://localhost:8000/health
```

The Caddyfile serves `labelsontap.ai` and redirects `www.labelsontap.ai` to the bare domain.

## Runtime Notes

The app does not call hosted OCR or hosted ML APIs. Demo routes use fixture OCR ground truth for deterministic evaluator behavior. Real uploads use the local docTR adapter when available and route OCR failures or low confidence to Needs Review.
