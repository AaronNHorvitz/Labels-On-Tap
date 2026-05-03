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

## May 2 Graph-Aware OCR Evidence POC

An experimental PyTorch graph scorer was trained on the existing 100-application
calibration set using cached local OCR boxes. The model does not replace OCR. It
scores whether OCR fragments support one expected application field, using
box-level geometry, KNN graph context, text-similarity features, field type, and
panel-level summary features.

The best initial GPU run was:

```bash
.venv-gpu/bin/python experiments/graph_ocr/train_graph_matcher.py \
  --epochs 40 \
  --run-name gpu-safety-neg2-e40 \
  --device cuda \
  --negative-loss-weight 2.0 \
  --false-clear-tolerance 0.0
```

On the held-out test split from the 100-application calibration set:

| Metric | Baseline Fuzzy Matcher | Graph-Aware Scorer |
|---|---:|---:|
| Accuracy | 0.8947 | 0.9408 |
| Precision | 0.8438 | 0.9531 |
| Positive-support recall | 0.7105 | 0.8026 |
| Specificity / negative rejection | 0.9561 | 0.9868 |
| F1 | 0.7714 | 0.8714 |
| False-clear rate | 0.0439 | 0.0132 |

The graph scorer improved support detection for brand name, fanciful name, and
net contents while lowering false clears on shuffled negative examples. This is
an experimental calibration result, not a locked-holdout production claim.

## May 2-3 Alternate OCR CPU Smoke Benchmarks

The curved-text OCR research brief suggested that a mature pre-trained OCR
engine may be more practical than training a custom curved-text model before
the submission deadline. To test that hypothesis without touching the deployed
runtime path, isolated PaddleOCR, OpenOCR/SVTRv2, PARSeq, ASTER, FCENet, and
ABINet smoke benchmarks were run in containers against real public COLA label images
that already had cached docTR OCR output.

PARSeq, ASTER, and ABINet are reported separately because they are scene-text
recognizers, not complete label-page detectors. Their smoke benchmarks use
OpenOCR-detected boxes as the crop source, then run recognition on those crops.
Those latency numbers are recognizer-stage plus crop-preparation time, not full
detector-plus-recognizer OCR latency.

FCENet is reported as a detector-plus-recognizer experiment. FCENet detects
arbitrary text contours on the full label image; ASTER then recognizes the
detected crops. Its timing therefore includes both detection and recognition.

The first modern stack installed but was not usable as-is:

| Stack | Result |
|---|---|
| PaddleOCR 3.5.0 + PaddlePaddle 3.3.1 | Installed, but CPU inference hit a oneDNN/PIR runtime error. |
| PaddleOCR 3.5.0 + PaddlePaddle 3.3.1 with MKLDNN disabled | Ran successfully, but averaged about 5 seconds per image. |
| PaddleOCR 3.3.3 + PaddlePaddle 3.2.0 | Ran successfully with usable CPU latency. |

Successful 30-image smoke result:

| Metric | PaddleOCR 3.3.3 / PaddlePaddle 3.2.0 | OpenOCR 0.1.5 / SVTRv2 | PARSeq AR over OpenOCR crops | PARSeq NAR/refine-2 over OpenOCR crops | ASTER over OpenOCR crops | FCENet + ASTER | ABINet over OpenOCR crops |
|---|---:|---:|---:|---:|---:|---:|---:|
| Images processed | 30 | 30 | 30 | 30 | 30 | 30 | 30 |
| Error count | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Mean latency | 1,105.00 ms/image | 563.77 ms/image | 293.47 ms/image | 215.17 ms/image | 119.87 ms/image | 4,526.70 ms/image | 458.83 ms/image |
| Median latency | 1,096.50 ms/image | 582.50 ms/image | 212.00 ms/image | 168.50 ms/image | 111.00 ms/image | 4,073.50 ms/image | 369.00 ms/image |
| Worst latency | 1,544 ms/image | 1,211 ms/image | 870 ms/image | 655 ms/image | 275 ms/image | 10,525 ms/image | 1,229 ms/image |
| Images under 1.5 seconds | 29 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 30 | 30 / 30 |
| Mean confidence | 0.9346 | 0.9356 | 0.9519 | 0.9158 | 0.7663 | 0.8538 | 0.7398 |
| Mean text blocks | 20.8 | 20.0 | 20.0 | 20.0 | 20.0 | 62.63 | 20.0 |
| Mean extracted characters | 431.67 | 376.63 | 303.37 | 325.50 | 281.43 | 398.23 | 285.77 |

Cached docTR comparison on the same 30 images:

| Metric | docTR Cached Baseline | PaddleOCR Smoke | OpenOCR Smoke | PARSeq AR Crops | PARSeq NAR Crops | ASTER Crops | FCENet + ASTER | ABINet Crops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mean latency | 800.53 ms/image | 1,105.00 ms/image | 563.77 ms/image | 293.47 ms/image | 215.17 ms/image | 119.87 ms/image | 4,526.70 ms/image | 458.83 ms/image |
| Median latency | 804.50 ms/image | 1,096.50 ms/image | 582.50 ms/image | 212.00 ms/image | 168.50 ms/image | 111.00 ms/image | 4,073.50 ms/image | 369.00 ms/image |
| Worst latency | 1,592 ms/image | 1,544 ms/image | 1,211 ms/image | 870 ms/image | 655 ms/image | 275 ms/image | 10,525 ms/image | 1,229 ms/image |
| Mean extracted characters | 436.00 | 431.67 | 376.63 | 303.37 | 325.50 | 281.43 | 398.23 | 285.77 |
| Mean text blocks | 79.3 | 20.8 | 20.0 | 20.0 | 20.0 | 20.0 | 62.63 | 20.0 |

Initial interpretation:

- PaddleOCR is viable enough to continue testing because 29 of 30 images were
  under the 1.5-second local CPU target.
- OpenOCR/SVTRv2 is operationally interesting because it was the fastest engine
  in the 30-image smoke and normalized cleanly into the same OCR schema.
- PARSeq did not fail the CPU latency test when run over already-detected
  crops. Autoregressive mode averaged 293.47 ms/image for crop recognition, and
  non-autoregressive/refine-2 mode averaged 215.17 ms/image. These are not full
  OCR pipeline timings.
- ASTER was the fastest recognizer-stage experiment at 119.87 ms/image over
  OpenOCR crops. This is not a full OCR pipeline timing.
- FCENet + ASTER is the only newly tested full detector-plus-recognizer stack
  in this group, but it averaged 4,526.70 ms/image on CPU and had a worst case
  of 10,525 ms/image. That misses the operational target for routine use.
- ABINet averaged 458.83 ms/image over OpenOCR crops. This is fast enough to
  keep as a documented recognizer-stage experiment, but it is not full OCR
  pipeline timing.
- PaddleOCR and OpenOCR did not clearly beat docTR on raw extracted-character
  count.
- Character count is only a crude proxy. Alternate engines produced fewer text
  blocks, which may mean cleaner line grouping or missing fine-grained tokens,
  so the important comparison is field-support performance.
- Small sample sizes increase variance. These numbers are directional smoke
  estimates only, not a stable engine ranking.

### Field-Support Classification Metrics

The same 30-image smoke set represented 20 COLA applications. A follow-up
field-support comparison scored expected application fields against each
engine's aggregated OCR text. Accepted application field values were treated as
positive examples. Controlled negative examples were created by shuffling
same-field values from other applications. Prediction threshold was a fuzzy
field-support score of `90`.

Overall result across all fields:

| Metric | docTR | PaddleOCR | OpenOCR | PARSeq AR Crops | PARSeq NAR Crops | ASTER Crops | FCENet + ASTER | ABINet Crops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Examples | 224 | 224 | 224 | 224 | 224 | 224 | 224 | 224 |
| Accuracy | 0.7455 | 0.7723 | 0.7143 | 0.6875 | 0.6875 | 0.6920 | 0.6205 | 0.6607 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 0.9773 | 0.9773 | 1.0000 | 0.9655 | 1.0000 |
| Recall | 0.5000 | 0.5714 | 0.4375 | 0.3839 | 0.3839 | 0.3839 | 0.2500 | 0.3214 |
| Specificity | 0.9911 | 0.9732 | 0.9911 | 0.9911 | 0.9911 | 1.0000 | 0.9911 | 1.0000 |
| F1 | 0.6627 | 0.7151 | 0.6049 | 0.5513 | 0.5513 | 0.5548 | 0.3972 | 0.4865 |
| False-clear rate | 0.0089 | 0.0268 | 0.0089 | 0.0089 | 0.0089 | 0.0000 | 0.0089 | 0.0000 |

Excluding `applicant_or_producer`, which remains a known weak OCR/application
field in the current data:

| Metric | docTR | PaddleOCR | OpenOCR | PARSeq AR Crops | PARSeq NAR Crops | ASTER Crops | FCENet + ASTER | ABINet Crops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Examples | 184 | 184 | 184 | 184 | 184 | 184 | 184 | 184 |
| Accuracy | 0.7989 | 0.8315 | 0.7609 | 0.7283 | 0.7283 | 0.7337 | 0.6467 | 0.6957 |
| Precision | 0.9825 | 0.9552 | 0.9800 | 0.9773 | 0.9773 | 1.0000 | 0.9655 | 1.0000 |
| Recall | 0.6087 | 0.6957 | 0.5326 | 0.4674 | 0.4674 | 0.4674 | 0.3043 | 0.3913 |
| Specificity | 0.9891 | 0.9674 | 0.9891 | 0.9891 | 0.9891 | 1.0000 | 0.9891 | 1.0000 |
| F1 | 0.7517 | 0.8050 | 0.6901 | 0.6324 | 0.6324 | 0.6370 | 0.4628 | 0.5625 |
| False-clear rate | 0.0109 | 0.0326 | 0.0109 | 0.0109 | 0.0109 | 0.0000 | 0.0109 | 0.0000 |

By field:

| Field | docTR F1 | PaddleOCR F1 | OpenOCR F1 | docTR Accuracy | PaddleOCR Accuracy | OpenOCR Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| alcohol_content | 0.8333 | 0.8966 | 0.8800 | 0.8462 | 0.8846 | 0.8846 |
| applicant_or_producer | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.5000 | 0.5000 |
| brand_name | 0.7500 | 0.7097 | 0.7097 | 0.8000 | 0.7750 | 0.7750 |
| class_type | 0.5714 | 0.5714 | 0.4000 | 0.7000 | 0.7000 | 0.6250 |
| country_of_origin | 0.7143 | 0.9412 | 0.7143 | 0.7778 | 0.9444 | 0.7778 |
| fanciful_name | 0.8235 | 0.9474 | 0.7500 | 0.8500 | 0.9500 | 0.8000 |
| net_contents | 0.8235 | 0.7500 | 0.6667 | 0.8500 | 0.8000 | 0.7500 |

Experimental stack by-field F1:

| Field | PARSeq AR Crops | PARSeq NAR Crops | ASTER Crops | FCENet + ASTER | ABINet Crops |
|---|---:|---:|---:|---:|---:|
| alcohol_content | 0.8800 | 0.8800 | 0.7619 | 0.8333 | 0.5556 |
| applicant_or_producer | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| brand_name | 0.5714 | 0.5714 | 0.6207 | 0.4615 | 0.5714 |
| class_type | 0.3333 | 0.3333 | 0.4615 | 0.2609 | 0.3333 |
| country_of_origin | 0.7143 | 0.6154 | 0.7143 | 0.6154 | 0.7143 |
| fanciful_name | 0.6667 | 0.7097 | 0.7097 | 0.2609 | 0.6667 |
| net_contents | 0.6667 | 0.6667 | 0.5714 | 0.3333 | 0.5714 |

Interpretation:

- PaddleOCR improved accuracy, recall, and F1 on this smoke task. That is a
  real signal in the current sample and keeps PaddleOCR in contention.
- docTR preserved higher precision and lower false-clear rate.
- OpenOCR was faster and matched docTR's low false-clear rate, but it did not
  beat the other engines on F1 in this first smoke.
- PARSeq was fast as a recognizer over detected crops, including autoregressive
  mode, but it produced lower field-support F1 in this setup. The likely issue
  is not PARSeq's recognition architecture alone; it is the whole crop contract:
  OpenOCR boxes, rectangular cropping, curved/rotated text, and loss of
  detector/recognizer integration.
- ASTER was even faster over OpenOCR crops and produced zero false clears in
  this smoke, but it had low recall and lower F1 than docTR/PaddleOCR. Its
  flexible rectification remains interesting, but the first crop-stage result
  does not justify replacing the current OCR path.
- FCENet + ASTER tested arbitrary-shape detection directly, but it was too slow
  on CPU and produced the lowest field-support F1 in this group. It remains a
  useful research checkpoint, not a practical runtime candidate for the
  five-second label-review target.
- ABINet was fast enough as a recognizer over OpenOCR crops and produced zero
  false clears in this smoke, but its recall and F1 were lower than the current
  complete OCR candidates. The first result does not justify replacing the
  runtime OCR path.
- The alcohol-content false-clear rate for PaddleOCR is too high to promote it
  directly without stricter field-specific thresholds or deterministic checks.
- Small sample sizes increase variance. The correct conclusion is not "choose
  docTR" or "choose PaddleOCR" yet; it is "run the larger calibration set and
  keep PaddleOCR, OpenOCR, and combined evidence under evaluation."

### Deterministic OCR Ensemble Smoke

After the single-engine sweep, a deterministic ensemble smoke treated docTR,
PaddleOCR, and OpenOCR as noisy OCR sensors. Each engine scored whether its
aggregated OCR text supported the expected field value. Several simple
arbitration policies were then compared with the same positive/shuffled-negative
field-support metric.

This is not BERT, LayoutLMv3, or an LLM. It is a deterministic bridge that tests
whether multi-engine evidence can be useful before adding a learned arbiter.

| Policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate |
|---|---:|---:|---:|---:|---:|---:|
| docTR single engine | 0.7455 | 0.9825 | 0.5000 | 0.9911 | 0.6627 | 0.0089 |
| PaddleOCR single engine | 0.7723 | 0.9552 | 0.5714 | 0.9732 | 0.7151 | 0.0268 |
| OpenOCR single engine | 0.7143 | 0.9800 | 0.4375 | 0.9911 | 0.6049 | 0.0089 |
| Any engine | 0.7902 | 0.9452 | 0.6161 | 0.9643 | 0.7459 | 0.0357 |
| Majority vote | 0.7411 | 0.9821 | 0.4911 | 0.9911 | 0.6548 | 0.0089 |
| Unanimous vote | 0.7009 | 1.0000 | 0.4018 | 1.0000 | 0.5732 | 0.0000 |
| Safety weighted | 0.7902 | 0.9710 | 0.5982 | 0.9821 | 0.7403 | 0.0179 |
| Government safe | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 |

Latency for the three-engine ensemble is currently reported as a conservative
sequential sum: mean `3,703.95 ms/application`, max `6,940 ms/application` on
the 20-application smoke. A production implementation could run the three OCR
engines in parallel, but that has not been implemented or measured.

The government-safe ensemble is the most important result: it improved F1 over
all single engines in this smoke and drove false-clear rate to zero by requiring
unanimous OCR support for alcohol-content evidence. This should be tested on the
larger calibration set before any runtime change.

### WineBERT/o Domain-NER Smoke

WineBERT/o was tested as a post-OCR entity arbiter over combined docTR,
PaddleOCR, and OpenOCR text. The point was to see whether a wine-domain token
classifier could clean up brand, fanciful-name, class/type, origin, or producer
evidence before the graph scorer or deterministic validator.

| Model / policy | Accuracy | Precision | Recall | Specificity | F1 | False-clear rate | Mean BERT / app | Max BERT / app |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WineBERT/o labels, entities only | 0.6607 | 1.0000 | 0.3214 | 1.0000 | 0.4865 | 0.0000 | 261.25 ms | 660 ms |
| WineBERT/o labels + government-safe ensemble | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 | 261.25 ms | 660 ms |
| WineBERT/o NER, entities only | 0.5312 | 1.0000 | 0.0625 | 1.0000 | 0.1176 | 0.0000 | 189.30 ms | 432 ms |
| WineBERT/o NER + government-safe ensemble | 0.7946 | 1.0000 | 0.5893 | 1.0000 | 0.7416 | 0.0000 | 189.30 ms | 432 ms |

By-field WineBERT/o-labels entity-only F1:

| Field | F1 | Recall | False-clear rate |
|---|---:|---:|---:|
| Brand name | 0.7500 | 0.6000 | 0.0000 |
| Fanciful name | 0.8235 | 0.7000 | 0.0000 |
| Class/type | 0.5714 | 0.4000 | 0.0000 |
| Alcohol content | 0.0000 | 0.0000 | 0.0000 |
| Net contents | 0.0000 | 0.0000 | 0.0000 |
| Country of origin | 0.3636 | 0.2222 | 0.0000 |
| Applicant / producer | 0.0000 | 0.0000 | 0.0000 |

Interpretation:

- WineBERT/o-labels is safe but low recall when used as entity-only evidence.
- WineBERT/o does not extract ABV or net contents, so it cannot be the main
  compliance arbiter for this workflow.
- Hybrid WineBERT/o support tied the government-safe deterministic ensemble but
  did not improve it.
- Lowering the threshold to `80` increased recall but raised the false-clear
  rate to `0.0714`, which is unacceptable for the current government-safe
  posture.
- The public model license is listed as unknown, so the deployment path would
  require replacement with an internally trained or clearly licensed model.

## May 2 COLA Cloud Stratified Calibration

After the sample-pack smoke test, a bounded COLA Cloud API sampling workflow
created a 1,500-record stratified evaluation plan under gitignored
`data/work/cola/official-sample-1500-balanced/`. The plan selected from 7,788
candidate records across May 1, 2025 through April 30, 2026 using deterministic
random business-day clusters within month strata, then balanced by product
type, domestic/import bucket, and single-panel versus multi-panel image
complexity.

The first 100 selected records were fetched as a calibration set and evaluated
with local docTR inside the Podman app image.

| Metric | Result |
|---|---:|
| Planned sample size | 1,500 applications |
| Candidate pool | 7,788 applications |
| Calibration details fetched | 100 applications |
| Calibration label images OCR'd | 169 images |
| Mean latency per application | 1,413 ms |
| Max latency per application | 3,620 ms |
| Brand-name match rate | 71% |
| Fanciful-name match rate | 65% |
| Country-origin match rate | 78.95% of 38 attempted |
| Class/type match rate | 49% |
| Alcohol-content match rate | 91.49% of 94 attempted |
| Net-contents match rate | 83.72% of 86 attempted |

This is a calibration result, not final model accuracy. It proves that the
bounded API corpus, image download, local OCR, and field-comparison pipeline all
work on recent real public COLA label images within Sarah's 5-second usability
target.

The first calibration pass exposed two mapping gaps: COLA Cloud detail records
contained `abv`, `volume`, and `volume_unit`, but the importer was leaving
`alcohol_content` and `net_contents` blank; class/type descriptions also needed
basic synonym expansion such as `MEZCAL FB -> mezcal` and `STRAIGHT BOURBON
WHISKY -> bourbon/whisky/whiskey`. After remapping and adding those evaluation
candidates, ABV and net-contents became measurable fields and class/type
matching improved from 16% to 49%.

The next defensible measurement design is a 3,000-application corpus split into:

| Split | Size | Purpose |
|---|---:|---|
| Calibration/tuning | 1,500 applications | Tune OCR preprocessing, field normalization, and pass/review thresholds. |
| Locked holdout | 1,500 applications | Report final OCR/field-match rates after tuning decisions are frozen. |

The sampler has been dry-run locally against the existing 7,788-record candidate
pool and produced exact split counts of 1,500 calibration and 1,500 holdout
applications without replacement.

For a binary proportion measured on the 1,500-record holdout, the conservative
95% margin of error is approximately `1.96 * sqrt(0.25 / 1500) = 2.53`
percentage points before finite-population correction. With an annual COLA
population around 150,000 applications, the finite-population correction changes
that only slightly, to about 2.52 percentage points. This is the basis for the
"about +/- 2.5 percentage points" claim. It is a margin of error for the locked
holdout estimate, not a guarantee of production accuracy.
