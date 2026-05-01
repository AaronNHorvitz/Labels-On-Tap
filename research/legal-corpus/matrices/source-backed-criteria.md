# Source-Backed Criteria Matrix

        Generated: 2026-04-30

        Every implemented rule should trace to at least one source, one detection method,
        one verdict policy, and eventually one fixture/test.

        | Rule ID | Category | Default Verdict | Sources | Status | Fixtures |
        |---|---|---|---|---|---|
        | GOV_WARNING_EXACT_TEXT | strict_compliance | fail | SRC_27_USC_215, SRC_27_CFR_PART_16 | planned | warning_good.png, warning_missing_machinery_comma.png, warning_title_case_heading.png |
| GOV_WARNING_HEADER_CAPS | strict_compliance | fail | SRC_27_CFR_PART_16 | planned | warning_title_case_heading.png |
| GOV_WARNING_HEADER_BOLD | cv_typography | needs_review | SRC_27_CFR_PART_16 | planned | warning_not_bold.png, warning_low_contrast.png |
| ALCOHOL_ABV_PROHIBITED | strict_compliance | fail | SRC_27_CFR_PART_5, SRC_27_CFR_PART_7 | planned | beer_5_percent_abv.png, spirits_45_percent_abv.png |
| MALT_NET_CONTENTS_16OZ_PINT | strict_compliance | fail | SRC_27_CFR_PART_7 | planned | beer_16_fl_oz_only.png, beer_1_pint_good.png |
| FORM_BRAND_MATCHES_LABEL | fuzzy_match | needs_review | SRC_TTB_FORM_5100_31, SRC_STAKEHOLDER_DISCOVERY | planned | brand_match_good.png, brand_case_difference.png, brand_mismatch.png |
| IMAGE_FORMAT_ALLOWED_TYPES | upload_preflight | fail | SRC_REPORT_14_HARDENING | planned | bad_pdf_upload.pdf, bad_double_extension.png.php |
| HEALTH_CLAIM_EXPLICIT | risk_review | needs_review | SRC_27_USC_205 | planned | bellion_style_health_claim.png |
| WINE_SEMI_GENERIC_NAME_DETECTED | risk_review | needs_review | SRC_TTB_IC_2006_01 | planned | wine_california_champagne_new_use.png, wine_angelica_exception.png |
| ABSINTHE_TERM_DETECTED | risk_review | needs_review | SRC_TTB_IC_2007_05 | planned | spirits_absinthe_standalone.png, spirits_absinthe_green_fairy_claim.png |
| SYNTHETIC_NEGATIVE_REQUIRED | data_strategy | info | SRC_REPORT_09_SYNTHETIC_FIXTURES, SRC_TTB_PUBLIC_COLA_REGISTRY | planned |  |
