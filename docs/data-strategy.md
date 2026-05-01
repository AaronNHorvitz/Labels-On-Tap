# Data Strategy

Labels On Tap uses a data contract that separates runtime user data, deterministic demo/test fixtures, optional public examples, and source-backed legal rules.

## Runtime Data

At runtime, reviewers provide:

```text
label image uploads
Form 5100.31-style application fields
batch manifest CSV/JSON files, where applicable
```

The app runs local OCR and source-backed validation against those user-provided inputs. It does not train a model from uploaded labels.

## Demo And Test Data

Core demo and test data is generated inside the repository:

```bash
python scripts/bootstrap_project.py
```

The bootstrap creates:

```text
data/fixtures/demo/
data/source-maps/fixture-provenance.json
data/source-maps/expected-results.json
```

Synthetic fixtures are preferred for the required test path because they are deterministic, offline-safe, and mapped to known expected results.

## Public Approved Data

Public approved COLA labels may be curated later for realistic OCR examples, typography variation, and manual demo enrichment.

They are optional. Tests and one-click demos should not depend on scraping or live registry access.

## Post-Market Public Data

Public surrendered or revoked registry records may be useful as post-market anomaly context. They are not treated as examples of confidential pre-market rejected or Needs Correction applications.

## Data Not Used

Labels On Tap does not rely on:

- confidential rejected or Needs Correction COLA applications,
- live registry scraping during tests or runtime,
- hosted OCR/LLM enrichment,
- third-party data services as runtime dependencies.

See `docs/fixture-generation.md` for the generated fixture contract.
