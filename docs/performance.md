# Performance

The prototype target is roughly five seconds per single label after OCR warmup, dependent on image size, VM resources, and OCR model cache state.

The current demo routes use fixture OCR ground truth so evaluator demos are immediate and deterministic. Real uploads use local docTR when installed; first-run model loading may be slower than steady-state processing.

## Local Non-Docker Smoke Measurements

Measured on the development machine on 2026-05-01 with FastAPI `TestClient` and fixture OCR:

| Check | Result |
|---|---:|
| `/health` | 30.2 ms |
| `/demo/clean` with redirect | 12.4 ms |
| `/demo/batch` with redirect | 11.6 ms |
| `pytest -q` | 61 tests in 0.61 s |

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

## Public COLA OCR Evaluation

The official public COLA evaluation runner is now available:

```bash
python scripts/evaluate_public_cola_ocr.py --limit 25 --run-name pilot-25
```

or, when using Docker OCR dependencies:

```bash
docker compose run --rm \
  -v "$PWD/data/work:/app/data/work" \
  app python scripts/evaluate_public_cola_ocr.py --limit 25 --run-name pilot-25
```

The runner treats one public COLA application as one evidence bundle. It scans
every downloaded label image for that application, preserves panel-level OCR
evidence, aggregates text across panels, and compares the aggregate evidence
against parsed application fields.

Outputs are written under:

```text
data/work/public-cola/parsed/ocr/evaluations/<run-name>/
  summary.json
  applications.json
  application_results.csv
  field_results.csv
```

The development shell used for this note does not have `python-doctr` installed,
so the first real OCR benchmark should be run inside the Docker image or the
AWS deployment host after OCR warmup. The local smoke test verified evaluator
wiring, multi-panel aggregation, output generation, and cache behavior, but it
does not represent real OCR accuracy or latency.

The container requirements pin CPU-only `torch` and `torchvision` wheels from
the PyTorch CPU index. That avoids pulling CUDA packages into the local/AWS VM
image and keeps the OCR deployment aligned with the CPU-only prototype target.

## May 2 Public-COLA Data Audit

The local Docker/Podman OCR image builds successfully with CPU-only PyTorch,
TorchVision, and docTR. A first public-COLA OCR pilot also exposed a data
quality issue before any metric was reported: the files previously recorded as
downloaded label images were HTML "Unable to render attachment" pages, not
raster label images.

Current audited local state:

| Item | Count |
|---|---:|
| Parsed public COLA applications | 810 |
| Discovered label panel attachment records | 1,433 |
| Valid local raster label panels | 0 |
| Invalid attachment files marked pending | 1,235 |

The downloader now validates image bytes with Pillow, and the evaluator skips
invalid image paths. The next real OCR benchmark should happen only after the
TTB attachment endpoint is reachable and pending image downloads have been
retried successfully.

## May 2 Local Container Smoke

Measured locally with Podman on port `8001` after rebuilding
`labels-on-tap-app:local`:

| Check | Result |
|---|---:|
| Container image build | Passed |
| `GET /health` | `200` |
| `GET /` | `200`, 3,277 bytes |
| `GET /demo/clean` with redirect | `200`, 1,759 bytes |

This verifies the local container shape before any AWS redeploy. It is not a
public latency benchmark.

## May 2 COLA Cloud Sample OCR Smoke

TTBOnline.gov remained unavailable/resetting during the weekend sprint, so the
COLA Cloud sample pack was used as a development-only fallback corpus. The
sample pack includes public COLA metadata plus CloudFront-hosted label image
URLs. The importer downloaded and converted 8 real label images for 5 COLA
applications, then the local docTR evaluator ran inside the Podman app image.

Tiny-sample result:

| Metric | Result |
|---|---:|
| Applications evaluated | 5 |
| Label images OCR'd | 8 |
| Mean latency per application | 1,784 ms |
| Max latency per application | 3,860 ms |
| Brand-name match rate | 80% |
| Fanciful-name match rate | 80% |
| Country-origin match rate | 100% of 3 attempted |
| Class/type match rate | 0% |

This is only a smoke result, not final accuracy. It proves the end-to-end path
from commercial public-data sample pack to local OCR to field-level evidence.
It also shows the next tuning target: class/type matching needs more tolerant
normalization and/or product-class synonym handling.
