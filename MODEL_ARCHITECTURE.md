# MODEL_ARCHITECTURE.md - Labels On Tap Model Architecture

**Project:** Labels On Tap
**Canonical URL:** `https://www.labelsontap.ai`
**Last updated:** May 3, 2026

This document explains the current and planned model architecture from raw COLA
application data through OCR, field matching, deterministic compliance scoring,
and final reviewer-facing verdicts.

The short version:

```text
COLAs Online-style application data
  + all submitted label-artwork panels for that application
  -> local OCR evidence
  -> field-support scoring
  -> deterministic safety policy
  -> Pass / Needs Review / Fail with evidence
```

The deployed prototype is intentionally conservative. It does not use hosted OCR
or hosted ML APIs, and it does not let a language model decide compliance.

---

## 1. Product Objective

Labels On Tap is designed to triage COLAs Online-style alcohol label submissions
and identify labels that appear out of compliance or do not match the submitted
application data.

The model problem is not "approve labels automatically." The model problem is:

```text
Given accepted application fields and submitted label artwork,
can the system find enough label evidence to support those fields?
```

That keeps the architecture auditable:

- OCR extracts text evidence from label images.
- Field-support logic compares OCR evidence to application fields.
- Rules and safety policy decide whether evidence is strong, missing, or
  contradictory.
- Human reviewers get the evidence and reviewer action.

---

## 2. End-To-End Runtime Flow

```mermaid
flowchart TD
    A["Reviewer or applicant uploads<br/>application fields + label images"] --> B["FastAPI route"]
    B --> C["Upload preflight<br/>extension, signature, size, Pillow decode"]
    C --> D["Filesystem job store<br/>randomized filenames"]
    D --> E{"Fixture/demo file?"}
    E -->|Yes| F["Fixture OCR ground truth<br/>deterministic demos/tests"]
    E -->|No| G["Local OCR adapter<br/>current runtime: docTR"]
    F --> H["Normalized OCRResult<br/>text + boxes + confidence + source"]
    G --> H
    H --> I["Field matching<br/>RapidFuzz + normalization"]
    I --> J["Deterministic rule engine<br/>source-backed checks"]
    J --> K["Safety policy<br/>Pass only on strong evidence"]
    K --> L["Pass"]
    K --> M["Needs Review"]
    K --> N["Fail"]
    L --> O["Result table, item detail,<br/>CSV export, evidence"]
    M --> O
    N --> O
```

Current deployed runtime:

| Layer | Runtime Choice |
|---|---|
| Web app | FastAPI |
| UI | Jinja2 + HTMX + local CSS |
| Storage | Filesystem JSON job/result store |
| OCR | docTR for real uploads, fixture OCR for deterministic demos |
| Matching | RapidFuzz and source-backed deterministic checks |
| Deployment | Docker Compose + Caddy on AWS Lightsail |

The deployed app is stable and intentionally does not yet depend on heavy
experimental OCR or Transformer models.

---

## 3. Data Inputs

There are three separate data classes. They must stay separate.

| Data Class | Purpose | Runtime Dependency | Storage |
|---|---|---:|---|
| User/demo uploads | Actual app workflow and one-click demos | Yes | `data/jobs/` at runtime |
| Synthetic fixtures | Known Pass/Needs Review/Fail regression tests | Yes for demos/tests | `data/fixtures/demo/` |
| Official public COLA examples | OCR and field-matching evaluation corpus | No | gitignored `data/work/` |

The official public COLA examples are used for evaluation, not runtime. The app
should be able to run without COLA Cloud, TTB registry scraping, or any hosted
data service. The current measured OCR/model calibration set is COLA
Cloud-derived public COLA data because the direct TTB attachment endpoint was
unstable during the sprint. The direct TTB Public COLA Registry parser remains
the official printable-form path, but those direct attachment downloads are not
the source of the current model metrics.

### Multi-Panel Application Contract

One COLA application can include multiple label-artwork panels:

```text
front label
back label
neck label
keg collar
government warning panel
other affixed materials
```

For field matching, the application is the unit of analysis. All valid label
images associated with one application must be OCR'd and pooled before deciding
whether the label artwork supports an application field.

```mermaid
flowchart LR
    A["COLA application<br/>TTB ID"] --> B["Application fields<br/>brand, class/type, ABV,<br/>net contents, origin"]
    A --> C["Label panel 1"]
    A --> D["Label panel 2"]
    A --> E["Label panel N"]
    C --> F["OCR text blocks"]
    D --> F
    E --> F
    F --> G["Application-level evidence pool"]
    B --> H["Field-support scorer"]
    G --> H
    H --> I["Field verdicts"]
```

---

## 4. Official Evaluation Corpus

The evaluation corpus should be built from accepted public COLA records because
they provide a safe public proxy for the form-data-to-label-artwork matching
task.

The current evaluation design is a locked application-level split:

```text
2,000 train applications
1,000 validation applications
3,000 locked holdout applications
```

The split must happen at the COLA application level before field-pair examples
are generated. This prevents leakage where the same TTB ID, brand, producer, or
OCR text appears in both training and test examples.

```mermaid
flowchart TD
    A["Public COLA candidate pool"] --> B["Validate metadata + image files"]
    B --> C["Stratify by month,<br/>product family, import/domestic,<br/>panel complexity"]
    C --> D["Sample applications<br/>without replacement"]
    D --> E["Application-level split"]
    E --> F["Train<br/>2,000 applications"]
    E --> G["Validation<br/>1,000 applications"]
    E --> H["Locked holdout<br/>3,000 applications"]
    F --> I["Generate field-support examples"]
    G --> J["Tune thresholds and model selection"]
    H --> K["Final reported metrics only"]
```

The validation set is used for:

- threshold selection,
- model-family selection,
- safety policy tuning,
- preprocessing decisions.

The locked test set is used once after those settings are frozen.

### OCR Conveyor Safety Layer

The max-win experimental path runs three OCR engines before BERT/graph scoring:

```text
docTR + PaddleOCR + OpenOCR
  -> DistilRoBERTa field-support arbiter
  -> graph-aware evidence scorer
  -> deterministic compliance rules
```

That path must run through the armored OCR conveyor before final evidence
attachment. The conveyor preflights image bytes, validates Pillow decode,
creates a resumable image/job manifest, and executes OCR chunks in subprocesses
so a native engine failure cannot kill the entire run.

```mermaid
flowchart TD
    A["Application split manifests"] --> B["Discover label image files"]
    B --> C["Signature + Pillow preflight"]
    C -->|invalid| D["Record skipped image"]
    C -->|valid| E["OCR chunk manifest"]
    E --> F["docTR subprocess chunks"]
    E --> G["PaddleOCR subprocess chunks"]
    E --> H["OpenOCR subprocess chunks"]
    F --> I["Normalized OCR JSON + rows.csv"]
    G --> I
    H --> I
    I --> J["OCR evidence attachment"]
    J --> K["DistilRoBERTa + graph scorer"]
```

The conveyor is implemented in `scripts/run_ocr_conveyor.py` and documented in
`docs/ocr-conveyor.md`. Outputs remain under gitignored `data/work/`.

After final test reporting, a production model may be retrained on train plus
validation, or eventually on all approved labeled internal data, but the
reported performance estimate must remain tied to the untouched locked test.

---

## 5. OCR Layer

The OCR layer reads image pixels and emits normalized evidence:

```text
text
bounding boxes / polygons where available
confidence where available
source engine
timing
```

Current and tested OCR paths:

| OCR Path | Status | Decision |
|---|---|---|
| docTR | Deployed baseline | Keep stable runtime path |
| PaddleOCR | 30-image smoke: higher F1, higher false-clear rate | Still in contention, needs larger calibration |
| OpenOCR / SVTRv2 | 30-image smoke: fastest complete OCR candidate | Still in contention, needs larger calibration |
| PARSeq / ASTER / ABINet over crops | Fast recognizer-stage experiments | Pruned from runtime promotion in current crop contract |
| FCENet + ASTER | Arbitrary-shape detector experiment | Pruned for CPU latency and low F1 in smoke |

```mermaid
flowchart TD
    A["Label image panel"] --> B["docTR baseline"]
    A --> C["PaddleOCR candidate"]
    A --> D["OpenOCR / SVTRv2 candidate"]
    B --> E["Normalized OCR blocks"]
    C --> E
    D --> E
    E --> F["Per-engine field-support scores"]
    F --> G["Deterministic arbitration"]
```

The Monday runtime should not switch OCR engines just because a smoke test looks
interesting. An OCR candidate must win on a larger calibration set and preserve
the false-clear posture before promotion.

---

## 6. Field-Support Scoring

Field-support scoring asks a narrow question:

```text
Does OCR evidence support this expected application field?
```

Target fields:

| Field | Why It Matters |
|---|---|
| Brand name | Common agent matching task |
| Fanciful name | Common label/application text field |
| Class/type | Required designation, currently difficult |
| Alcohol content | High-value numeric field |
| Net contents | Required label element |
| Country of origin | Required for imports |
| Applicant/producer/bottler | Useful but visibility is inconsistent |

The current deterministic scorer uses normalization, RapidFuzz matching, and
source-backed rules. It is intentionally asymmetric:

```text
strong support     -> field supported
weak/missing OCR   -> Needs Review
clear contradiction -> Fail or Fail Candidate
```

---

## 7. Government-Safe Ensemble Policy

The current best pure OCR ensemble treats docTR, PaddleOCR, and OpenOCR as noisy
sensors. It combines their field-support scores with extra caution on high-risk
fields.

```mermaid
flowchart TD
    A["docTR field scores"] --> D["Government-safe ensemble"]
    B["PaddleOCR field scores"] --> D
    C["OpenOCR field scores"] --> D
    D --> E{"Field risk"}
    E -->|"Alcohol content"| F["Require unanimous / very strong support"]
    E -->|"Lower-risk text fields"| G["Allow majority or high-confidence support"]
    F --> H["Supported / Needs Review"]
    G --> H
```

Measured smoke result:

| Policy | F1 | False-Clear Rate | Decision |
|---|---:|---:|---|
| Naive any-engine support | 0.7459 | 0.0357 | Pruned as unsafe |
| Government-safe OCR ensemble | 0.7416 | 0.0000 | Best pure OCR smoke result |

The small F1 sacrifice is acceptable because it removes false clears in the
first shuffled-negative smoke.

---

## 8. Typography Preflight For Warning Boldness

Jenny Park's interview note creates a separate visual problem from OCR: the
government warning heading must be exactly `GOVERNMENT WARNING:` and must be
bold. OCR can tell us what the text says. It does not reliably prove font
weight on noisy raster label images.

The current deployed compliance posture is conservative:

```text
GOV_WARNING_EXACT_TEXT       -> deterministic text check
GOV_WARNING_HEADER_CAPS      -> deterministic capitalization check
GOV_WARNING_HEADER_BOLD_REVIEW -> human typography review
```

The next architecture adds a lightweight OpenCV typography preflight. The first
SVM experiment is implemented, but it stays outside the deployed runtime until
the corrected decision labels are inspected and a new model comparison is
validated strongly enough to support autonomous evidence.

```mermaid
flowchart TD
    A["OCR text + boxes"] --> B{"Can isolate<br/>GOVERNMENT WARNING:?"}
    B -->|No| C["Needs Review<br/>manual typography check"]
    B -->|Yes| D["Heading crop"]
    D --> E["OpenCV preprocessing<br/>grayscale, threshold,<br/>safe deskew/crop cleanup"]
    E --> F["Feature extraction<br/>ink density, edge density,<br/>stroke width, connected components,<br/>skeleton ratio, HOG"]
    F --> G["SVM / XGBoost / CatBoost<br/>CPU-only typography classifier"]
    G --> H{"Typography decision"}
    H -->|"Strong bold"| I["Typography preflight supported"]
    H -->|"Strong non-bold"| J["Needs Review / Fail Candidate<br/>depending validation gate"]
    H -->|"Borderline / degraded"| K["Needs Review"]
    I --> L["Deterministic compliance layer"]
    J --> L
    K --> L
```

Why this model family fits:

- The task is narrow: classify the visual stroke weight of one known phrase.
- The feature vector can capture the relevant geometry directly.
- CPU inference should be near-zero relative to OCR.
- A synthetic dataset can be generated without touching public-data OCR jobs.
- The decision threshold can be tuned for the primary safety metric:
  false clears.

The first dataset is synthetic because the negative cases are not public. It
renders `GOVERNMENT WARNING:` in bold, regular, medium, and degraded styles
across many local fonts and distortions.

Manual inspection found that the first binary SVM dataset mixed source font
weight, visual quality, and auto-clearance policy into one target. That was too
noisy: a degraded crop could be generated from a bold font but labeled negative,
and readable medium/semibold crops could be treated as review even though the
requirement is explicit bold type.

The corrected `audit-v4` dataset separates provenance from decision targets:

| Label | Meaning |
|---|---|
| `font_weight_label` | Source font provenance: `bold`, `not_bold`, `borderline`. |
| `header_text_label` | Source text provenance: `correct`, `incorrect`, `borderline`. |
| `quality_label` | Crop quality provenance: `clean`, `mild`, `degraded`. |
| `visual_font_decision_label` | Model 1 target: `clearly_bold`, `clearly_not_bold`, `needs_review_unclear`. |
| `header_decision_label` | Model 2 target: `correct`, `incorrect`, `needs_review_unclear`. |

Boundary and whitespace artifacts are intentionally routed to
`needs_review_unclear` for the image classifier. They remain useful deterministic
string/crop-boundary tests, but they should not be used as clean visible
`incorrect` header examples.

Implemented split:

```text
train:      20,000 crops
validation: 5,000 crops
test:       5,000 crops
```

The split should hold out font families and distortion recipes, not just random
rows. That makes the test stronger: it asks whether the classifier learned
boldness features rather than memorizing one font's rasterization.

Evaluation metrics:

| Metric | Meaning |
|---|---|
| Accuracy / F1 | General binary classifier quality |
| Specificity | Ability to reject non-bold/degraded headings |
| False-clear rate | Non-bold or uncertain headings incorrectly accepted as bold |
| Mean/p95 latency | Whether the crop classifier is negligible compared with OCR |

The planned classifier is justified as a classical statistical-learning model,
not a deep-learning shortcut. Hastie, Tibshirani, and Friedman describe
support vector machines as margin-based supervised learners; this is a good fit
when engineered stroke/shape features carry the decision boundary and compute
cost matters.

Initial measured result from the flawed binary baseline:

| Operating Point | Test F1 | Precision | Recall | False-Clear Rate | Interpretation |
|---|---:|---:|---:|---:|---|
| Zero validation false-clear tolerance | 0.0321 | 0.9737 | 0.0163 | 0.0004 | Safe but barely clears bold headings. |
| 0.25% validation false-clear tolerance | 0.1170 | 0.8987 | 0.0626 | 0.0059 | Still too weak for promotion. |
| 5% validation false-clear tolerance | 0.7757 | 0.8867 | 0.6894 | 0.0733 | Better F1, unsafe false-clear posture. |

Latency:

```text
mean SVM decision latency: about 0.09 ms/crop
```

Conclusion:

```text
The model class is computationally viable, but the first synthetic target was
too noisy to promote. It supports a measured path toward typography preflight
while confirming that boldness should remain Needs Review for the submission.
```

Reference:

```text
Hastie, Trevor; Tibshirani, Robert; Friedman, Jerome.
The Elements of Statistical Learning: Data Mining, Inference, and Prediction.
2nd ed., Springer, 2009.
```

Promotion gate:

```text
The typography preflight can become runtime evidence only if validation/test
false-clear behavior is safe. Until then, boldness remains Needs Review.
```

---

## 9. Domain-NER / BERT Arbiter Experiments

Post-OCR Transformer models are being tested as arbiters, not as OCR engines and
not as compliance decision makers.

```mermaid
flowchart LR
    A["Combined OCR text<br/>docTR + PaddleOCR + OpenOCR"] --> B["Domain-NER candidate"]
    B --> C["Entity evidence by field"]
    C --> D["Supplement lower-risk field support"]
    D --> E["Government-safe ensemble"]
    E --> F["Field support / Needs Review"]
```

Measured smoke results:

| Candidate | Entity-Only F1 | Hybrid F1 | False-Clear Rate | Decision |
|---|---:|---:|---:|---|
| WineBERT/o labels | 0.4865 | 0.7416 | 0.0000 | Not promoted; no lift, unknown license, wine-only coverage |
| WineBERT/o NER | 0.1176 | 0.7416 | 0.0000 | Not promoted |
| OSA market-domain NER | 0.5166 | 0.7486 | 0.0000 | Promising; needs 100-app calibration |
| FoodBaseBERT-NER | 0.0522 | 0.7416 | 0.0000 | Pruned; wrong semantic domain |

OSA is the current best BERT-assisted smoke result, but its lift was one extra
true positive across `224` field-support examples. That earns a larger
calibration run, not automatic deployment.

---

## 10. Trainable Field-Support Classifier

The next serious supervised model should be a field-support classifier, not a
token-level NER model.

Why:

- public COLA data gives application fields and accepted label images,
- it does not give gold token-level spans,
- field-support classification directly matches the product problem,
- it is easier to weak-label without pretending we have human span labels.

Training example shape:

```text
Input:
  field_name
  expected application value
  OCR candidate text or OCR evidence window
  optional engine scores/confidence/source

Output:
  supports_field = yes/no
```

Example positive:

```text
FIELD: alcohol_content
EXPECTED: 45% Alc./Vol. (90 Proof)
OCR TEXT: OLD TOM DISTILLERY ... 45% Alc./Vol. ... 750 mL
LABEL: supports
```

Example negative:

```text
FIELD: alcohol_content
EXPECTED: 13.5% Alc./Vol.
OCR TEXT: OLD TOM DISTILLERY ... 45% Alc./Vol. ... 750 mL
LABEL: does_not_support
```

Recommended training order:

```text
1. DistilRoBERTa field-support classifier
2. RoBERTa-base field-support classifier
3. DistilRoBERTa / RoBERTa + government-safe ensemble
```

```mermaid
flowchart TD
    A["Train split applications"] --> B["Generate positive field-support pairs"]
    A --> C["Generate shuffled / hard negative pairs"]
    B --> D["DistilRoBERTa classifier"]
    C --> D
    B --> E["RoBERTa-base classifier"]
    C --> E
    D --> F["Validation metrics + threshold tuning"]
    E --> F
    F --> G{"Beats baseline and preserves false-clear posture?"}
    G -->|No| H["Keep deterministic ensemble as runtime"]
    G -->|Yes| I["Evaluate once on locked test"]
    I --> J{"Still safe on locked test?"}
    J -->|No| H
    J -->|Yes| K["Promote behind feature flag / adapter"]
```

The classifier is allowed to improve recall only if it does not create an
unacceptable false-clear rate. For this project, the false-clear metric is more
important than headline F1.

---

## 11. Metrics And Gates

Primary safety metric:

| Metric | Meaning |
|---|---|
| False-clear rate | Known bad or shuffled-negative examples incorrectly treated as supported/pass |

Secondary metrics:

| Metric | Meaning |
|---|---|
| Field-support F1 | Balance of support precision and recall |
| Recall | How often true field evidence is found |
| Precision | How often supported fields are actually supported |
| Reviewer-escalation rate | How much uncertainty routes to Needs Review |
| Application-level pass/review/fail distribution | How the full triage behaves |
| Per-application latency | Whether it stays near stakeholder tolerance |

Promotion gate:

```text
candidate model can be promoted only if:
  validation F1 improves over baseline
  validation false-clear rate is acceptable
  locked-test false-clear rate remains acceptable after freeze
  CPU latency fits the deployment target
  runtime has a rollback path
```

---

## 12. Final Runtime Recommendation

For the take-home submission, the safest runtime posture is:

```text
Deployed app:
  docTR or fixture OCR
  deterministic field matching
  source-backed rules
  conservative Needs Review fallback

Experimental evidence:
  PaddleOCR/OpenOCR/ensemble/BERT results documented
  OSA and field-support classifier path ready for calibration
```

Do not merge a trained RoBERTa or DistilRoBERTa model into the public runtime
unless it clears the validation and locked-test gates. A measured, conservative
system is stronger than an impressive model that overfits or false-clears
problematic labels.

---

## 13. Future Architecture

If time and data permit after the current sprint:

```mermaid
flowchart TD
    A["All application label panels"] --> B["Parallel local OCR sensors<br/>docTR / PaddleOCR / OpenOCR"]
    B --> C["Box/text normalization"]
    C --> D["Field-support classifier<br/>DistilRoBERTa or RoBERTa"]
    D --> E["Graph-aware evidence scorer"]
    E --> F["Deterministic compliance rules"]
    F --> G["Local LLM explanation draft<br/>explain only, never decide"]
    G --> H["Reviewer-facing evidence packet"]
```

A custom HO-GNN/TPS/SVTR curved-text vision model remains a future research
path. It should only be pursued if mature OCR engines and post-OCR arbitration
plateau because OCR fails to detect text in the first place.
