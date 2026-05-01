# PHASE1_REJECTION.md - Rejection / Needs Correction Checklist

This checklist captures the Phase 1 rejection and Needs Correction reasons implied by the stakeholder interviews and technical requirements. The app should use these as the first product-completeness target for COLA-style application data plus label artwork verification.

## Application-Label Mismatch Reasons

- [ ] Brand name on the label does not match the application.
- [ ] Alcohol content / ABV on the label does not match the application.
- [ ] Class/type designation on the label does not match the application.
- [ ] Net contents on the label do not match the application.
- [ ] Bottler/producer name is missing or does not match expected application data.
- [ ] Bottler/producer address is missing or does not match expected application data.
- [ ] Country of origin is missing for an imported product.
- [ ] Country of origin on the label conflicts with the application.
- [ ] Fanciful name mismatch, if a fanciful name is present in the application.
- [ ] Label artwork does not represent the product/application record being reviewed.

## Government Warning Reasons

- [ ] Government Health Warning Statement is missing.
- [ ] Government warning text is not exact word-for-word.
- [ ] Government warning punctuation differs from required wording.
- [ ] `GOVERNMENT WARNING:` heading is not all caps.
- [ ] `GOVERNMENT WARNING:` heading is not bold.
- [ ] Warning text is too small.
- [ ] Warning text is buried or not reasonably visible.
- [ ] Warning statement is present but unreadable.

## Image Quality Reasons

- [ ] Label image is too blurry to read.
- [ ] Label image is photographed at a bad angle.
- [ ] Label image has poor lighting.
- [ ] Label image has glare.
- [ ] Label image is low contrast or otherwise hard to read.
- [ ] Required label areas are cropped, hidden, or not included.
- [ ] OCR confidence is too low to safely verify the label.

## Product-Type / Required-Element Reasons

- [ ] Required common label element is missing: brand name.
- [ ] Required common label element is missing: class/type designation.
- [ ] Required common label element is missing: alcohol content, where required.
- [ ] Required common label element is missing: net contents.
- [ ] Required common label element is missing: bottler/producer name and address.
- [ ] Required common label element is missing: country of origin for imports.
- [ ] Required common label element is missing: Government Health Warning Statement.
- [ ] Beverage-type-specific requirement is missing or inconsistent for wine, malt beverages, or distilled spirits.
- [ ] Distilled spirits label does not include expected spirits fields like class/type, proof/alcohol content, or net contents where applicable.
- [ ] Wine-specific fields such as varietal, appellation, or vintage are inconsistent if they appear in the application/label.
- [ ] Malt beverage-specific rules are violated, such as net contents expression issues.

## False-Rejection Guardrails

- [ ] Cosmetic capitalization differences should not automatically reject the application.
- [ ] Harmless punctuation/formatting differences should not automatically reject fuzzy fields like brand name.
- [ ] Ambiguous OCR or fuzzy matches should go to Needs Review, not hard Fail.
- [ ] The tool must distinguish true mismatch from obvious equivalence, like `STONE'S THROW` vs `Stone's Throw`.

## Operational / Intake Reasons

- [ ] Uploaded label image format is unsupported.
- [ ] Label image file is too large or unusable.
- [ ] Batch application row cannot be matched to its label image.
- [ ] Application data is incomplete enough that automated comparison cannot be trusted.
- [ ] Multiple applications/images are mixed up in a batch.
- [ ] The system cannot process fast enough for reviewer workflow. This is not a COLA rejection reason, but it is a tool-adoption failure reason.

## Phase 1 Acceptance Gate

- [ ] The app can compare COLA-style application data against label artwork and produce a reviewer-ready Pass / Needs Review / Fail report for the rejection reasons above.
