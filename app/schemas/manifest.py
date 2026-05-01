from __future__ import annotations

from pydantic import BaseModel


class ManifestItem(BaseModel):
    filename: str
    fixture_id: str | None = None
    product_type: str
    brand_name: str
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    country_of_origin: str | None = None
    imported: bool = False
