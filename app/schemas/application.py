from __future__ import annotations

from pydantic import BaseModel


class ColaApplication(BaseModel):
    fixture_id: str | None = None
    filename: str
    product_type: str = "malt_beverage"
    brand_name: str
    fanciful_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    country_of_origin: str = ""
    imported: bool = False
    formula_id: str = ""
    statement_of_composition: str = ""
