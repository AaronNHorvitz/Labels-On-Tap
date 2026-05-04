"""Application-field schemas used by label verification.

Notes
-----
The model is intentionally close to the fields surfaced in the take-home brief
and Form 5100.31-style workflows. It is not a complete COLA application model.
"""

from __future__ import annotations

from pydantic import BaseModel


class ColaApplication(BaseModel):
    """Structured application fields compared against label OCR text.

    Attributes
    ----------
    filename:
        Original label filename shown in the UI and CSV export.
    product_type:
        Broad commodity type used to route product-specific rules.
    brand_name:
        Application brand value used by fuzzy label matching.
    bottler_producer_name_address:
        Optional name/address text for the responsible producer, bottler,
        importer, or applicant when available.
    country_of_origin:
        Required for imported-product checks when ``imported`` is true.
    imported:
        Controls whether ``COUNTRY_OF_ORIGIN_MATCH`` is enforced.
    """

    fixture_id: str | None = None
    filename: str
    product_type: str = "malt_beverage"
    brand_name: str
    fanciful_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    bottler_producer_name_address: str = ""
    country_of_origin: str | None = None
    imported: bool = False
    formula_id: str = ""
    statement_of_composition: str = ""
