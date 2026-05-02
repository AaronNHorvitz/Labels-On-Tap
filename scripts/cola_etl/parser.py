"""Parse public COLA printable-form HTML into structured data.

The public registry printable page is a rendered Form 5100.31 artifact. It is
not a pristine API, so this parser is intentionally tolerant: extract known
fields when labels are present, preserve raw-ish form fields, and keep every
label attachment with source URL and panel metadata.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


TTB_BASE_URL = "https://ttbonline.gov"
DIMENSION_RE = re.compile(
    r"Actual\s+Dimensions:\s*([0-9.]+)\s*inches\s*W\s*X\s*([0-9.]+)\s*inches\s*H",
    re.IGNORECASE,
)


def normalize_space(value: str | None) -> str:
    """Collapse noisy HTML whitespace into readable text."""

    if not value:
        return ""
    return re.sub(r"[ \t\r\f\v]+", " ", unescape(value)).strip()


def normalize_lines(value: str | None) -> str:
    """Normalize text while preserving meaningful line breaks."""

    if not value:
        return ""
    lines = [normalize_space(line) for line in unescape(value).splitlines()]
    return "\n".join(line for line in lines if line)


def _has_class(tag: Tag, class_fragment: str) -> bool:
    classes = tag.get("class") or []
    return any(class_fragment in class_name for class_name in classes)


def _field_by_label(soup: BeautifulSoup, *needles: str) -> str:
    """Find the data cell associated with a visible form label."""

    lowered_needles = [needle.lower() for needle in needles]
    for div in soup.find_all("div"):
        if not isinstance(div, Tag) or not (
            _has_class(div, "label") or _has_class(div, "boldlabel")
        ):
            continue

        label_text = normalize_space(div.get_text(" "))
        label_lower = label_text.lower()
        if not any(needle in label_lower for needle in lowered_needles):
            continue

        parent = div.find_parent("td")
        if parent is None:
            next_data = div.find_next_sibling("div")
            if next_data and _has_class(next_data, "data"):
                return normalize_lines(next_data.get_text("\n"))
            parent = div.parent
        values: list[str] = []
        for data_div in parent.find_all("div"):
            if _has_class(data_div, "data"):
                value = normalize_lines(data_div.get_text("\n"))
                if value and value not in values:
                    values.append(value)
        return "\n".join(values)

    return ""


def _checked_alt_suffix(soup: BeautifulSoup, prefix: str) -> str:
    """Return the checked checkbox value encoded in an ``alt`` attribute."""

    prefix_lower = prefix.lower()
    for input_tag in soup.find_all("input"):
        if not input_tag.has_attr("checked"):
            continue
        alt = normalize_space(input_tag.get("alt", ""))
        if alt.lower().startswith(prefix_lower):
            return normalize_space(alt.split(":", 1)[-1])
    return ""


def _checked_row_text(soup: BeautifulSoup, alt_contains: str) -> str:
    """Return row text for a checked checkbox when the alt text is generic."""

    needle = alt_contains.lower()
    for input_tag in soup.find_all("input"):
        if not input_tag.has_attr("checked"):
            continue
        alt = normalize_space(input_tag.get("alt", ""))
        if needle not in alt.lower():
            continue
        row = input_tag.find_parent("tr")
        if row:
            return normalize_space(row.get_text(" "))
    return ""


def _value_after_heading(soup: BeautifulSoup, heading: str) -> str:
    """Extract a value from a bold heading followed by a data div."""

    heading_lower = heading.lower()
    for div in soup.find_all("div"):
        if not isinstance(div, Tag) or not _has_class(div, "boldlabel"):
            continue
        if heading_lower not in normalize_space(div.get_text(" ")).lower():
            continue
        next_data = div.find_next_sibling("div")
        if next_data and _has_class(next_data, "data"):
            return normalize_lines(next_data.get_text("\n"))
    return ""


def _special_wording(soup: BeautifulSoup) -> str:
    """Extract item 19 wording/translations when present."""

    for div in soup.find_all("div"):
        if not isinstance(div, Tag) or not _has_class(div, "data"):
            continue
        text = normalize_lines(div.get_text("\n"))
        if "19. SHOW ANY WORDING" not in text:
            continue
        match = re.search(r"APPEARING ON LABELS\.\s*(.*)", text, re.IGNORECASE | re.DOTALL)
        if match:
            return normalize_lines(match.group(1))
        return text
    return ""


def _normalize_product_type(value: str) -> str:
    text = value.lower()
    if "malt" in text:
        return "malt_beverage"
    if "distilled" in text or "spirit" in text:
        return "distilled_spirits"
    if "wine" in text:
        return "wine"
    return ""


def _status_from_text(value: str) -> str:
    match = re.search(r"STATUS\s+IS\s+([A-Z ]+)\.", value, re.IGNORECASE)
    if match:
        return normalize_space(match.group(1)).lower()
    return normalize_space(value).lower()


def _query_filename(src: str) -> str:
    parsed = urlparse(src)
    query = parse_qs(parsed.query)
    filename = query.get("filename", [""])[0]
    return unquote(filename)


def _context_lines_before_image(img: Tag) -> list[str]:
    fragments: list[str] = []
    for node in img.previous_elements:
        if isinstance(node, Tag) and node.name == "img":
            break
        if isinstance(node, NavigableString):
            value = normalize_lines(str(node))
            if value:
                fragments.append(value)
            if "AFFIX COMPLETE SET OF LABELS BELOW" in value:
                break

    lines: list[str] = []
    for fragment in reversed(fragments):
        lines.extend(line for line in fragment.splitlines() if line.strip())
    return lines


def _image_type_from_context(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if not line.lower().startswith("image type"):
            continue
        value = normalize_space(line.split(":", 1)[-1] if ":" in line else "")
        if value:
            return value
        for candidate in lines[index + 1 :]:
            if candidate.lower().startswith("actual dimensions"):
                return ""
            return normalize_space(candidate)
    return ""


def _dimensions_from_context(lines: list[str]) -> tuple[float | None, float | None]:
    joined = "\n".join(lines)
    match = DIMENSION_RE.search(joined)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _attachments(soup: BeautifulSoup, source_url: str | None) -> list[dict]:
    attachments: list[dict] = []
    base_url = source_url or TTB_BASE_URL
    for image in soup.find_all("img"):
        src = image.get("src", "")
        if "publicViewAttachment.do" not in src or "filetype=l" not in src:
            continue

        lines = _context_lines_before_image(image)
        width_inches, height_inches = _dimensions_from_context(lines)
        attachments.append(
            {
                "panel_order": len(attachments) + 1,
                "filename": _query_filename(src),
                "source_url": urljoin(base_url, src),
                "image_type": _image_type_from_context(lines),
                "width_inches": width_inches,
                "height_inches": height_inches,
                "alt_text": normalize_space(image.get("alt", "")),
                "html_width": image.get("width"),
                "html_height": image.get("height"),
            }
        )
    return attachments


def parse_public_cola_form(html: str, source_url: str | None = None) -> dict:
    """Parse one public COLA printable HTML page."""

    soup = BeautifulSoup(html, "html.parser")
    attachments = _attachments(soup, source_url)

    source_of_product = _checked_alt_suffix(soup, "Source of Product:")
    type_of_product = _checked_alt_suffix(soup, "Type of Product:")
    type_of_application = _checked_row_text(soup, "Type of Application")
    status_text = _value_after_heading(soup, "STATUS")

    form_fields = {
        "ttb_id": _field_by_label(soup, "TTB ID"),
        "representative_id": _field_by_label(soup, "REP. ID"),
        "plant_registry_basic_permit_brewers_number": _field_by_label(
            soup, "PLANT REGISTRY", "BASIC PERMIT"
        ),
        "source_of_product": source_of_product,
        "serial_number": _field_by_label(soup, "SERIAL NUMBER"),
        "type_of_product": type_of_product,
        "brand_name": _field_by_label(soup, "BRAND NAME"),
        "fanciful_name": _field_by_label(soup, "FANCIFUL NAME"),
        "applicant_name_address": _field_by_label(soup, "NAME AND ADDRESS OF APPLICANT"),
        "mailing_address": _field_by_label(soup, "MAILING ADDRESS"),
        "formula_id": _field_by_label(soup, "FORMULA"),
        "net_contents": _field_by_label(soup, "NET CONTENTS"),
        "alcohol_content": _field_by_label(soup, "ALCOHOL CONTENT"),
        "wine_appellation": _field_by_label(soup, "WINE APPELLATION"),
        "wine_vintage": _field_by_label(soup, "WINE VINTAGE"),
        "special_wording": _special_wording(soup),
        "type_of_application": type_of_application,
        "date_of_application": _field_by_label(soup, "DATE OF APPLICATION"),
        "applicant_or_agent_name": _field_by_label(soup, "PRINT NAME OF APPLICANT"),
        "date_issued": _field_by_label(soup, "DATE ISSUED"),
        "qualifications": _value_after_heading(soup, "QUALIFICATIONS"),
        "status": _status_from_text(status_text),
        "class_type_description": _value_after_heading(soup, "CLASS/TYPE DESCRIPTION"),
    }

    first_attachment = attachments[0] if attachments else {}
    application = {
        "fixture_id": form_fields["ttb_id"],
        "filename": first_attachment.get("filename") or f"{form_fields['ttb_id']}.jpg",
        "product_type": _normalize_product_type(type_of_product),
        "brand_name": form_fields["brand_name"],
        "fanciful_name": form_fields["fanciful_name"],
        "class_type": form_fields["class_type_description"],
        "alcohol_content": form_fields["alcohol_content"],
        "net_contents": form_fields["net_contents"],
        "country_of_origin": None,
        "imported": source_of_product.lower() == "imported",
        "formula_id": form_fields["formula_id"],
        "statement_of_composition": form_fields["special_wording"],
    }

    return {
        "source_type": "ttb_public_cola_registry",
        "source_url": source_url,
        "ttb_id": form_fields["ttb_id"],
        "form_fields": form_fields,
        "application": application,
        "attachments": attachments,
    }
