# Trade-Offs

The MVP chooses a working, explainable reviewer-support slice over broad regulatory coverage.

- Demo/test fixtures are synthetic and source-backed so tests are reproducible without confidential rejected-label data.
- Fixture OCR fallback makes demos deterministic while preserving a local docTR adapter for real uploads.
- Filesystem job storage avoids database setup for the take-home; production should use an approved durable store with audit and retention controls.
- Warning text and capitalization are deterministic checks. Boldness and typography route to Needs Review instead of brittle hard failure from raster images.
- Raw Pass / Needs Review / Fail outcomes are triage verdicts. A planned reviewer-policy control board can require human approval for candidate acceptances, candidate rejections, and unknown government-warning evidence.
- Unknown/unverifiable government-warning evidence defaults to failure when the warning-review gate is off because the warning is mandatory.
- Photo OCR intake is included as a demonstration aid for real phone photos, but it does not produce verification verdicts without application fields.
- The public COLA example comparison demo reads gitignored local COLA Cloud-derived records and images when present, but it is not a runtime dependency and may show a missing-data page on hosts without that local corpus.
- Manual manifest-backed batch upload is implemented synchronously in the web process for the sprint. A production batch workflow should move OCR work to a background queue.
- ZIP upload is intentionally out of scope for the first MVP because safe archive handling would add risk and testing burden.
