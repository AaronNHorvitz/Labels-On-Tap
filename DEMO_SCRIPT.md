# Demo Script

Public URL:

```text
https://www.labelsontap.ai
```

## 1. Open With The Point

"Labels On Tap triages COLA-style alcohol label submissions by comparing
application fields against OCR evidence from label artwork. It does not replace
reviewers; it routes routine matches, mismatches, and uncertain cases into a
review queue with source-backed reasons."

## 2. Health Check

Open:

```text
https://www.labelsontap.ai/health
```

Expected:

```json
{"status":"ok"}
```

## 3. Fast Fixture Demos

From the home page:

1. Run Clean Label Demo.
2. Run Warning Failure Demo.
3. Run ABV Failure Demo.
4. Run Malt Net Contents Failure Demo.
5. Run Import Origin Demo.
6. Run Batch Demo.

Point out:

- result counts,
- policy queues,
- top reason,
- item detail links,
- CSV export.

## 4. Evidence Detail

Open one failed or review item.

Show:

- application fields,
- submitted label image,
- warning-heading crop when available,
- OCR blocks,
- rule checks,
- expected vs observed values,
- source refs,
- reviewer action,
- full OCR text.

Save a reviewer decision:

```text
Request correction / better image
```

## 5. Reviewer Dashboard

Open:

```text
/review
```

Show:

- Ready to accept,
- Acceptance review,
- Manual evidence review,
- Rejection review,
- Ready to reject.

Explain that auth/admin/roles are future production work; this prototype focuses
on the queue mechanics and evidence flow.

## 6. Batch Upload

Use the home page batch form.

Inputs:

- `manifest.csv` or `manifest.json`,
- loose JPG/PNG images or a ZIP archive of images.

Show:

- immediate redirect to job page,
- queue status,
- incremental results,
- CSV export.

## 7. Photo OCR Intake

Upload one local phone photo of a bottle/can/shelf label.

Explain:

- this is OCR exploration,
- it parses likely fields,
- it is not a formal COLA verification unless application fields are supplied.

## 8. Model / Measurement Summary

Useful talking points:

- Local-first OCR avoids hosted ML endpoints.
- DistilRoBERTa is optional field-support evidence, not the compliance judge.
- Warning-heading boldness uses a conservative low-latency model.
- Graph and CNN ensembles are documented future promotion candidates, not hidden
  runtime claims.

## 9. Close

"The core deliverable is working: deployed URL, runnable repo, upload workflows,
batch triage, reviewer dashboard, CSV export, source-backed decisions, and
documented trade-offs."
