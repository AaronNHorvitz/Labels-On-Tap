# PRD.md — Labels On Tap

## Product Requirements Document

**Product:** Labels On Tap
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Deployment URL:** `https://www.labelsontap.ai`
**Document status:** Draft v1 for build planning
**Primary deliverable:** Working deployed prototype with source code, README, setup/run instructions, documented assumptions, and trade-offs

---

## 1. Executive Summary

Labels On Tap is a local-first, source-backed alcohol label preflight prototype for TTB-style Certificate of Label Approval (COLA) review. The application compares uploaded alcohol label artwork against expected application fields modeled after TTB Form 5100.31 / COLAs Online workflows. It uses local OCR, deterministic rule checks, fuzzy matching, image preflight checks, and risk-based human-review triggers to return clear **Pass**, **Needs Review**, or **Fail** results.

The product is designed around a specific stakeholder problem: TTB compliance agents spend significant time manually verifying routine label/application matches, including brand name, alcohol content, net contents, class/type, and government warning text. The prototype should reduce repetitive visual checking without replacing human judgment or making final legal determinations.

The build intentionally avoids hosted ML APIs, cloud OCR, and large vision-language models. Runtime verification must run locally or self-hosted because stakeholder discovery identified federal firewall constraints and prior vendor failure modes involving blocked outbound ML endpoints. The prototype must also feel usable by non-technical reviewers: obvious upload flow, live batch progress, plain-language results, and source-backed explanations.

### Latest Model-Selection Evidence

The current typography model-selection comparison uses one controlled dataset
and split: `audit-v6`, `6,000` train / `1,500` validation / `1,500` untouched
test crops. Base learners use five-fold out-of-fold train predictions, and
ensembles are trained on probabilities from all base learners, including
MobileNetV3 CNN.

| Type | Model / Policy | Test F1 | Test false-clear |
|---|---|---:|---:|
| Base model | MobileNetV3 CNN | 0.9686 | 0.0055 |
| Ensemble | Logistic stacker + CNN | 0.9908 | 0.0099 |
| Ensemble | LightGBM reject + CNN | 0.9552 | 0.0033 |
| Ensemble | XGBoost reject + CNN | 0.9656 | 0.0044 |

Product decision: deploy the conservative JSON logistic typography preflight
for the MVP, and keep CNN-inclusive reject ensembles as measured promotion
candidates because they better respect the false-clear posture.

---

## 2. Problem Statement

TTB label review involves a large volume of repetitive matching work. A reviewer must inspect a COLA application, inspect the submitted label artwork, and confirm that required information appears correctly on the label. Many checks are routine but time-consuming: brand name, alcohol content, net contents, class/type, warning statement, and other mandatory or conditional disclosures.

The current manual process creates three product problems:

1. **Routine verification consumes reviewer capacity.** Agents are spending time on mechanical comparisons instead of higher-value regulatory analysis.
2. **Slow automation is worse than no automation.** A previous scanning pilot reportedly took 30–40 seconds per label, causing agents to abandon it and return to manual review.
3. **Batch workflows are poorly supported.** Peak-season importers can submit hundreds of labels, but reviewers still process applications one at a time.

Labels On Tap solves the narrow version of this problem: it provides a fast, local, auditable preflight tool that helps agents triage labels and identify obvious matches, deterministic failures, and ambiguous cases requiring human review. A production workflow should also let the agency choose whether candidate acceptances, candidate rejections, or both require reviewer approval before final action.

---

## 3. Product Positioning

### 3.1 What the Product Is

Labels On Tap is a **source-backed reviewer-support and preflight system**. It helps a reviewer answer:

- Does the label artwork appear to match the application fields?
- Is the government warning present and exact?
- Are obvious alcohol-content, net-contents, class/type, or image-upload issues present?
- Are there risk signals that should be routed to human review?
- Which source-backed criterion caused each result?

### 3.2 What the Product Is Not

Labels On Tap is **not**:

- A final TTB approval or rejection system.
- A replacement for human label specialists.
- A direct COLAs Online integration.
- A cloud OCR or hosted ML application.
- A legal-advice system.
- A complete implementation of every possible beverage-alcohol regulation.
- A system for scraping private, pending, rejected, or Needs Correction applications.

The correct product language is:

> Labels On Tap provides source-backed preflight results and human-review escalation. It does not issue final legal determinations.

---

## 4. Goals and Success Criteria

### 4.1 Product Goals

| Goal | Description | Priority |
|---|---|---:|
| Deployed working app | Publicly accessible prototype at `https://www.labelsontap.ai`. | P0 |
| Local-first OCR | Runtime OCR and validation run without hosted ML endpoints. | P0 |
| Fast single-label feedback | Target approximately 5 seconds per label after OCR model warmup, dependent on image complexity and VM resources. | P0 |
| Batch support | Accept and process large label batches asynchronously with immediate progress feedback. | P0 |
| Simple reviewer UX | Provide a clear, accessible workflow for older/non-technical reviewers. | P0 |
| Source-backed results | Every major rule result links to a source-backed criterion and plain-language rationale. | P0 |
| Dual-standard validation | Apply fuzzy matching for reviewer-judgment fields and strict checks for deterministic compliance fields. | P0 |
| Safe uncertainty handling | Route low-confidence OCR, brittle visual checks, and subjective legal risks to Needs Review. | P0 |
| Human review policy | Support agency-configurable approval gates before final acceptance and/or rejection. | P1 |
| Photo OCR intake demo | Let evaluators upload a real bottle/can/shelf photo and inspect extracted candidate fields without claiming COLA verification. | P1 |
| Research corpus | Maintain a legal/regulatory research corpus that maps sources to rules, fixtures, and UI explanations. | P1 |
| Synthetic fixture generation | Generate controlled negative examples because true rejected/Needs Correction data is not generally public. | P1 |

### 4.2 Success Metrics

| Metric | Target |
|---|---|
| Live app availability | `www.labelsontap.ai` loads and supports demo workflow. |
| Single-label result latency | Approximately 5 seconds after OCR warmup on target VM for demo fixtures. |
| Batch responsiveness | Job page renders immediately and updates progress every few seconds. |
| Batch size | Designed for 200+ images; sprint validation should demonstrate at least one large synthetic batch. |
| Source traceability | Each implemented rule has source refs, verdict policy, and fixture mapping. |
| Reviewer clarity | Result table shows status, top reason, evidence, and reviewer action. |
| False certainty avoidance | Low-confidence OCR and brittle image conditions return Needs Review, not unsupported Pass. |

---

## 5. Stakeholders and Personas

### 5.1 Sarah Chen — Deputy Director of Label Compliance

**Need:** Faster routine matching and batch triage.
**Pain:** Agents are overloaded with repetitive visual checks; prior automation was too slow.
**Product implication:** The app must return fast per-label feedback, support batch uploads, and avoid complex UI.

### 5.2 Marcus Williams — IT Systems Administrator

**Need:** Standalone, local-first prototype that does not rely on blocked cloud ML endpoints.
**Pain:** Hosted ML features failed behind federal firewall constraints; direct COLA integration is out of scope.
**Product implication:** No OpenAI, Anthropic, Google Cloud Vision, Azure AI Vision, AWS Textract, or hosted VLM runtime. The prototype must be deployable as a standalone app.

### 5.3 Dave Morrison — Senior Compliance Agent

**Need:** Review nuance.
**Pain:** Not every text difference is a real mismatch; a tool that fails harmless typographic differences will make the job harder.
**Product implication:** Use fuzzy matching for fields such as brand name, fanciful name, class/type, and addresses. Route ambiguous results to Needs Review.

### 5.4 Jenny Park — Junior Compliance Agent

**Need:** Exact checks for routine checklist items, especially the government warning.
**Pain:** Warning text and formatting are easy to miss manually, and applicants often alter wording, capitalization, size, or placement.
**Product implication:** Government warning must be checked strictly for wording and capitalization; visual formatting such as boldness and legibility should be checked with best-effort CV heuristics and Needs Review fallbacks.

The reviewer-policy control board should also support a warning-specific gate:
unknown or unverifiable government-warning evidence can be sent to human review
when the reviewer enables that setting. The default is no human review for this
case; without that explicit review gate, an unknown government warning defaults
to failure because the warning is mandatory and the applicant must provide
readable label evidence.

### 5.5 Evaluator / Hiring Panel

**Need:** Quickly evaluate whether the prototype works, why the technical choices were made, and how the candidate handled trade-offs.
**Product implication:** The app must ship with a five-minute demo path, README, PRD, architecture docs, validation docs, trade-offs, and clean repository organization.

---

## 6. User Experience Requirements

### 6.1 Core Workflow

```text
Upload Labels
  → Run Local Verification
  → Review Pass / Needs Review / Fail Results
  → Inspect Evidence and Source-Backed Reasons
  → Export CSV
```

### 6.2 UX Principles

- Large buttons.
- Plain-language labels.
- High-contrast status badges.
- No hidden controls.
- No unnecessary navigation.
- Immediate feedback after upload.
- Live batch progress.
- Results visible as soon as each label finishes.
- Evidence shown next to the rule that triggered.
- Clear difference between Fail and Needs Review.
- Clear difference between raw system verdicts and final reviewer/agency actions.
- Batch queues that can require reviewer approval before acceptance, rejection, or both.

### 6.3 Result States

| State | Meaning | Product Behavior |
|---|---|---|
| Pass | The label appears consistent with source-backed checks and OCR confidence is sufficient. | Show green status and completed checks. |
| Needs Review | The system found ambiguity, low OCR confidence, subjective legal risk, or brittle visual conditions. | Show yellow status, evidence, source, and reviewer action. |
| Fail | A deterministic, source-backed rule clearly failed with adequate evidence. | Show red status, expected vs observed text/value, and source-backed explanation. |

### 6.4 Review Policy Modes

Raw verdicts should be separated from final agency action. The recommended
policy controls are:

```text
Require reviewer approval before rejection: Yes / No
Require reviewer approval before acceptance: Yes / No
```

Default posture:

```text
Unknown government warning human review: No
Before rejection: No
Before acceptance: No
```

Policy routing:

| Raw system result | Warning unknown review enabled | Rejection review required | Acceptance review required | Queue |
|---|---|---|---|---|
| Pass | n/a | n/a | No | Ready to accept |
| Pass | n/a | n/a | Yes | Acceptance review |
| Fail | n/a | No | n/a | Ready to reject |
| Fail | n/a | Yes | n/a | Rejection review |
| Government warning unknown | No | No | n/a | Ready to reject |
| Government warning unknown | No | Yes | n/a | Rejection review |
| Government warning unknown | Yes | any | n/a | Manual evidence review |
| Needs Review | n/a | any | any | Manual evidence review |

Reviewer actions:

```text
Accept
Reject
Request correction / better image
Override with note
Escalate
```

This policy layer is especially important for large importer batches. The tool
should produce queue counts such as `Ready to accept`, `Acceptance review`,
`Rejection review`, and `Manual evidence review` so agents can process 200-300
applications without losing final judgment.

---

## 7. MVP Scope

### 7.1 P0 Features

#### P0.1 Public deployed app

- App available at `https://www.labelsontap.ai`.
- Dockerized deployment on an x86_64 Linux VM.
- HTTPS enabled through Caddy or equivalent reverse proxy.
- No hosted ML endpoints required for runtime validation.

#### P0.2 Single-label upload

Reviewer can upload one label image and provide expected application fields.

Minimum fields:

- Product type: wine, distilled spirits, malt beverage.
- Brand name.
- Class/type.
- Alcohol content.
- Net contents.
- Optional formula ID.
- Optional statement of composition.
- Optional appellation/country/origin fields.
- Label image.

#### P0.3 Batch upload

Reviewer can upload:

- `manifest.csv` or `manifest.json`.
- Multiple label images.
- ZIP intake is intentionally out of scope for the MVP unless safe archive handling is added later.

The job page must show:

- Total items.
- Processed count.
- Pass count.
- Needs Review count.
- Fail count.
- Completed rows as they finish.

#### P0.4 Local OCR and topology extraction

The app must extract:

- Full OCR text.
- Text blocks.
- Bounding boxes or polygons where supported.
- Confidence scores.
- Timing metrics.

OCR engine selection should be benchmark-driven. The runtime engine must satisfy:

- CPU-only local inference.
- Docker reliability.
- Bounding-box output.
- Confidence score output.

#### P1.0 Photo OCR intake demo

The app should support a demonstration-only flow for real-world phone photos:

- Upload one bottle, can, or store-shelf label image.
- Run the same upload preflight and local OCR path.
- Display likely candidate fields: brand, product type, class/type, alcohol content, net contents, country of origin, and government warning signals.
- Display OCR source, confidence, OCR lines, and raw OCR text.
- Clearly state that the result is an extraction aid, not a verification verdict, because no application fields were supplied.
- Good enough performance for the approximate 5-second per-label target.

#### P0.5 Image and upload preflight

The app must check upload safety and label-image quality before relying on OCR.

Minimum checks:

- Allowed extensions: `.jpg`, `.jpeg`, `.png` for label artwork.
- Reject PDFs as label artwork.
- File signature / magic-byte validation.
- Double-extension rejection.
- Path traversal protection.
- File-size limits.
- ZIP safety checks if ZIP upload is implemented.
- OCR confidence warnings.
- Blur / low-quality image warning.
- Large whitespace or obvious non-label background warning where feasible.

#### P0.6 Fuzzy application-to-label matching

Use fuzzy matching for:

- Brand name.
- Fanciful name.
- Class/type.
- Producer/bottler name.
- Address.

Minor differences in capitalization, spacing, apostrophes, and punctuation should not cause automatic failure.

#### P0.7 Strict government warning validation

The app must check:

- Warning present.
- Canonical warning text match after whitespace normalization only.
- `GOVERNMENT WARNING:` all caps.
- Heading boldness, best effort.
- Body not bold, best effort.
- Legibility / contrast / OCR confidence.

Canonical text:

```text
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
```

#### P0.8 Alcohol content checks

The app must check:

- Application alcohol value vs label alcohol value.
- Proof equivalence where relevant for distilled spirits.
- Prohibited or risky abbreviation usage such as `ABV` / `A.B.V.` and `ABW` / `A.B.W.` where source-backed.
- Low OCR confidence around alcohol statement.

#### P0.9 Net contents checks

The app must check source-backed, demoable failures, especially malt beverage intermediate-volume issues:

- `16 fl. oz.` where `1 pint` is expected.
- `22 fl. oz.` where `1 pint 6 fl. oz.` is expected.
- `oz.` without `fl.` where fluid-ounce designation is required.
- Metric-only risk where U.S. measure is required.

#### P0.10 Source-backed result explanations

Every triggered check must include:

- Rule ID.
- Verdict.
- Evidence found.
- Expected value or source-backed requirement.
- Plain-language rationale.
- Reviewer action.
- Source IDs from the legal corpus.

#### P0.11 CSV export

Batch results must be exportable as CSV with at least:

- Filename.
- Overall verdict.
- Top reason.
- Triggered rule IDs.
- Evidence text.
- OCR confidence.
- Processing time.

---

### 7.2 P1 Features

#### P1.1 Legal corpus and source ledger

Create a structured legal corpus:

```text
research/legal-corpus/
  source-ledger.json
  source-ledger.md
  source-confidence.md
  federal-statutes.md
  cfr-regulations.md
  ttb-guidance-and-circulars.md
  court-cases-and-precedents.md
  public-data-boundaries.md
  forms/
  excerpts/
  matrices/
  reports/
```

Every implemented rule should trace to:

```text
Source → Extracted Requirement → Rule Matrix Row → App Rule → Fixture/Test → UI Explanation
```

#### P1.2 Source-backed criteria matrix

Create:

```text
research/legal-corpus/matrices/source-backed-criteria.json
research/legal-corpus/matrices/source-backed-criteria.md
research/legal-corpus/matrices/source-backed-criteria.csv
```

Each criterion should define:

- Rule ID.
- Beverage types.
- Category.
- Source refs.
- Requirement summary.
- Detection method.
- Pass condition.
- Fail condition.
- Needs Review condition.
- App module.
- Fixtures.
- UI message.

#### P1.3 Synthetic fixture generation

Create controlled negative fixtures for rules where public rejected/Needs Correction data is unavailable.

Fixture classes:

- Government warning defects.
- Alcohol term defects.
- Net contents defects.
- Image preflight defects.
- Low-confidence OCR defects.
- Risk-review phrases.
- Semi-generic/absinthe/geographic examples where appropriate.

#### P1.4 Risk-based Needs Review rules

Add lightweight risk heuristics for:

- Health-claim language.
- Statement-of-composition anomalies.
- Formula-trigger language.
- Multiple geographic/AVA terms.
- Semi-generic wine names.
- Absinthe/thujone references.
- Distilled-spirits class/type conflicts.

These should generally return **Needs Review**, not Fail, unless the rule is deterministic and supported by current official authority.

#### P1.5 OCR benchmark harness

Add a benchmark script and documentation for local OCR candidates.

Metrics:

- Engine.
- Image name.
- OCR time.
- Total time.
- OCR confidence.
- Bounding-box availability.
- Warning detected.
- Brand detected.
- Alcohol detected.
- Net contents detected.
- Docker reliability notes.

---

### 7.3 P2 / Future Features

- Direct COLAs Online integration.
- Authentication / SSO / RBAC.
- Production audit logging.
- Formal records retention.
- PostgreSQL / enterprise database.
- Full legal-grade AVA geospatial validation.
- Full formula-document parsing.
- Chemical/lab validation for thujone or ingredients.
- Full font-size measurement from physical bottle geometry.
- Custom OCR training.
- Large-scale registry ingestion.
- Registry scraping or TTB ID enumeration.
- VLM-based semantic review.
- Mobile bottle-photo workflow.

---

## 8. Functional Requirements

### 8.1 Upload and Job Creation

| ID | Requirement | Priority |
|---|---|---:|
| FR-001 | User can upload one label image and expected fields. | P0 |
| FR-002 | User can upload batch manifest plus images. | P0 |
| FR-003 | User can upload ZIP only if extraction is safe and limited. | P1 |
| FR-004 | App validates file type before OCR. | P0 |
| FR-005 | App creates a job ID and redirects immediately to progress page. | P0 |
| FR-006 | App stores uploaded files under randomized safe paths. | P0 |
| FR-007 | App rejects unsafe or unsupported files with clear explanation. | P0 |
| FR-008 | App supports demonstration-only photo OCR intake for one free-form label photo. | P1 |
| FR-009 | App supports a local public COLA example demo that compares application fields against OCR evidence from all associated label panels. | P1 |

### 8.2 OCR and Topology

| ID | Requirement | Priority |
|---|---|---:|
| FR-010 | App runs OCR locally without hosted ML. | P0 |
| FR-011 | OCR returns text, confidence, and bounding boxes where supported. | P0 |
| FR-012 | App records processing timing metrics. | P0 |
| FR-013 | App creates a label topology object from OCR blocks. | P1 |
| FR-014 | App creates evidence snippets/crops for key failures where feasible. | P1 |
| FR-015 | App extracts candidate fields from free-form photo OCR text for demonstration only. | P1 |
| FR-016 | For public example applications, app pools OCR evidence across every associated front/back/neck/side label panel before scoring field support. | P1 |

### 8.3 Validation

| ID | Requirement | Priority |
|---|---|---:|
| FR-020 | App performs fuzzy matching for brand/name/class fields. | P0 |
| FR-021 | App performs strict government warning text check. | P0 |
| FR-022 | App checks government warning capitalization. | P0 |
| FR-023 | App performs best-effort warning boldness/body-bold checks. | P0 |
| FR-024 | App checks alcohol value and terminology. | P0 |
| FR-025 | App checks net contents and malt beverage conversion issues. | P0 |
| FR-026 | App performs image quality checks and routes uncertainty to Needs Review. | P0 |
| FR-027 | App performs source-backed risk-review scans. | P1 |
| FR-028 | App includes source-backed explanation for each triggered rule. | P0 |

### 8.4 Batch Processing

| ID | Requirement | Priority |
|---|---|---:|
| FR-030 | App processes batch labels asynchronously or in a non-blocking worker path. | P0 |
| FR-031 | App displays live progress. | P0 |
| FR-032 | App displays completed rows incrementally. | P0 |
| FR-033 | App handles individual failures without failing the full batch. | P0 |
| FR-034 | App exports batch results as CSV. | P0 |
| FR-035 | App supports policy toggles for reviewer approval before rejection, before acceptance, and for unknown government-warning evidence. | P1 |
| FR-036 | App maps raw verdicts into reviewer queues such as Ready to accept, Acceptance review, Rejection review, Manual evidence review, and Ready to reject. | P1 |
| FR-037 | App records reviewer actions with decision, note, timestamp, and original evidence reference. | P1 |

### 8.5 Documentation and Research

| ID | Requirement | Priority |
|---|---|---:|
| FR-040 | Repo contains PRD.md. | P0 |
| FR-041 | Repo contains README.md with setup/run/deployment instructions. | P0 |
| FR-042 | Repo contains ARCHITECTURE.md. | P0 |
| FR-043 | Repo contains TRADEOFFS.md. | P0 |
| FR-044 | Repo contains research/legal-corpus source ledger and rule matrix. | P1 |
| FR-045 | Repo contains fixture provenance mapping. | P1 |
| FR-046 | Repo contains demo script. | P0 |

---

## 9. Nonfunctional Requirements

### 9.1 Performance

| ID | Requirement | Priority |
|---|---|---:|
| NFR-001 | Single-label processing should target approximately 5 seconds after OCR warmup for demo fixtures. | P0 |
| NFR-002 | The UI must show immediate feedback after batch upload. | P0 |
| NFR-003 | Full batch completion time may exceed 5 seconds; UI must make progress visible. | P0 |
| NFR-004 | OCR benchmark results should document p50/p95 runtime where possible. | P1 |

### 9.2 Local-First Runtime

| ID | Requirement | Priority |
|---|---|---:|
| NFR-010 | Runtime must not call hosted OCR or ML endpoints. | P0 |
| NFR-011 | Runtime must not depend on OpenAI, Anthropic, Google Cloud Vision, Azure AI Vision, AWS Textract, or hosted VLMs. | P0 |
| NFR-012 | OCR model files should be local to the deployment container or mounted volume. | P0 |

### 9.3 Security and Privacy

| ID | Requirement | Priority |
|---|---|---:|
| NFR-020 | Validate extension and file signature. | P0 |
| NFR-021 | Rename files to generated safe names. | P0 |
| NFR-022 | Enforce upload size limits. | P0 |
| NFR-023 | Prevent path traversal and double-extension attacks. | P0 |
| NFR-024 | If ZIP support exists, enforce safe extraction, maximum file count, and maximum uncompressed size. | P1 |
| NFR-025 | Do not store sensitive data long-term. | P0 |
| NFR-026 | Document prototype security limitations. | P0 |

### 9.4 Accessibility

| ID | Requirement | Priority |
|---|---|---:|
| NFR-030 | Use high-contrast status indicators with text labels, not color alone. | P0 |
| NFR-031 | Ensure form controls are keyboard accessible. | P0 |
| NFR-032 | Use plain language and visible error messages. | P0 |
| NFR-033 | Provide progress text for batch status. | P0 |

### 9.5 Reliability

| ID | Requirement | Priority |
|---|---|---:|
| NFR-040 | A failed image must not crash the batch. | P0 |
| NFR-041 | OCR timeout or engine failure should return Needs Review / Error status, not hang the UI. | P0 |
| NFR-042 | Job results should be written atomically. | P0 |
| NFR-043 | App should include `/health` endpoint. | P0 |

---

## 10. Data and Fixture Strategy

### 10.1 Data Principles

The project must not depend on confidential rejected or Needs Correction application records. Public data strategy should be lawful, reproducible, and transparent.

Use:

1. Public approved COLA labels as realistic positive examples.
2. Public surrendered/revoked records only as post-market anomaly context.
3. Synthetic negative fixtures for deterministic failure testing.
4. Public legal/guidance/case-study materials for rule inspiration.
5. Small, curated fixtures in repo.

Do not use:

- Private COLAs Online data.
- Bulk scraped hidden application data.
- Confidential rejection notices.
- Credentials or API keys.
- Large uncurated scraped datasets.

### 10.2 Fixture Provenance

Each fixture must map to:

- Fixture ID.
- File path.
- Source type.
- Base source if applicable.
- Rule IDs.
- Source refs.
- Expected verdict.
- Mutation summary.

Example:

```yaml
fixture_id: warning_missing_machinery_comma
file_path: data/fixtures/synthetic/warning_missing_machinery_comma.png
source_type: synthetic_mutation
rule_ids:
  - GOV_WARNING_EXACT_TEXT
source_refs:
  - SRC_27_CFR_PART_16
expected_verdict: fail
mutation_summary: Removed required comma after 'machinery' in the warning text.
```

---

## 11. Legal and Regulatory Corpus Requirements

The repo should include a structured legal corpus:

```text
research/legal-corpus/
  README.md
  source-ledger.json
  source-ledger.md
  source-confidence.md
  federal-statutes.md
  cfr-regulations.md
  ttb-guidance-and-circulars.md
  court-cases-and-precedents.md
  public-data-boundaries.md
  forms/
  excerpts/
  matrices/
  reports/
```

### 11.1 Source Confidence Policy

| Tier | Sources | Rule Behavior |
|---|---|---|
| Tier 1 | U.S. Code, CFR/eCFR, TTB.gov, TTB forms, TTB circulars, federal court opinions | Deterministic rules may Fail/Pass; subjective issues route to Needs Review. |
| Tier 2 | Law firm summaries, compliance providers, public legal analysis, public case studies | Needs Review unless confirmed by Tier 1 deterministic source. |
| Tier 3 | OSINT, forums, research synthesis, synthetic mutations | Needs Review or fixture inspiration only. |

### 11.2 Key Regulatory Source Categories

The corpus should include, at minimum:

- FAA Act authority: 27 U.S.C. § 205.
- Alcoholic Beverage Labeling Act / health warning authority: 27 U.S.C. § 215.
- 27 CFR Part 4 — Wine.
- 27 CFR Part 5 — Distilled Spirits.
- 27 CFR Part 7 — Malt Beverages.
- 27 CFR Part 13 — Labeling Proceedings and public-data boundaries.
- 27 CFR Part 16 — Government Health Warning.
- TTB Form 5100.31.
- TTB Public COLA Registry guidance.
- COLAs Online image upload guidance.
- TTB Industry Circular 2006-01 — semi-generic wine names / Retsina.
- TTB Industry Circular 2007-05 — absinthe / thujone.
- Relevant case studies and court rulings, especially health-claim and geographic-origin examples.

---

## 12. Source-Backed Rule Categories

### 12.1 Strict Deterministic Rules

Strict rules can produce Fail when OCR confidence and evidence are adequate.

Examples:

- `GOV_WARNING_EXACT_TEXT`
- `GOV_WARNING_HEADER_CAPS`
- `ALCOHOL_ABV_PROHIBITED`
- `ALCOHOL_ABW_PROHIBITED`
- `MALT_NET_CONTENTS_16OZ_PINT`
- `MALT_NET_CONTENTS_22OZ_PINT_6OZ`
- `MALT_OZ_MISSING_FL`
- `IMAGE_FORMAT_ALLOWED_TYPES`

### 12.2 Fuzzy Matching Rules

Fuzzy rules compare application fields to OCR text while tolerating harmless presentation differences.

Examples:

- `FORM_BRAND_MATCHES_LABEL`
- `FORM_FANCIFUL_NAME_MATCHES_LABEL`
- `FORM_CLASS_TYPE_MATCHES_LABEL`
- `FORM_NAME_ADDRESS_MATCHES_LABEL`

### 12.3 Numeric and Unit Normalization Rules

Numeric rules parse values and compare normalized quantities.

Examples:

- `ALCOHOL_VALUE_MATCH`
- `PROOF_EQUIVALENCE`
- `NET_CONTENTS_MATCH`
- `ALCOHOL_TOLERANCE_BY_COMMODITY`

### 12.4 Image Quality and Topology Rules

Image/CV rules protect against false certainty.

Examples:

- `OCR_CONFIDENCE_LOW`
- `WARNING_CONTRAST_LEGIBILITY`
- `WARNING_HEADER_BOLD`
- `IMAGE_BLUR_LOW_CONFIDENCE`
- `IMAGE_EXCESS_WHITE_SPACE`
- `WARNING_TYPE_SIZE_ESTIMATE`

### 12.5 Risk Review Rules

Risk rules usually return Needs Review because they involve subjective, contextual, or precedent-driven analysis.

Examples:

- `HEALTH_CLAIM_EXPLICIT`
- `HEALTH_CLAIM_IMPLICIT`
- `SOC_PROPRIETARY_ACRONYM_NEAR_COMPOSITION`
- `GEOGRAPHIC_MULTI_AVA_RISK`
- `WINE_SEMI_GENERIC_NAME_DETECTED`
- `ABSINTHE_TERM_DETECTED`
- `SPIRITS_FORMULA_REQUIRED_RISK`
- `SPIRITS_STANDARD_IDENTITY_CONFLICT`

---

## 13. Application Schema Requirements

The manifest should support simple demo mode and expanded Form 5100.31 mode.

### 13.1 Simple Demo Mode

```json
{
  "filename": "sample_label.png",
  "product_type": "malt_beverage",
  "brand_name": "Old Tom Brewing",
  "class_type": "India Pale Ale",
  "alcohol_content": "5.0% ALC/VOL",
  "net_contents": "1 Pint",
  "formula_id": null
}
```

### 13.2 Expanded Form Mode

```json
{
  "application_id": null,
  "representative_id": null,
  "serial_number": "26-01",
  "plant_registry_or_basic_permit": null,
  "source_of_product": "domestic",
  "product_type": "distilled_spirits",
  "type_of_application": "standard_cola",
  "brand_name": "Example Spirits",
  "fanciful_name": null,
  "class_type": "Straight Bourbon Whiskey",
  "formula_id": null,
  "statement_of_composition": null,
  "grape_varietals": [],
  "appellation_of_origin": null,
  "translations": null,
  "embossed_or_blow_in_information": null,
  "label_width_inches": null,
  "label_height_inches": null,
  "container_volume": "750 mL",
  "alcohol_content": "45% ALC/VOL",
  "net_contents": "750 mL",
  "country_of_origin": null,
  "imported": false
}
```

---

## 14. Technical Architecture Requirements

The PRD does not lock the final architecture to one OCR library, but it does impose runtime requirements.

### 14.1 Required Architecture Properties

- FastAPI or equivalent Python web service.
- Server-rendered reviewer UI using Jinja/HTMX or similarly simple approach.
- Local OCR adapter layer.
- Deterministic validation engine.
- Source-backed criteria registry.
- Filesystem-first or otherwise sprint-safe result persistence.
- Dockerized deployment.
- Public URL with HTTPS.

### 14.2 OCR Selection Policy

OCR engine selection must be benchmark-driven.

Candidate engines:

- docTR.
- Tesseract.
- PaddleOCR.
- EasyOCR.

Excluded from runtime MVP:

- Hosted OCR APIs.
- Hosted VLMs.
- Heavy local VLMs.
- GPU-dependent models.

Selection criteria:

- Local CPU latency.
- Docker reliability.
- Memory footprint.
- Bounding-box output.
- Confidence scores.
- Warning-text recall.
- Evidence crop support.

---

## 15. Security Requirements

Because `labelsontap.ai` is public, upload safety is part of the product, not an implementation detail.

Minimum upload controls:

- Extension allowlist.
- Magic-byte validation.
- MIME type treated as untrusted.
- Randomized server-side filenames.
- Maximum file size.
- Maximum batch size.
- ZIP bomb protection if ZIP support exists.
- Path traversal prevention.
- No execution permissions in upload directories.
- Cleanup of old jobs.
- No long-term sensitive storage.

The app should document that production federal deployment would require additional controls, including authentication, authorization, audit logging, retention policy, and formal security review.

---

## 16. Acceptance Criteria

### 16.1 Core App Acceptance

The submission is acceptable if:

- `https://www.labelsontap.ai` loads.
- User can upload a single label and expected fields.
- User receives Pass / Needs Review / Fail result.
- Result includes evidence and source-backed reason.
- User can upload a batch manifest and multiple images.
- Batch page shows live progress.
- CSV export works.
- App does not call hosted ML endpoints.
- README explains setup/run/deployment.
- Trade-offs are documented.

### 16.2 Demo Acceptance

The demo should include fixtures showing:

| Fixture | Expected Result |
|---|---|
| Clean label | Pass |
| Brand casing difference | Pass |
| Bad government warning text | Fail |
| Title-case Government Warning | Fail |
| ABV abbreviation | Fail |
| 16 fl. oz. malt beverage | Fail |
| Blurry/low-confidence warning | Needs Review |
| Health/geographic/circular risk | Needs Review |
| Batch of multiple labels | Live progress + export |

### 16.3 Legal Corpus Acceptance

The research/legal corpus is acceptable if:

- Every implemented rule has at least one source ref.
- Every source ref exists in the source ledger.
- Every non-info rule has at least one fixture or an explicit fixture-pending note.
- Tier 2/Tier 3 rules default to Needs Review, not Fail.
- Public data boundaries are documented.

---

## 17. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| OCR dependency/deployment failure | App cannot process labels live. | Dockerize and benchmark OCR early; keep pluggable OCR adapter. |
| OCR latency exceeds target | Users abandon app. | Resize images, preload model, benchmark engines, show progress immediately. |
| Overbuilt research corpus delays app | Missing deployed deliverable. | Build core app first; corpus supports rules and docs. |
| Bold detection brittle | False failures or passes. | Use best-effort CV; route uncertainty to Needs Review. |
| SQLite/database locks | Batch failures. | Prefer filesystem-first atomic JSON result files for MVP. |
| Public upload abuse | Security risk. | Implement upload allowlist, signature validation, limits, safe filenames, cleanup. |
| Legal overclaiming | Credibility risk. | Position as preflight and reviewer support, not final agency action. |
| Automated adverse action without review | Applicant fairness and reviewer trust risk. | Add policy toggle requiring reviewer approval before rejection; default to Yes. |
| Over-reviewing clean applications | Efficiency gain may shrink. | Make acceptance review optional; default to No for routine-pass triage. |
| Data provenance concerns | Ethical/legal risk. | Use public approved data, post-market public context, and synthetic negative fixtures only. |

---

## 18. Out of Scope for MVP

- Direct COLAs Online integration.
- Authenticated TTB system access.
- Registry scraping or TTB ID enumeration.
- Production SSO/RBAC.
- Full federal retention and audit compliance.
- Final legal determination.
- Full formula-document parsing.
- Full AVA GIS validation.
- Full physical font-size certainty without reliable dimensions/DPI.
- Chemical lab validation.
- Large VLM reasoning.
- PDF parsing for label artwork.

---

## 19. README Implications

This PRD should drive the README structure.

The README should include:

1. What Labels On Tap is.
2. Live deployment URL.
3. Quick start.
4. Demo flow.
5. Architecture summary.
6. Local-first rationale.
7. Validation rule summary.
8. Batch upload instructions.
9. Legal/research corpus pointer.
10. Data/fixture strategy.
11. Trade-offs and limitations.
12. Security/privacy notes.
13. Performance notes.

The README should be shorter and more evaluator-facing than this PRD. It should not repeat the entire legal corpus.

---

## 20. Build Priority Order

1. App skeleton and deployment path.
2. Upload and job creation.
3. Local OCR adapter and benchmark smoke test.
4. Single-label validation pipeline.
5. Government warning / alcohol / net contents P0 rules.
6. Result UI with evidence and source-backed explanation.
7. Batch upload and live progress.
8. CSV export.
9. Demo fixtures.
10. Legal corpus bootstrap and validation script.
11. README / docs / trade-offs.
12. Deployment smoke test at `www.labelsontap.ai`.

---

## 21. Reference Source Categories

This PRD is grounded in:

- Take-home stakeholder discovery notes.
- Form 5100.31 / COLAs Online field-mapping research.
- Local-first OCR architecture research.
- Federal prototype hardening and accessibility research.
- Deterministic CFR/rule-matrix research.
- Public COLA data and synthetic fixture generation research.
- Public data-boundary research.

Official/public references to include in the legal corpus:

- eCFR Part 4 — Wine labeling and advertising: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-4
- eCFR Part 5 — Distilled spirits labeling and advertising: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5
- eCFR Part 7 — Malt beverage labeling and advertising: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-7
- eCFR Part 13 — Labeling proceedings: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-13
- eCFR Part 16 — Alcoholic Beverage Health Warning Statement: https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16
- TTB Public COLA Registry: https://www.ttb.gov/regulated-commodities/labeling/cola-public-registry
- TTB Form 5100.31: https://www.ttb.gov/system/files/images/pdfs/forms/f510031.pdf
- TTB COLAs Online FAQs: https://www.ttb.gov/faqs/colas-and-formulas-online-faqs/print
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

---

## 22. Final Product Principle

Labels On Tap should fail deterministic, source-backed errors; pass only when OCR and validation are confident; and route subjective, precedent-driven, image-limited, or low-confidence findings to human review.

```text
Fail when the rule is deterministic.
Pass when the evidence is strong.
Needs Review when human judgment is required.
Always show why.
```
