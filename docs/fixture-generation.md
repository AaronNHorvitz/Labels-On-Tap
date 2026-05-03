# Fixture Generation

Labels On Tap generates deterministic demo and test fixtures inside the repository. This keeps the project runnable before any public COLA examples are curated and avoids relying on confidential rejected or Needs Correction applications.

## Command

```bash
python scripts/bootstrap_project.py
```

This command runs:

```text
scripts/bootstrap_legal_corpus.py
scripts/seed_demo_fixtures.py
scripts/validate_legal_corpus.py
```

To regenerate fixture images and metadata:

```bash
python scripts/bootstrap_project.py --force
```

## Generated Files

The fixture generator writes PNG labels, application payloads, expected results, OCR text ground truth, and batch manifests:

```text
data/fixtures/demo/
  clean_malt_pass.png
  warning_missing_comma_fail.png
  warning_title_case_fail.png
  abv_prohibited_fail.png
  malt_16_fl_oz_fail.png
  brand_case_difference_pass.png
  low_confidence_blur_review.png
  brand_mismatch_fail.png
  imported_missing_country_review.png
  conflicting_country_origin_fail.png
  warning_missing_block_review.png
  imported_country_origin_pass.png
  batch_manifest.csv
  batch_manifest.json
```

For each label, it also writes:

```text
{fixture_id}.application.json
{fixture_id}.expected.json
{fixture_id}.ocr_text.json
```

The source maps live in:

```text
data/source-maps/fixture-provenance.json
data/source-maps/fixture-provenance.md
data/source-maps/expected-results.json
```

## Fixture Contract

Each fixture has:

- a synthetic label image,
- Form 5100.31-style application fields,
- expected Pass / Needs Review / Fail outcome,
- expected reviewer-policy queue when policy-routing tests are added,
- checked rule IDs,
- triggered rule IDs for Fail or Needs Review outcomes,
- source references,
- OCR-text ground truth for deterministic unit tests.

The intended test split is:

```text
unit tests
  use generated .ocr_text.json payloads and expected results

integration tests
  run generated PNG labels through the OCR pipeline
```

This keeps most tests fast and deterministic while still supporting full image-to-result coverage.

## Public COLA Data

Public approved COLA records may be curated later for OCR realism and demo enrichment. They should not be required for test setup, CI, or one-click evaluator demos.

The core test data should remain synthetic, source-backed, offline-safe, and reproducible.
