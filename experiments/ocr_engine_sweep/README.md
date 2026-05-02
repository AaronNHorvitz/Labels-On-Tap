# OCR Engine Sweep

This experiment compares local OCR engines without changing the deployed
runtime path. The current production-safe baseline remains docTR with fixture
OCR fallback. Alternate engines must earn promotion with measured accuracy,
latency, and failure behavior.

## Candidate Order

| Engine | Role | Status |
|---|---|---|
| docTR | Current local baseline | Implemented in app runtime |
| PaddleOCR / PP-OCR | First alternate local OCR candidate | Smoke harness started |
| OpenOCR / SVTRv2 | Second alternate local OCR candidate | Research candidate |
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
python -m pip install paddleocr
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

Outputs are written under gitignored `data/work/ocr-engine-sweep/`.

## Notes

- This harness measures OCR extraction only. Field-level comparison should use
  the existing public COLA evaluator once an engine can produce normalized OCR.
- OpenVINO/ONNX/INT8 is intentionally deferred until a candidate engine wins a
  normal CPU benchmark.
- The full HO-GNN/TPS/SVTR architecture remains future research, not the
  Monday-critical runtime path.
