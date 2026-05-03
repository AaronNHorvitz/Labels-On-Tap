# OCR Engine Sweep

This experiment compares local OCR engines without changing the deployed
runtime path. The current production-safe baseline remains docTR with fixture
OCR fallback. Alternate engines must earn promotion with measured accuracy,
latency, and failure behavior.

## Candidate Order

| Engine | Role | Status |
|---|---|---|
| docTR | Current local baseline | Implemented in app runtime |
| PaddleOCR / PP-OCR | First alternate local OCR candidate | 30-image smoke benchmark and field-support metrics recorded |
| OpenOCR / SVTRv2 | Second alternate local OCR candidate | 30-image smoke benchmark and field-support metrics recorded |
| PARSeq | Scene-text recognizer over detected crops | AR and NAR crop-recognition smoke benchmarks recorded |
| ASTER | Rectifying scene-text recognizer over detected crops | MMOCR ASTER crop-recognition smoke benchmark recorded |
| FCENet + ASTER | Fourier-contour detector plus rectifying recognizer | MMOCR detector-recognizer smoke benchmark recorded |
| Graph scorer | Post-OCR field evidence scorer | Implemented under `experiments/graph_ocr/` |

## Promotion Gate

An engine can become the deployed default only if it satisfies all of these:

```text
- runs locally without hosted OCR or hosted ML APIs,
- normalizes output to OCRResult-compatible text/blocks/confidence/timing,
- improves field matching on public COLA calibration data,
- does not increase false clears on synthetic known-bad fixtures,
- meets the five-second per-label target after warmup,
- has a clean Docker/deployment rollback path.
```

## Local Smoke

Use a separate environment so production dependencies stay stable:

```bash
python -m venv .venv-ocr-sweep
source .venv-ocr-sweep/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install optional engines only inside that environment:

```bash
python -m pip install paddlepaddle==3.2.0 paddleocr==3.3.3
```

Then run a small smoke benchmark:

```bash
python experiments/ocr_engine_sweep/benchmark_ocr_engines.py \
  --engine doctr \
  --image-glob 'data/work/public-cola/raw/images/*/*' \
  --limit 10
```

If PaddleOCR is installed:

```bash
python experiments/ocr_engine_sweep/benchmark_ocr_engines.py \
  --engine paddleocr \
  --image-glob 'data/work/public-cola/raw/images/*/*' \
  --limit 10
```

If OpenOCR is installed:

```bash
python -m pip install openocr-python==0.1.5
python experiments/ocr_engine_sweep/benchmark_ocr_engines.py \
  --engine openocr \
  --image-glob 'data/work/public-cola/raw/images/*/*' \
  --limit 10
```

Outputs are written under gitignored `data/work/ocr-engine-sweep/`.

## Statistical Caution

The initial 20-application / 30-image smoke is intentionally small. Small
sample sizes increase variance, so early F1, accuracy, recall, and false-clear
rates are directional calibration evidence only. PaddleOCR's higher F1 in the
first smoke is a real reason to keep testing it, not enough evidence to promote
it. OpenOCR's fast latency is also a real reason to keep testing it, not enough
evidence to pick it despite lower first-pass F1.

PARSeq is a recognizer-stage experiment. It requires detected text crops, so
its crop benchmark is not a full OCR pipeline benchmark. The first PARSeq run
uses OpenOCR boxes as the crop source and reports recognizer-plus-cropping
latency separately from detector-inclusive OCR latency.

ASTER is also a recognizer-stage experiment. It includes a flexible
rectification mechanism, but still requires detected text crops in this smoke
contract. The first ASTER run uses OpenOCR boxes as the crop source and reports
recognizer-plus-cropping latency separately from detector-inclusive OCR
latency.

FCENet is a detector-stage experiment. It predicts arbitrary-shaped text
contours using Fourier-domain signatures, so the first project benchmark pairs
FCENet detection with ASTER recognition and reports full detector-plus-recognizer
latency.

## PARSeq Crop Recognition

Install the optional standalone PARSeq stack in an isolated environment or
container:

```bash
python -m pip install pydantic pillow
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install timm einops pytorch-lightning hydra-core nltk lmdb
```

Then run PARSeq over previously detected OpenOCR boxes:

```bash
python experiments/ocr_engine_sweep/parseq_crop_benchmark.py \
  --box-run-dir data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --box-engine openocr \
  --limit 30 \
  --device cpu \
  --decode-ar \
  --refine-iters 1 \
  --run-name parseq-openocr-crops-ar-smoke-30
```

The non-autoregressive/refinement variant:

```bash
python experiments/ocr_engine_sweep/parseq_crop_benchmark.py \
  --box-run-dir data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --box-engine openocr \
  --limit 30 \
  --device cpu \
  --no-decode-ar \
  --refine-iters 2 \
  --run-name parseq-openocr-crops-nar-r2-smoke-30
```

## ASTER Crop Recognition

Install the optional MMOCR ASTER stack in an isolated Python 3.10 environment
or container:

```bash
python -m pip install "pip<25" setuptools wheel
python -m pip install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cpu
python -m pip install openmim
python -m mim install "mmcv==2.0.1"
python -m pip install mmdet==3.0.0 mmocr==1.0.1
python -m pip install --force-reinstall "numpy<2"
```

Then run ASTER over previously detected OpenOCR boxes:

```bash
python experiments/ocr_engine_sweep/aster_crop_benchmark.py \
  --box-run-dir data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --box-engine openocr \
  --limit 30 \
  --batch-size 32 \
  --device cpu \
  --run-name aster-openocr-crops-smoke-30
```

## FCENet + ASTER Detector/Recognizer

Use the same isolated MMOCR environment as ASTER, then run:

```bash
python experiments/ocr_engine_sweep/fcenet_aster_benchmark.py \
  --image-run-dir data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --image-engine openocr \
  --limit 30 \
  --batch-size 32 \
  --device cpu \
  --min-score 0.5 \
  --max-crops-per-image 128 \
  --run-name fcenet-aster-smoke-30
```

## PaddleOCR Version Notes

The first working CPU smoke used:

```text
paddlepaddle==3.2.0
paddleocr==3.3.3
```

PaddleOCR 3.5.0 and PaddlePaddle 3.3.1 installed, but CPU inference hit a
oneDNN/PIR runtime error in this container. Disabling MKLDNN allowed that newer
stack to run, but it averaged roughly five seconds per image on the first
10-image smoke. The pinned 3.3.3/3.2.0 stack completed the 30-image smoke with
mean latency near 1.10 seconds per image.

The benchmark writes both compact CSV metrics and normalized OCR JSON artifacts
for later field-level comparison.

## Field-Support Metrics

After a smoke run produces normalized OCR JSON, compute side-by-side
classification metrics against cached docTR:

```bash
python experiments/ocr_engine_sweep/field_support_metrics.py \
  --paddle-run-dir data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json \
  --run-name paddle-vs-doctr-smoke-30
```

Or compare multiple engines:

```bash
python experiments/ocr_engine_sweep/field_support_metrics.py \
  --engine-run paddleocr=data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json \
  --engine-run openocr=data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --run-name doctr-vs-paddle-vs-openocr-smoke-30
```

Including PARSeq crop runs:

```bash
python experiments/ocr_engine_sweep/field_support_metrics.py \
  --engine-run paddleocr=data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json \
  --engine-run openocr=data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --engine-run parseq_ar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-ar-smoke-30 \
  --engine-run parseq_nar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-nar-r2-smoke-30 \
  --run-name doctr-vs-paddle-vs-openocr-vs-parseq-ar-nar-smoke-30
```

Including ASTER crop runs:

```bash
python experiments/ocr_engine_sweep/field_support_metrics.py \
  --engine-run paddleocr=data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json \
  --engine-run openocr=data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --engine-run parseq_ar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-ar-smoke-30 \
  --engine-run parseq_nar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-nar-r2-smoke-30 \
  --engine-run aster_openocr_crops=data/work/ocr-engine-sweep/aster-openocr-crops-smoke-30 \
  --run-name doctr-vs-paddle-vs-openocr-vs-parseq-vs-aster-smoke-30
```

Including FCENet + ASTER:

```bash
python experiments/ocr_engine_sweep/field_support_metrics.py \
  --engine-run paddleocr=data/work/ocr-engine-sweep/paddleocr-333-paddle-320-smoke-30-json \
  --engine-run openocr=data/work/ocr-engine-sweep/openocr-015-mobile-poly-smoke-30 \
  --engine-run parseq_ar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-ar-smoke-30 \
  --engine-run parseq_nar_openocr_crops=data/work/ocr-engine-sweep/parseq-openocr-crops-nar-r2-smoke-30 \
  --engine-run aster_openocr_crops=data/work/ocr-engine-sweep/aster-openocr-crops-smoke-30 \
  --engine-run fcenet_aster=data/work/ocr-engine-sweep/fcenet-aster-smoke-30 \
  --run-name doctr-vs-paddle-vs-openocr-vs-parseq-vs-aster-vs-fcenet-smoke-30
```

This writes summary JSON and per-engine score CSVs under:

```text
data/work/ocr-engine-sweep/field-support-metrics/
```

The current metric task treats accepted application fields as positive examples
and uses same-field shuffled values from other applications as controlled
negative examples. It is a smoke metric, not final production accuracy.

## Notes

- This harness measures OCR extraction only. Field-level comparison should use
  the existing public COLA evaluator once an engine can produce normalized OCR.
- OpenVINO/ONNX/INT8 is intentionally deferred until a candidate engine wins a
  normal CPU benchmark.
- The full HO-GNN/TPS/SVTR architecture remains future research, not the
  Monday-critical runtime path.
