# Fixture Provenance

        Generated: 2026-04-30

        This file maps demo/test fixtures to rule IDs, source references, and expected verdicts.

        | Fixture | Rule IDs | Expected Verdict | Source Type | Mutation Summary |
        |---|---|---|---|---|
        | warning_missing_machinery_comma | GOV_WARNING_EXACT_TEXT | fail | synthetic_mutation | Removed required comma after 'machinery' in the government warning. |
| beer_16_fl_oz_only | MALT_NET_CONTENTS_16OZ_PINT | fail | synthetic_mutation | Used 16 fl. oz. instead of 1 Pint for a malt beverage fixture. |
| beer_5_percent_abv | ALCOHOL_ABV_PROHIBITED | fail | synthetic_mutation | Used ABV shorthand in alcohol-content statement. |
| bellion_style_health_claim | HEALTH_CLAIM_EXPLICIT | needs_review | synthetic_mutation | Injected health-benefit/risk-reduction language near product identity text. |
