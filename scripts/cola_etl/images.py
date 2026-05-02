"""Image validation helpers for public COLA attachment downloads.

The TTB attachment endpoint can return a normal HTTP 200 response containing an
HTML error page when an image cannot be rendered. These helpers make the ETL
prove that downloaded bytes are actually readable raster images before the
OCR/evaluation layer accepts them.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class InvalidImageDownload(ValueError):
    """Raised when a downloaded attachment is not a usable image."""


def content_looks_like_html(content: bytes) -> bool:
    """Return True when response bytes look like an HTML page."""

    stripped = content.lstrip()[:512].lower()
    return (
        stripped.startswith(b"<!doctype html")
        or stripped.startswith(b"<html")
        or b"<title>ttb online" in stripped
        or b"unable to render attachment" in stripped
    )


def validate_image_bytes(content: bytes, *, content_type: str = "") -> bytes:
    """Validate that response bytes are a real image and return them unchanged.

    Parameters
    ----------
    content:
        Raw HTTP response body.
    content_type:
        Optional response ``Content-Type`` header.

    Raises
    ------
    InvalidImageDownload
        Raised when the response body is empty, HTML, an unexpected MIME type,
        or unreadable by Pillow.
    """

    if not content:
        raise InvalidImageDownload("empty attachment response")

    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type and not media_type.startswith("image/") and media_type != "application/octet-stream":
        raise InvalidImageDownload(f"unexpected attachment content type: {content_type}")
    if content_looks_like_html(content):
        raise InvalidImageDownload("attachment endpoint returned HTML instead of an image")

    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageDownload(f"attachment bytes are not a readable image: {exc}") from exc
    return content


def is_valid_image_path(path: Path) -> bool:
    """Return True when a local path points to a readable image."""

    try:
        validate_image_bytes(path.read_bytes())
    except (OSError, InvalidImageDownload):
        return False
    return True
