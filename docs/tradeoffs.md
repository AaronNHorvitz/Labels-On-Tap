# Trade-Offs

The MVP chooses a working, explainable reviewer-support slice over broad regulatory coverage.

- Demo/test fixtures are synthetic and source-backed so tests are reproducible without confidential rejected-label data.
- Fixture OCR fallback makes demos deterministic while preserving a local docTR adapter for real uploads.
- Filesystem job storage avoids database setup for the take-home; production should use an approved durable store with audit and retention controls.
- Warning text and capitalization are deterministic checks. Boldness and typography route to Needs Review instead of brittle hard failure from raster images.
- Manual manifest-backed batch upload is implemented synchronously in the web process for the sprint. A production batch workflow should move OCR work to a background queue.
- ZIP upload is intentionally out of scope for the first MVP because safe archive handling would add risk and testing burden.
