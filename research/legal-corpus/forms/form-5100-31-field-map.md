# TTB Form 5100.31 Field Map

        | Form Field | App Schema Field | Label OCR Comparison? | Rule IDs | Notes |
        |---|---|---:|---|---|
        | Representative ID | representative_id | No | FORM_REPRESENTATIVE_CONTEXT | Proxy/agent context |
        | Plant Registry / Basic Permit | plant_registry_or_basic_permit | No | FORM_PERMIT_PRESENT | Applicant authority |
        | Source of Product | source_of_product | No | PRODUCT_SOURCE_ROUTING | Domestic/imported routing |
        | Country of Origin | country_of_origin | Yes, for imports | COUNTRY_OF_ORIGIN_MATCH | Import-origin match |
        | Serial Number | serial_number | No | FORM_SERIAL_PRESENT | Applicant tracking |
        | Type of Product | product_type | No | PRODUCT_TYPE_ROUTING | Wine / spirits / malt |
        | Brand Name | brand_name | Yes | FORM_BRAND_MATCHES_LABEL | Fuzzy match |
        | Fanciful Name | fanciful_name | Yes | FORM_FANCIFUL_NAME_MATCHES_LABEL | Fuzzy match |
        | Name and Address | applicant_name / applicant_address | Yes | FORM_NAME_ADDRESS_MATCHES_LABEL | Fuzzy/address match |
        | Formula / SOP | formula_id / statement_of_composition | Conditional | FORMULA_REQUIRED_RISK, SOC_EXACT_MATCH | Formula-trigger rules |
        | Grape Varietal | grape_varietals | Wine only | WINE_VARIETAL_MATCH | Wine-specific |
        | Appellation | appellation_of_origin | Wine only | WINE_APPELLATION_MATCH, GEOGRAPHIC_ORIGIN_RISK | Wine-specific |
        | Type of Application | type_of_application | Contextual | CERTIFICATE_EXEMPTION_CONTEXT | COLA/exemption/distinctive bottle |
        | Translations / Embossed Info | translations / embossed_or_blow_in_information | Conditional | FOREIGN_TEXT_TRANSLATION_REQUIRED | If foreign text present |
        | Label Dimensions | label_width_inches / label_height_inches | Indirect | WARNING_TYPE_SIZE_ESTIMATE | Needed for typography estimates |
