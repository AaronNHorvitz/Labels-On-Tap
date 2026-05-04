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

## Current Model-Selection Evidence

The latest typography comparison is the valid one to cite for model selection:
every base learner and ensemble used the same `audit-v6` split, with ensemble
stackers trained on five-fold out-of-fold probabilities from SVM, XGBoost,
LightGBM, Logistic Regression, MLP, CatBoost, and MobileNetV3 CNN.

| Type | Model / Policy | Test F1 | Test false-clear |
|---|---|---:|---:|
| Base model | MobileNetV3 CNN | 0.9686 | 0.0055 |
| Ensemble | Logistic stacker + CNN | 0.9908 | 0.0099 |
| Ensemble | LightGBM reject + CNN | 0.9552 | 0.0033 |
| Ensemble | XGBoost reject + CNN | 0.9656 | 0.0044 |

Trade-off: raw-F1 stackers look strongest on F1, but reject-threshold ensembles
better match the government false-clear posture. The MVP runtime therefore
keeps the simpler real-adapted JSON logistic bridge while documenting the
CNN-inclusive reject ensembles as promotion candidates.
