# OCR Conveyor Layer

The OCR conveyor is the project layer that makes the max-win architecture safe
to execute over thousands of public COLA label images.

```text
COLA label images
  -> image preflight
  -> resumable OCR job manifest
  -> subprocess-isolated docTR / PaddleOCR / OpenOCR chunks
  -> normalized OCR JSON + rows.csv
  -> OCR evidence attachment
  -> DistilRoBERTa field-support arbiter
  -> graph-aware evidence scorer
  -> deterministic compliance rules
```

## Why This Layer Exists

Normal Python `try/except` is not enough for a long OCR run. It catches ordinary
exceptions, but it cannot safely recover from every native runtime failure:

- segmentation faults
- ONNX/Paddle/OpenCV aborts
- hard out-of-memory kills
- corrupt images that trigger native decoder errors
- engine initialization failures

The conveyor treats each OCR engine and image chunk as a separate subprocess.
If one subprocess fails, the parent records the failure and continues.

## Safety Contract

The conveyor must:

- preflight image signatures before OCR,
- validate image decoding with Pillow,
- skip invalid images before engine calls,
- write a manifest of every discovered image,
- write a manifest of every OCR chunk job,
- write stdout/stderr logs per job,
- record `completed`, `subprocess_failed`, `timeout`, or `incomplete_rows`,
- support resume by skipping completed jobs,
- keep all OCR artifacts under gitignored `data/work/`.

## Command

Dry run over train and validation:

```bash
python scripts/run_ocr_conveyor.py \
  --split train \
  --split validation \
  --engine doctr \
  --engine paddleocr \
  --engine openocr \
  --chunk-size 8 \
  --dry-run
```

Real run:

```bash
python scripts/run_ocr_conveyor.py \
  --split train \
  --split validation \
  --engine doctr \
  --engine paddleocr \
  --engine openocr \
  --chunk-size 8 \
  --timeout-seconds 900
```

Holdout run, after all preprocessing/model/threshold choices are frozen:

```bash
python scripts/run_ocr_conveyor.py \
  --split holdout \
  --engine doctr \
  --engine paddleocr \
  --engine openocr \
  --chunk-size 8 \
  --timeout-seconds 900
```

Outputs:

```text
data/work/ocr-conveyor/tri-engine-v1/
  manifest/
    images.csv
    jobs.csv
  jobs/
    <job_id>/
      stdout.log
      stderr.log
      result.json
  runs/
    <job_id>/
      rows.csv
      summary.json
      ocr/
        <engine>/
          *.json
  summary.json
```

## Current Decision

The deployed app remains stable while this experiment runs offline. No
tri-engine/BERT/graph path becomes the runtime default until it beats the
current baseline on validation, survives the locked holdout, and fits the CPU
latency budget.
