"""Batch manifest schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ManifestItem(BaseModel):
    """One row or item from a CSV/JSON batch manifest.

    Notes
    -----
    Manual batch upload uses this model as the contract between user-supplied
    manifests and the same ``ColaApplication`` rule path used for single-label
    uploads.
    """

    filename: str
    panel_filenames: list[str] = Field(default_factory=list)
    fixture_id: str | None = None
    product_type: str
    brand_name: str
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    fanciful_name: str = ""
    bottler_producer_name_address: str = ""
    country_of_origin: str | None = None
    imported: bool = False
