# DEMO_SCRIPT.md — Labels On Tap Evaluator Walkthrough

**Project:** Labels On Tap
**Canonical deployment URL:** `https://www.labelsontap.ai`
**Repository:** `https://github.com/AaronNHorvitz/Labels-On-Tap`
**Audience:** Take-home evaluators, technical reviewers, and product stakeholders
**Goal:** Demonstrate the core value of the app in approximately five minutes.

---

## 1. Demo Objective

This demo is designed to show that Labels On Tap is not a generic OCR toy. It is a **local-first, source-backed alcohol label preflight prototype** that helps reviewers triage routine label/application matching work.

The demo should prove five things quickly:

```text
1. The app is deployed and usable.
2. It can evaluate label artwork against expected application fields.
3. It returns raw Pass / Needs Review / Fail triage outcomes.
4. It explains each result with evidence and source-backed rationale.
5. It supports a batch-style review workflow without forcing evaluators to prepare their own data.
```

---

## 2. Pre-Demo Checklist

Before sending the deployed URL or presenting the app, verify:

```text
- [ ] https://www.labelsontap.ai loads.
- [ ] https://labelsontap.ai redirects to https://www.labelsontap.ai.
- [ ] /health returns OK.
- [ ] Home page displays 1-click demo buttons.
- [ ] Clean Label Demo works.
- [ ] Warning Failure Demo works.
- [ ] ABV Failure Demo works.
- [ ] Malt Net Contents Failure Demo works.
- [ ] Import Origin Demo works.
- [ ] Batch Demo works.
- [ ] Manual upload page loads.
- [ ] CSV export works.
- [ ] README.md links to this demo script.
- [ ] TASKS.md final checklist is updated.
- [ ] TRADEOFFS.md exists.
- [ ] Docker container restarts cleanly.
```

---

## 3. Five-Minute Evaluator Demo

### Opening Statement

Use this short framing:

> Labels On Tap is a local-first TTB label preflight prototype. It compares uploaded label artwork against Form 5100.31-style application fields using local OCR, deterministic source-backed rules, and fuzzy matching where reviewer judgment is appropriate. It does not use hosted ML endpoints and does not claim to issue final agency decisions. The raw Pass / Needs Review / Fail verdict is evidence for a reviewer workflow, not final agency action.

---

## 4. Demo Step 1 — Home Page and Product Framing

**Action:** Open:

```text
https://www.labelsontap.ai
```

**What to point out:**

```text
- Simple reviewer-oriented interface.
- One-click evaluator demo buttons.
- Manual upload option.
- Pass / Needs Review / Fail vocabulary.
- Planned reviewer-policy queues before final acceptance or rejection.
- Local-first / no hosted ML runtime positioning.
```

**Suggested narration:**

> The assignment emphasized that reviewers have mixed technical comfort levels, so the interface is intentionally simple. The one-click demo buttons remove evaluator friction and show the core workflows immediately.

Optional policy framing:

> In a production pilot, the raw system verdict would feed configurable reviewer queues. The agency could require human approval before rejection, before acceptance, or both. My recommended default is review before rejection on, review before acceptance off, so routine clean matches can move quickly while adverse or uncertain cases remain human-confirmed.

---

## 5. Demo Step 2 — Clean Label Pass

**Action:** Click:

```text
Run Clean Label Demo
```

**Expected result:**

```text
Overall verdict: Pass
```

**Expected checks:**

```text
- Brand name matches expected application field.
- Alcohol content uses acceptable wording.
- Net contents are acceptable.
- Government warning text matches expected canonical text.
- Government warning heading capitalization passes.
```

**What to point out:**

```text
- The app compares label text to application data.
- The result page shows checked rules, evidence text, and source-backed reasoning.
- This is the routine matching work Sarah described.
```

**Suggested narration:**

> This is the high-volume routine review use case: brand, class/type, alcohol content, net contents, country-of-origin context when relevant, and government warning checks.

---

## 6. Demo Step 3 — Government Warning Failure

**Action:** Return to home page and click:

```text
Run Warning Failure Demo
```

**Expected result:**

```text
Overall verdict: Fail
```

**Expected triggered rule:**

```text
GOV_WARNING_EXACT_TEXT
```

**What to point out:**

```text
- Government warning text is treated as strict, not fuzzy.
- Whitespace may be normalized, but punctuation, words, and required capitalization are not.
- The app shows expected vs. observed evidence.
```

**Suggested narration:**

> This is Jenny’s strict-compliance case. Some fields allow reviewer judgment, but the government warning is a strict source-backed check.

---

## 7. Demo Step 4 — ABV Prohibited Wording Failure

**Action:** Click:

```text
Run ABV Failure Demo
```

**Expected result:**

```text
Overall verdict: Fail
```

**Expected triggered rule:**

```text
ALCOHOL_ABV_PROHIBITED
```

**What to point out:**

```text
- The app detects prohibited shorthand in alcohol-content statements.
- The check is fast and deterministic.
- The reviewer sees evidence text and an explanation.
```

**Suggested narration:**

> This demonstrates why the prototype does not need a large vision-language model. Many high-value corrections are deterministic text and formatting checks once OCR gives us the label text.

---

## 8. Demo Step 5 — Malt Net Contents Failure

**Action:** Click:

```text
Run Malt Net Contents Failure Demo
```

**Expected result:**

```text
Overall verdict: Fail
```

**Expected triggered rule:**

```text
MALT_NET_CONTENTS_16OZ_PINT
```

**What to point out:**

```text
- The rule is beverage-type gated.
- It applies to malt beverages only.
- It shows exact reviewer action: verify/correct net contents declaration.
```

**Suggested narration:**

> This rule shows the value of commodity-specific validation. The same OCR text can mean different things depending on whether the product is wine, spirits, or malt beverage.

---

## 9. Demo Step 6 — Needs Review Case

**Action:** Click:

```text
Run Batch Demo
```

Then open the `low_confidence_blur_review` detail row.

**Expected result:**

```text
Overall verdict: Needs Review
```

**Expected reason examples:**

```text
- OCR confidence is low.
- Image quality limits certainty.
- Government warning boldness requires manual typography verification.
```

**What to point out:**

```text
- The app does not overclaim certainty.
- Low-confidence and image-limited checks are routed to human review.
- This is deliberate and safer than false pass/fail automation.
```

**Suggested narration:**

> Needs Review is not a failure of the tool. It is a safety mechanism. When image quality or legal context prevents a deterministic answer, the system escalates rather than guessing.

---

## 10. Demo Step 7 — Country of Origin Demo

**Action:** Return to home page and click:

```text
Run Import Origin Demo
```

**Expected result:**

```text
Overall verdict: Pass
```

**Expected checked rule:**

```text
COUNTRY_OF_ORIGIN_MATCH
```

**What to point out:**

```text
- Imported product is marked in the application fields.
- Country of origin is provided as France.
- OCR evidence includes PRODUCT OF FRANCE.
- The result detail page shows the imported/country fields.
```

**Suggested narration:**

> Country of origin is handled as a first-class application field for imported products, not as an afterthought.

---

## 11. Demo Step 8 — Batch Demo

**Action:** Click:

```text
Run Batch Demo
```

**Expected result:**

```text
Batch-style results table appears with 12 rows.
```

**Expected table rows:**

```text
clean_malt_pass                Pass
warning_missing_comma_fail     Fail
warning_title_case_fail        Fail
abv_prohibited_fail            Fail
malt_16_fl_oz_fail             Fail
brand_case_difference_pass     Pass
low_confidence_blur_review     Needs Review
brand_mismatch_fail            Fail
imported_missing_country_review Needs Review
conflicting_country_origin_fail Fail
warning_missing_block_review   Needs Review
imported_country_origin_pass   Pass
```

Expected summary:

```text
Processed: 12 / 12
Pass: 3
Needs Review: 3
Fail: 6
```

**What to point out:**

```text
- Batch review is a core stakeholder need.
- The prototype shows results in a triage table.
- Reviewers can prioritize Fail and Needs Review items.
- The planned policy layer can split raw results into Ready to accept,
  Acceptance review, Manual evidence review, Rejection review, and Ready to reject.
- The workflow is designed to scale toward 200+ label batches.
```

**Suggested narration:**

> Sarah specifically raised peak-season importer batches. The goal is not to make reviewers wait silently; it is to provide immediate progress and triage visibility.

---

## 12. Demo Step 9 — Result Detail Page

**Action:** Open one failed result detail page.

**Show:**

```text
- Uploaded/demo label filename
- Application fields
- OCR text or fixture OCR source
- Rule checklist
- Evidence text
- Expected value
- Observed value
- Reviewer action
- Source references or source IDs
```

**Suggested narration:**

> Each rule is designed to be auditable. The reviewer should be able to see what was found, why it was flagged, and what action is recommended.

---

## 13. Demo Step 10 — Manual Upload

**Action:** Return to the home page and use the Single Label Upload section.

**Show fields:**

```text
- Product type
- Brand name
- Class/type
- Alcohol content
- Net contents
- Imported?
- Country of origin
- Label image
```

**What to point out:**

```text
- Country of origin is included for imports.
- The UI is intentionally simple.
- The form maps to Form 5100.31-style application data without overwhelming the user.
```

**Suggested narration:**

> The deployed app can run from generated demo fixtures or from a manually uploaded label. The simple mode keeps the evaluator workflow fast.

---

## 14. Demo Step 11 — Export / Summary

**Action:** Click:

```text
Export CSV
```

**What to point out:**

```text
- Results can be exported for reviewer workflow.
- Each row includes status and top reason.
```

---

## 15. What Not to Overclaim

Do **not** say:

```text
This approves or rejects COLAs.
The current prototype has final agency-action queues fully implemented.
This guarantees legal compliance.
This replaces TTB reviewers.
This has all federal beverage alcohol law implemented.
This performs final typography certification from arbitrary raster images.
This uses a hidden rejected-label training corpus.
```

Say:

```text
This is a source-backed preflight and reviewer-support prototype.
This catches deterministic routine issues quickly.
This routes uncertainty to Needs Review.
This separates raw machine verdicts from future reviewer approval policy.
This is designed to reduce repetitive matching workload.
This does not use hosted ML endpoints.
This is extensible through the legal corpus and rule matrix.
```

---

## 16. If Something Breaks During Demo

### If OCR is slow

Use one-click fixture demos and explain:

```text
The demo fixtures use deterministic OCR text to make evaluator results stable. Runtime local OCR is available for manual uploads, and performance is documented separately.
```

### If manual upload fails

Use one-click demos and explain:

```text
The deployed evaluator flow is demonstrated through generated source-backed fixtures. Manual upload is part of the same route structure and is documented in the task plan.
```

### If manual batch upload needs explanation

Use one-click batch demo and explain:

```text
The batch demo uses pre-generated fixtures to show triage behavior. Manual manifest-backed batch upload is also available on the home page for CSV/JSON manifests plus multiple JPG/PNG label images; in the sprint prototype it runs synchronously in the web process.
```

### If TLS is still propagating

Use:

```text
http://<server-ip>
```

only as an emergency fallback through Caddy, and explain that DNS/TLS propagation is in progress. The target canonical URL remains:

```text
https://www.labelsontap.ai
```

---

## 17. Closing Statement

Use this closing line:

> Labels On Tap demonstrates a practical path for local-first, source-backed label verification. It focuses on the routine matching and deterministic checks that consume reviewer time, while preserving human judgment for ambiguous or legally contextual issues.

---

## 18. Demo Success Criteria

A successful demo means the evaluator sees:

```text
- The app loads at https://www.labelsontap.ai.
- A clean label produces Pass.
- A government warning defect produces Fail.
- An ABV wording defect produces Fail.
- A malt net-contents defect produces Fail.
- An imported country-of-origin check produces Pass.
- A low-confidence or typography-limited case produces Needs Review.
- A batch-style triage view appears.
- A result detail page explains evidence and reviewer action.
- The repo documents trade-offs and source-backed rule design.
```

If those are visible, the prototype has demonstrated the assignment’s core value.
