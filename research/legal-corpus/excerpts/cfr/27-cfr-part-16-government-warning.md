# 27 CFR Part 16 — Government Warning Implementation Excerpt

        Source ID: SRC_27_CFR_PART_16

        ## Canonical warning text

        GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

        ## Implementation notes

        - Normalize whitespace and OCR line breaks only.
        - Do not normalize punctuation.
        - Do not normalize capitalization in `GOVERNMENT WARNING:`.
        - Header capitalization is a separate strict check.
        - Bold detection is a CV heuristic and may return Needs Review.
