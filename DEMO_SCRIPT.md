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

## 3. LOT Demo: Public COLA Walkthrough

From the home page:

1. Click `LOT Demo`.
2. Show that the page has 300 public COLA applications loaded.
3. Use `Next Application` and `Next Photo` to show multiple application panels.
4. Point out the `Actual` column under the image. These are the application
   truth fields.
5. Click `Parse This Application`.
6. Show the `Scraped` column filling in beside the actual fields.
7. Click `Parse This Directory of Applications` if you want to show the full
   300-application progress and timing path.

Point out:

- result counts,
- policy queues,
- Actual vs Scraped field comparison,
- reviewer action buttons,
- CSV export.

## 4. LOT Actual: Upload Path

From the home page:

1. Click `LOT Actual`.
2. Click `Download Examples` if you want a ready-made upload pack.
3. Click `Data Format Instructions` to show the expected folder and manifest
   layout.
4. Upload one application folder or a folder of applications.
5. Browse the uploaded panels.
6. Parse one application or parse the directory.
7. Explain that the upload remains available in that browser until `Reset`.

## 5. Evidence Detail

Open one result card from a job page.

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
Accept or Reject
```

Point out that the saved decision appears immediately on the job page and is
included in CSV export.

## 6. Reviewer Dashboard

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
