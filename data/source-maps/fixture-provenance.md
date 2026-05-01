# Fixture Provenance

Generated: 2026-04-30

This file maps demo/test fixtures to rule IDs, source references, and expected verdicts.

| Fixture | Rule IDs | Expected Verdict | Source Type | Mutation Summary |
|---|---|---|---|---|
| warning_missing_machinery_comma | GOV_WARNING_EXACT_TEXT | fail | synthetic_mutation | Removed required comma after 'machinery' in the government warning. |
| beer_16_fl_oz_only | MALT_NET_CONTENTS_16OZ_PINT | fail | synthetic_mutation | Used 16 fl. oz. instead of 1 Pint for a malt beverage fixture. |
| beer_5_percent_abv | ALCOHOL_ABV_PROHIBITED | fail | synthetic_mutation | Used ABV shorthand in alcohol-content statement. |
| bellion_style_health_claim | HEALTH_CLAIM_EXPLICIT | needs_review | synthetic_mutation | Injected health-benefit/risk-reduction language near product identity text. |
| clean_malt_pass | GOV_WARNING_EXACT_TEXT, GOV_WARNING_HEADER_CAPS, ALCOHOL_ABV_PROHIBITED, MALT_NET_CONTENTS_16OZ_PINT, FORM_BRAND_MATCHES_LABEL | pass | synthetic_generation | Control fixture with matching application fields and canonical warning text. |
| warning_missing_comma_fail | GOV_WARNING_EXACT_TEXT | fail | synthetic_generation | Removed the required comma after 'machinery' in the government warning. |
| warning_title_case_fail | GOV_WARNING_HEADER_CAPS | fail | synthetic_generation | Changed the warning heading from all caps to title case. |
| abv_prohibited_fail | ALCOHOL_ABV_PROHIBITED | fail | synthetic_generation | Used ABV shorthand in a malt beverage alcohol-content statement. |
| malt_16_fl_oz_fail | MALT_NET_CONTENTS_16OZ_PINT | fail | synthetic_generation | Used 16 fl. oz. where the demo application expects 1 Pint. |
| brand_case_difference_pass | FORM_BRAND_MATCHES_LABEL | pass | synthetic_generation | Changed brand casing to validate fuzzy matching tolerance. |
| low_confidence_blur_review | OCR_LOW_CONFIDENCE, GOV_WARNING_HEADER_BOLD_REVIEW | needs_review | synthetic_generation | Applied blur to create an OCR/typography confidence review fixture. |
