# Performance

The prototype target is roughly five seconds per single label after OCR warmup, dependent on image size, VM resources, and OCR model cache state.

The current demo routes use fixture OCR ground truth so evaluator demos are immediate and deterministic. Real uploads use local docTR when installed; first-run model loading may be slower than steady-state processing.

## Local Non-Docker Smoke Measurements

Measured on the development machine on 2026-05-01 with FastAPI `TestClient` and fixture OCR:

| Check | Result |
|---|---:|
| `/health` | 27.6 ms |
| `/demo/clean` with redirect | 10.7 ms |
| `/demo/batch` with redirect | 9.7 ms |
| `pytest -q` | 30 tests in 0.50 s |

These numbers are useful only as local smoke checks. They do not represent real docTR OCR latency, Docker image startup, or public EC2 network latency.

## Measurements Still Needed

Before final submission, record:

- Docker Compose build result on the deployment host,
- public `https://www.labelsontap.ai/health` response,
- public clean demo response,
- public batch demo response,
- one real-upload docTR warm and cold timing if docTR is enabled on the VM.

Each result records OCR source and confidence. Future benchmarking should record:

- VM size,
- OCR engine,
- fixture count,
- p50 and p95 per-label processing time,
- first-run warmup time,
- batch completion time.
