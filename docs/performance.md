# Performance

The prototype target is roughly five seconds per single label after OCR warmup, dependent on image size, VM resources, and OCR model cache state.

The current demo routes use fixture OCR ground truth so evaluator demos are immediate and deterministic. Real uploads use local docTR when installed; first-run model loading may be slower than steady-state processing.

Each result records OCR source and confidence. Future benchmarking should record:

- VM size,
- OCR engine,
- fixture count,
- p50 and p95 per-label processing time,
- first-run warmup time,
- batch completion time.
