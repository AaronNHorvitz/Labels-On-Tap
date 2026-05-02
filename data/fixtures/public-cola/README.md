# Public COLA Fixtures

This directory is reserved for small, curated fixtures exported from official TTB Public COLA Registry records.

Bulk registry pulls, downloaded form HTML, raw label images, OCR outputs, and the local SQLite index belong in the gitignored `data/work/public-cola/` workspace. Only reviewer-safe fixtures with clear provenance should be committed here.

Expected layout:

```text
data/fixtures/public-cola/
  <ttb_id>/
    source.html
    application.json
    labels/
    expected.json
    provenance.json
```

Runtime tests and one-click demos should use committed fixtures or generated synthetic fixtures, not live registry scraping.
