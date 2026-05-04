# Deployment

Canonical URL:

```text
https://www.labelsontap.ai
```

The deployed prototype runs on an AWS Lightsail Ubuntu VM using Docker Compose
and Caddy.

## Services

```text
app     FastAPI application
caddy   HTTPS reverse proxy
```

## Refresh Deployment

On the server:

```bash
cd ~/Labels-On-Tap
git pull
docker compose build
docker compose up -d
docker compose logs --tail=100 app
curl https://www.labelsontap.ai/health
```

Expected health response:

```json
{"status":"ok"}
```

## DNS / TLS

Caddy serves:

```text
www.labelsontap.ai
```

The apex domain redirects permanently:

```text
labelsontap.ai -> https://www.labelsontap.ai
```

## Model Artifact

The optional DistilRoBERTa field-support model is not committed because it is
large. If the artifact is present on the host, Docker Compose mounts it here:

```text
./data/work/field-support-models/distilroberta-field-support-v1-runtime/model
-> /app/models/field_support/distilroberta
```

If absent, the app falls back to deterministic matching.

## Runtime Data

Runtime jobs are stored in:

```text
data/jobs/
```

Bulk public COLA data and model training outputs are stored in:

```text
data/work/
```

Both are gitignored.

## Production Gaps

- Add SSO/RBAC.
- Add audit logs and retention rules.
- Replace the local queue with a broker-backed worker pool.
- Add malware scanning for uploads/ZIPs.
- Add centralized monitoring and logs.
